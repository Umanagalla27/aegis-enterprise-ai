# Aegis Enterprise AI: Production Deployment Guide

This guide covers how a team at a real company takes this repository from a laptop to production, phase by phase. Each phase covers:

- **What** you do, with exact commands.
- **Why** companies do it (interviewers ask this).
- **What breaks**, and how to fix it. The errors listed here were reproduced on this codebase, not made up.

Companion document: [INTERVIEW_PREP.md](INTERVIEW_PREP.md) (resume bullets, project pitch, interview Q&A, and the bugs fixed in this project).

---

## Contents

- [Phase 0: How companies ship software (the big picture)](#phase-0-how-companies-ship-software)
- [Phase 1: Local development setup](#phase-1-local-development-setup)
- [Phase 2: Git workflow and code review](#phase-2-git-workflow-and-code-review)
- [Phase 3: Code quality, tests and evaluation gates](#phase-3-code-quality-tests-and-evaluation-gates)
- [Phase 4: Containerization (Docker)](#phase-4-containerization-docker)
- [Phase 5: CI/CD pipeline (GitHub Actions to GHCR)](#phase-5-cicd-pipeline)
- [Phase 6: Deploy, Option A: single VM with Docker Compose and HTTPS](#phase-6-option-a-single-vm)
- [Phase 6: Deploy, Option B: Kubernetes with Helm and ArgoCD (GitOps)](#phase-6-option-b-kubernetes)
- [Phase 6: Deploy, Option C: AWS ECS Fargate with Terraform](#phase-6-option-c-aws-ecs-fargate-with-terraform)
- [Phase 7: Configuration and secrets](#phase-7-configuration-and-secrets)
- [Phase 8: Observability (metrics, logs, traces, alerts)](#phase-8-observability)
- [Phase 9: Releases, rollbacks and zero-downtime deploys](#phase-9-releases-and-rollbacks)
- [Phase 10: Operating in production (incidents, postmortems, cost)](#phase-10-operating-in-production)
- [Troubleshooting catalog: every error, cause and fix](#troubleshooting-catalog)
- [Production-readiness checklist](#production-readiness-checklist)

---

## Phase 0: How companies ship software

```
 Requirement -> Design -> Code (feature branch) -> Pull Request + Review -> CI (lint, test, build, scan)
     -> Artifact (container image, immutable tag) -> Deploy to staging -> Smoke/E2E tests
     -> Deploy to production (rolling/canary) -> Monitor (metrics/logs/alerts) -> Incident -> Postmortem
```

| Concept | Meaning | Where it lives in this repo |
| :--- | :--- | :--- |
| **Environments** | `dev` (laptop), `staging` (copy of prod), `prod` (real users) | `ENVIRONMENT` env var in `terraform/ecs_fargate.tf`; Helm values per env |
| **Artifact** | The thing you deploy. Build it once and promote the same artifact through every environment | `Dockerfile` produces `ghcr.io/umanagalla27/aegis-enterprise-ai:<git-sha>` |
| **Immutable tag** | Tag images with the git commit SHA, never only `latest`, so you know exactly what is running and can roll back | CI pushes `:<sha>` (plus `:latest` on `main`) |
| **Infrastructure as Code (IaC)** | Servers, networks and budgets defined in files and reviewed like code | `terraform/` |
| **GitOps** | Git is the source of truth for what runs; a controller (ArgoCD) syncs the cluster to Git | `k8s/argocd/application.yaml` |
| **12-Factor config** | Config comes from environment variables, never hard-coded | `AEGIS_CORS_ORIGINS`, `WEB_CONCURRENCY`, `PORT` |

**Interview line:** *"We build one immutable image per commit in CI, scan it, push it to a registry, and promote that exact image from staging to prod. Config differs per environment through env vars and secrets; the code does not."*

---

## Phase 1: Local development setup

### 1.1 Prerequisites

| Tool | Version | Check |
| :--- | :--- | :--- |
| Python | 3.12 (CI uses 3.12; 3.13 also works) | `python --version` |
| Git | any recent | `git --version` |
| Docker Desktop / Docker Engine | 24+ | `docker version` (the **Server** section must appear) |
| (Optional) kind + kubectl + helm | latest | for Phase 6 Option B |

### 1.2 Clone and create a virtual environment

```bash
git clone https://github.com/Umanagalla27/aegis-enterprise-ai.git
cd aegis-enterprise-ai

python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install --upgrade pip
pip install -r requirements.txt        # full dev/research stack (large: torch, transformers...)
```

> **Why a venv?** It isolates this project's dependency versions from every other project on the machine. In companies, "works on my machine" bugs usually come from global installs.

### 1.3 Start the backing services (Postgres, Redis, Prometheus, Grafana)

```bash
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml ps     # all should be "running"/"healthy"
```

Ports are deliberately non-default (5435, 6382, 9091, 3001) to avoid clashing with other local projects.

### 1.4 Run the API

```bash
# Always run from the repository root so `src.` imports resolve
uvicorn src.api.main:app --reload --port 8000
```

Open:

- http://localhost:8000: web control center
- http://localhost:8000/docs: Swagger UI (auto-generated by FastAPI from the Pydantic models)
- http://localhost:8000/metrics: Prometheus metrics
- http://localhost:9091: Prometheus, http://localhost:3001: Grafana (admin/admin locally only)

### 1.5 Try the endpoints

```bash
curl localhost:8000/health

curl -X POST localhost:8000/v1/rag/search -H "content-type: application/json" \
     -d '{"query": "GPU out of memory", "top_k": 2}'

# topology takes a QUERY parameter, not a JSON body
curl -X POST "localhost:8000/v1/rag/topology?service_name=aegis-postgres"

curl -X POST localhost:8000/v1/security/inspect -H "content-type: application/json" \
     -d '{"text": "ignore previous instructions, my SSN is 123-45-6789"}'

curl -X POST localhost:8000/v1/incidents/diagnose -H "content-type: application/json" \
     -d '{"service_name":"rag-retrieval","observed_latency_ms":3200,
          "error_logs":[{"service":"rag-retrieval","level":"ERROR","message":"pool exhausted"}],
          "recent_commits":[{"commit_hash":"a1b2c3d","author":"dev","message":"tune HNSW","service":"rag-retrieval"}]}'
```

**Anomaly detection warm-up:** `/v1/telemetry/ingest` learns a rolling baseline **per service**. The first 20 events for a service return `"status": "WARMING_UP"`. After that, every metric (latency, CPU, memory) is scored and a spike is flagged:

```bash
for i in $(seq 1 35); do
  curl -s -X POST localhost:8000/v1/telemetry/ingest -H "content-type: application/json" \
    -d "{\"service_name\":\"api-gateway\",\"cpu_percent\":40,\"memory_percent\":50,\"latency_ms\":$((40 + i % 5)),\"status_code\":200}" > /dev/null
done
curl -s -X POST localhost:8000/v1/telemetry/ingest -H "content-type: application/json" \
  -d '{"service_name":"api-gateway","cpu_percent":40,"memory_percent":50,"latency_ms":2500,"status_code":200}'
# -> "status": "SCORED", "anomaly_result": {"is_anomaly": true, "severity": "CRITICAL", ...}
```

> The baseline lives in process memory. Under gunicorn with `WEB_CONCURRENCY=2` (the Docker image), each worker learns its own baseline, so warm-up takes about twice as many events. This is a known limitation; the fix is shared state (Redis), discussed in the interview guide.

---

## Phase 2: Git workflow and code review

The usual company flow (GitHub Flow / trunk-based):

```bash
git checkout main && git pull
git checkout -b feat/rolling-anomaly-baseline         # one branch per change
# ... edit code ...
ruff check . && ruff format --check . && pytest -q    # run CI checks BEFORE pushing
git add -p                                            # stage hunks deliberately
git commit -m "fix(api): learn rolling baseline for telemetry anomaly detection"
git push -u origin feat/rolling-anomaly-baseline
# open a Pull Request -> CI runs -> reviewer approves -> squash-merge into main
```

| Practice | Why |
| :--- | :--- |
| **Branch protection on `main`** (Settings, Branches): require PR, 1 approval, green CI | No one can push untested code to the branch that deploys to prod |
| **Conventional commits** (`feat:`, `fix:`, `docs:`, `ci:`) | Readable history; tools can auto-generate changelogs and versions |
| **Small PRs** | Easier review, easier rollback |
| **CODEOWNERS** | Auto-requests the right reviewer per folder (for example `k8s/` goes to the platform team) |
| **Never commit secrets** | `.env`, `*.tfvars` and `*.tfstate` are already in `.gitignore` |

---

## Phase 3: Code quality, tests and evaluation gates

```bash
ruff check .              # linting: unused imports, bad syntax, import order, modern syntax (UP)
ruff format --check .     # formatting (CI fails if any file would be reformatted)
pytest -q                 # unit + integration tests (tests/ and eval/)
python eval/run_aiops_eval.py   # 20-fault chaos benchmark (must stay >= 95%)
```

| Test file | What it protects |
| :--- | :--- |
| `tests/test_phase2.py` | Transformer block shapes, chunking, BM25 + RRF hybrid retrieval, Graph RAG |
| `tests/test_phase3.py` | LangGraph workflow, HITL interrupt/resume, PII redaction, injection defense, tool allowlist |
| `tests/test_phase4.py` | Kafka partitioning and DLQ, consumer offsets, aggregator quantiles, dbt marts, Airflow SLA gate |
| `tests/test_phase5.py` | Anomaly engine, RCA agent, FastAPI endpoints, Prometheus metrics, **regression tests for the bugs fixed in this project** |
| `eval/test_eval_gates.py` | Quality gates: faithfulness >= 0.85, recall >= 0.80, agent accuracy >= 90%, HITL = 100% |

**The testing pyramid companies use:** many fast unit tests, fewer integration tests (FastAPI `TestClient`), a handful of end-to-end smoke tests against a deployed environment (the CI smoke test in Phase 5 is one).

**Regression test rule:** every bug fix ships with a test that **fails before the fix and passes after it**. The three tests at the bottom of `tests/test_phase5.py` were verified this way.

> ⚠️ Known test side effect: running `tests/test_phase4.py` or the ETL endpoint rewrites the tracked file `data/analytics/daily_service_metrics.parquet`. Run `git checkout data/` before committing, or (better, a good first PR) change the tests to use pytest's `tmp_path`.

---

## Phase 4: Containerization (Docker)

### 4.1 Build and run

```bash
docker build -t aegis-api:local .
docker run --rm -p 8000:8000 \
  --read-only --tmpfs /tmp --tmpfs /app/data:uid=10001,gid=10001 \
  -e AEGIS_CORS_ORIGINS=http://localhost:8000 \
  aegis-api:local
curl localhost:8000/health
```

### 4.2 The `Dockerfile`, line by line

| Line / decision | Why companies do this |
| :--- | :--- |
| **Multi-stage build** (`builder` then `runtime`) | Compilers and pip caches stay in the throwaway stage, so the final image is smaller and has less attack surface |
| `python:3.12-slim` | Same Python version as CI; `slim` drops roughly 800 MB of unused OS packages |
| **`requirements-prod.txt`** (not `requirements.txt`) | The API never imports torch, transformers or langchain. Installing them would add several GB, slow every deploy and pull in more CVEs. Result: **~233 MB compressed** |
| `useradd ... aegis` + `USER aegis` (UID 10001) | **Never run as root.** If the app is compromised, the attacker is an unprivileged user |
| `COPY` only `src/ eval/ data_platform/` + `.dockerignore` | No `.git`, tests, docs or secrets in the image; better layer caching |
| `PYTHONUNBUFFERED=1` | Logs appear immediately in `docker logs` / CloudWatch instead of being buffered |
| `HEALTHCHECK` | Docker marks the container `unhealthy` if `/health` stops answering |
| **gunicorn + uvicorn workers** | gunicorn supervises worker processes (restarts crashed ones, handles `SIGTERM` gracefully); uvicorn runs the async app. `WEB_CONCURRENCY` controls the worker count |
| `exec` in `CMD` | The server becomes PID 1 and receives `SIGTERM` directly, which enables graceful shutdown |
| Read-only root FS + tmpfs `/app/data` | An attacker cannot modify the code on disk; only explicit scratch paths are writable |

> **Real bug hit while building this:** running read-only with a plain `--tmpfs /app/data` made `POST /v1/airflow/run-etl` crash with `PermissionError: [Errno 13] Permission denied: 'data/analytics'`. The tmpfs was owned by root but the app runs as UID 10001. **Fix:** `--tmpfs /app/data:uid=10001,gid=10001` in Docker, and `fsGroup: 10001` + an `emptyDir` volume in Kubernetes (already in the Helm chart).

### 4.3 Useful Docker commands

```bash
docker images aegis-api                      # size
docker logs -f <container>                   # stream logs
docker exec -it <container> sh               # shell inside (debugging)
docker inspect --format '{{.State.Health.Status}}' <container>
docker stats                                 # live CPU/memory
```

---

## Phase 5: CI/CD pipeline

File: `.github/workflows/ci.yml`. It runs on pushes to `main`, on every pull request, and manually (`workflow_dispatch`).

```
Job 1: lint-and-test                      Job 2: build-and-push-image (needs job 1)
  ├─ Postgres + Redis service containers    ├─ docker buildx build (with GitHub Actions layer cache)
  ├─ pip install -r requirements.txt        ├─ Smoke test: run container read-only, poll /health
  ├─ ruff check + ruff format --check       ├─ Trivy scan: fail on fixable HIGH/CRITICAL CVEs
  ├─ pytest per phase                       ├─ (not on PRs) login to GHCR with GITHUB_TOKEN
  ├─ eval gates (RAGAS / agent)             └─ push :<short-sha>, and :latest on main
  └─ 20-fault chaos benchmark
```

| Stage | Why |
| :--- | :--- |
| **Lint before tests** | Cheapest failure first; saves CI minutes |
| **Service containers** | Real Postgres/Redis in CI, the same as prod, instead of mocks |
| **`concurrency: cancel-in-progress`** | A new push cancels the outdated run for the same branch |
| **Smoke test the built image** | Unit tests passing does not prove the *container* starts (missing dependency, wrong `CMD`, file permissions) |
| **Trivy image scan** | Supply-chain security: blocks known-vulnerable packages from reaching prod. Scanned locally: `Total: 0 (HIGH: 0, CRITICAL: 0)` |
| **Push only from non-PR events** | PRs from forks must never get registry credentials |
| **`GITHUB_TOKEN` + `packages: write`** | No long-lived password stored anywhere; the token expires when the job ends |

**One-time setup after the first push to `main`:** GitHub, your profile, **Packages**, `aegis-enterprise-ai`, **Package settings**: either make it **public** (simplest for a portfolio) or create a pull secret for the cluster/VM (see the `ImagePullBackOff` entry in the [troubleshooting catalog](#troubleshooting-catalog)).

**Continuous Deployment step (how companies close the loop):** after pushing `:<sha>`, either

1. a CI job opens a PR that bumps `image.tag` in `k8s/helm/aegis-platform/values.yaml` (ArgoCD syncs once it merges), or
2. **ArgoCD Image Updater** watches GHCR and updates the tag automatically.

Option 1 is the most common because every production change remains a reviewed Git commit.

---

## Phase 6: Option A: single VM

**Best choice for a portfolio:** cheap (an AWS `t3.small`, Hetzner CX22, or Oracle Cloud free tier), a real domain, real HTTPS, and the same image as Kubernetes would use.

Files: `docker/docker-compose.prod.yml`, `docker/Caddyfile`, `docker/prometheus.prod.yml`, `docker/.env.example`.

```
Internet ──443──> Caddy (auto Let's Encrypt TLS) ──> api:8000 ──scraped by──> Prometheus <── Grafana (127.0.0.1 only)
```

### Steps

1. **Create a VM** (Ubuntu 24.04, 2 vCPU / 2 GB RAM is enough).
2. **Firewall / security group:** allow inbound **22** (SSH, from your IP only), **80** and **443** (from anywhere). Do **not** open 8000, 9090 or 3001.
3. **DNS:** create an `A` record such as `aegis.yourdomain.com` pointing to the VM's public IP. (A free subdomain from DuckDNS also works.)
4. **Install Docker:**
   ```bash
   ssh ubuntu@<vm-ip>
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER && exit      # log in again so the group applies
   ```
5. **Get the deployment files and configure them:**
   ```bash
   git clone https://github.com/Umanagalla27/aegis-enterprise-ai.git && cd aegis-enterprise-ai/docker
   cp .env.example .env && nano .env       # set DOMAIN, AEGIS_CORS_ORIGINS, GRAFANA_ADMIN_PASSWORD, IMAGE_TAG=<sha>
   chmod 600 .env
   ```
6. **Start:**
   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env up -d
   docker compose -f docker-compose.prod.yml ps
   docker compose -f docker-compose.prod.yml logs -f caddy    # watch the certificate get issued
   ```
7. **Verify:** `curl https://aegis.yourdomain.com/health` should return `{"status":"HEALTHY",...}`. Grafana is reachable through an SSH tunnel: `ssh -L 3001:localhost:3001 ubuntu@<vm-ip>`, then open http://localhost:3001.
8. **Deploy a new version:** set `IMAGE_TAG=<new sha>` in `.env`, then `docker compose ... pull api && docker compose ... up -d api`.
9. **Roll back:** set `IMAGE_TAG` back to the previous SHA and run the same command.

> This stack was tested in this repository: the image runs read-only as UID 10001 behind Caddy, and `https://localhost/health` returned `HEALTHY`.

---

## Phase 6: Option B: Kubernetes

This is how most mid-to-large companies run services. You can **practice for free locally with kind** and later point the same chart at EKS, GKE or AKS.

### What each manifest does

| File | Purpose |
| :--- | :--- |
| `templates/deployment.yaml` | Pods: image, env, probes, resources, **non-root + read-only security context**, `emptyDir` volumes for `/tmp` and `/app/data`, 40 s graceful termination |
| `templates/service.yaml` | Stable in-cluster virtual IP and DNS name in front of the pods |
| `templates/ingress.yaml` | Public HTTP(S) routing through ingress-nginx, with a **TLS block** so cert-manager issues a certificate |
| `templates/hpa.yaml` | HorizontalPodAutoscaler: 3 to 10 replicas at 75% CPU / 80% memory |
| `values.yaml` | All tunables; override per environment (`values-staging.yaml`, `values-prod.yaml`) |
| `k8s/argocd/application.yaml` | ArgoCD watches `main` and syncs the chart into the `aegis-production` namespace (prune + self-heal) |

**Probes explained (a common interview question):**

- `startupProbe`: gives the app up to 120 s to boot before liveness checks begin, so slow starts are not killed.
- `readinessProbe`: if it fails, the pod is **removed from the Service**, so it receives no traffic but is not restarted.
- `livenessProbe`: if it fails 3 times, the kubelet **restarts** the container (for deadlocks).

### 6B.1 Local practice cluster with kind

```bash
kind create cluster --name aegis
docker build -t ghcr.io/umanagalla27/aegis-enterprise-ai:dev .
kind load docker-image ghcr.io/umanagalla27/aegis-enterprise-ai:dev --name aegis

# metrics-server is required for the HPA (otherwise targets show <unknown>)
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl -n kube-system patch deploy metrics-server --type=json \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'

helm lint k8s/helm/aegis-platform
helm upgrade --install aegis k8s/helm/aegis-platform -n aegis --create-namespace \
  --set image.tag=dev --set ingress.enabled=false
kubectl -n aegis get pods -w                 # wait for 3/3 Running and READY 1/1
kubectl -n aegis port-forward svc/aegis-aegis-platform 8000:8000
curl localhost:8000/health
```

### 6B.2 Real cluster (for example EKS) with Ingress, TLS and GitOps

```bash
# 1. Ingress controller
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm install ingress-nginx ingress-nginx/ingress-nginx -n ingress-nginx --create-namespace
kubectl -n ingress-nginx get svc ingress-nginx-controller   # note EXTERNAL-IP / hostname -> DNS record

# 2. cert-manager + Let's Encrypt ClusterIssuer named "letsencrypt-prod"
helm repo add jetstack https://charts.jetstack.io
helm install cert-manager jetstack/cert-manager -n cert-manager --create-namespace --set crds.enabled=true
cat <<'EOF' | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata: { name: letsencrypt-prod }
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: you@example.com
    privateKeySecretRef: { name: letsencrypt-prod-key }
    solvers: [ { http01: { ingress: { ingressClassName: nginx } } } ]
EOF

# 3. ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl apply -f k8s/argocd/application.yaml
kubectl -n argocd get applications            # SYNC STATUS: Synced, HEALTH: Healthy
```

Change `ingress.hosts[0].host`, `ingress.tls[0].hosts` and `env.AEGIS_CORS_ORIGINS` in `values.yaml` to your real domain before syncing.

**From now on, deploying means a Git commit:** bump `image.tag` in `values.yaml`, merge the PR, and ArgoCD rolls it out. **Rolling back means `git revert`.**

### Missing pieces worth adding (and naming in interviews)

- `PodDisruptionBudget` (`minAvailable: 2`) so node drains never take all pods down.
- `NetworkPolicy` allowing traffic only from the ingress controller and Prometheus.
- Separate `values-staging.yaml` / `values-prod.yaml` and an ArgoCD Application per environment.
- A `ServiceMonitor` (Prometheus Operator) so Prometheus discovers the pods automatically.

---

## Phase 6: Option C: AWS ECS Fargate with Terraform

`terraform/` currently defines **an ECS cluster, a task definition and a budget alarm. It is not deployable on its own.** Be honest about this in interviews and describe what is missing:

| Missing resource | Why it is needed |
| :--- | :--- |
| `aws_ecs_service` | A task definition alone runs nothing; the *service* keeps N tasks running and registers them with the load balancer |
| `aws_iam_role` (task **execution** role with `AmazonECSTaskExecutionRolePolicy`) | Fargate needs it to pull the image and write to CloudWatch. Without it, tasks fail with `ResourceInitializationError` |
| `aws_cloudwatch_log_group "/ecs/aegis-production"` | The `awslogs` driver fails if the log group does not exist |
| VPC, subnets, security groups, ALB, target group (health check `/health`), listener with an ACM certificate | Networking and public HTTPS entry |
| ECR repository (or a GHCR pull secret in Secrets Manager) | The task definition points at a placeholder account `123456789012` and `:latest` |
| Remote state (`backend "s3"` + DynamoDB lock table) | Local `terraform.tfstate` cannot be shared by a team and has no locking |

Also note: `monthly_budget_usd = 5`. One always-on Fargate task with 0.5 vCPU / 1 GB costs about **$18/month** before the ALB (about $16/month), so the budget alarm **will fire**. That is fine for a demo (the alarm only sends email) but shows why cost estimation is part of design.

Workflow when complete:

```bash
cd terraform
terraform init          # downloads providers, configures backend
terraform fmt -check && terraform validate
terraform plan -out tfplan     # review exactly what will change (in CI, posted on the PR)
terraform apply tfplan
terraform destroy              # tear down the demo to stop billing
```

---

## Phase 7: Configuration and secrets

| Setting | Where it is read | Example |
| :--- | :--- | :--- |
| `AEGIS_CORS_ORIGINS` | `src/api/main.py` | `https://aegis.yourdomain.com` (comma-separated; default `http://localhost:8000`). Credentials are always disabled |
| `WEB_CONCURRENCY` | `Dockerfile` CMD | Gunicorn workers. Rule of thumb: `2 x vCPU` for I/O-bound apps; keep it small here because state is per-process |
| `PORT` | `Dockerfile` CMD | `8000` |

**Secrets rules used in companies:**

1. Never in Git, never baked into the image, never printed in logs.
2. Local: `.env` (git-ignored). VM: `.env` with `chmod 600`. Kubernetes: `Secret` objects, ideally synced from AWS Secrets Manager or Vault by **External Secrets Operator**. ECS: `secrets` in the task definition pointing to Secrets Manager or SSM.
3. CI: GitHub Actions **Secrets** (or OIDC federation to AWS, so no static keys exist at all).
4. Rotate anything that leaked. Removing it from Git history is not enough.

> The local `docker/docker-compose.yml` uses `password` / `admin` credentials. That is acceptable **only** on a laptop. The production compose file reads them from `.env`.

---

## Phase 8: Observability

The **three pillars** are metrics, logs and traces, plus **alerts** on top.

### Metrics (already implemented)

`/metrics` exposes:

- `aegis_http_requests_total{method, endpoint, status_code}`
- `aegis_http_request_duration_seconds_bucket{endpoint, le}`

Useful **PromQL** for Grafana panels and alerts:

```promql
# Requests per second per endpoint
sum by (endpoint) (rate(aegis_http_requests_total[5m]))

# Error rate (5xx) as a percentage
100 * sum(rate(aegis_http_requests_total{status_code=~"5.."}[5m]))
    / sum(rate(aegis_http_requests_total[5m]))

# p95 latency per endpoint
histogram_quantile(0.95, sum by (le, endpoint) (rate(aegis_http_request_duration_seconds_bucket[5m])))
```

**The golden signals** (Google SRE book) are latency, traffic, errors and saturation (CPU/memory). Alert on **symptoms users feel** (error rate > 1% for 5 min, p95 > 500 ms) rather than causes (CPU 80%).

> **Bug fixed in this project:** the middleware labelled metrics with the raw URL (`request.url.path`). Every random 404 path from a scanner (`/wp-admin`, `/.env`, ...) created a **new time series** forever. This is the classic *high-cardinality* problem that can take Prometheus down. Now the route template is used, and unknown paths become `endpoint="unmatched"`.

### Logs

- Gunicorn writes access logs to stdout (`--access-logfile -`). In containers, **always log to stdout/stderr** and let the platform collect them (CloudWatch, Loki, ELK).
- Next step: structured JSON logs with a request ID so one request can be followed across services.

### Traces

`src/observability/otel_instrumentation.py` sets up OpenTelemetry with a **console** exporter, and it is not wired into the API. For production, export OTLP to Jaeger, Tempo or Datadog and add `opentelemetry-instrumentation-fastapi`.

### SLO example (for interviews)

> *"Availability SLO 99.5% over 30 days means an error budget of about 3.6 hours. If we burn the budget fast, we freeze feature deploys and work on reliability."*

---

## Phase 9: Releases and rollbacks

| Strategy | How | Used when |
| :--- | :--- | :--- |
| **Rolling update** (Kubernetes default) | New pods start, become *ready*, then old pods are terminated | Most deploys |
| **Blue/Green** | Two full environments; switch the load balancer at once | Risky database or infra changes; instant rollback |
| **Canary** | 5%, then 25%, then 100% of traffic, watching error rate and latency at each step (Argo Rollouts, Flagger) | High-traffic services |
| **Feature flags** | Code is deployed but switched off; turn it on per user or percentage | Decouple deploy from release |

**Zero-downtime ingredients already in this repo:** readiness probe (no traffic to unready pods), `terminationGracePeriodSeconds: 40` > gunicorn `--graceful-timeout 30` (in-flight requests finish), at least 3 replicas, `exec` so `SIGTERM` reaches gunicorn.

**Rollback commands:**

```bash
helm -n aegis history aegis && helm -n aegis rollback aegis <revision>   # Helm
git revert <bad-commit> && git push                                      # GitOps (ArgoCD syncs it)
kubectl -n aegis rollout undo deploy/aegis-aegis-platform                 # emergency; ArgoCD self-heal reverts it unless Git is fixed too
IMAGE_TAG=<old-sha> docker compose -f docker-compose.prod.yml up -d api   # VM
```

**Database migrations** (when Postgres is used for real): use the expand-and-contract pattern. Add the new column, deploy code that writes both, backfill, switch reads, drop the old column. Each step stays backward compatible so a rollback never breaks.

---

## Phase 10: Operating in production

1. **On-call and alerts:** alerts route to PagerDuty or Opsgenie; each alert links to a runbook (this project's RAG search indexes runbooks for exactly this reason).
2. **Incident flow:** detect, triage (severity P1 to P4), mitigate first (rollback or scale out), *then* find the root cause, communicate on a status page.
3. **Blameless postmortem:** timeline, impact, root cause, what went well, action items with owners. Example: the metric-cardinality bug in Phase 8 would get the action item *"lint rule: no raw paths in metric labels"*.
4. **Cost:** right-size requests and limits from real usage (`kubectl top pods`), autoscale, budget alarms (`terraform/budget_alarm.tf`), tear down demo environments.
5. **Security hygiene:** Dependabot or Renovate for dependency updates, image scanning (Trivy in CI), least-privilege IAM, TLS everywhere, periodic secret rotation.

---

## Troubleshooting catalog

Format: **Symptom**, then **Cause**, then **Fix**. Entries marked ✅ were reproduced on this repository.

### Python / application errors

| # | Symptom | Cause | Fix |
| :--- | :--- | :--- | :--- |
| 1 | `ModuleNotFoundError: No module named 'src'` | Running from inside `src/` or a script directory, so the repo root is not on `sys.path` | Run from the repo root: `uvicorn src.api.main:app`. Pytest already sets `pythonpath = ["."]` in `pyproject.toml` |
| 2 | `ModuleNotFoundError: No module named 'fastapi'` (or another package) | venv not activated, or dependencies installed into a different Python | `which python` / `where python`, activate `.venv`, `pip install -r requirements.txt` |
| 3 ✅ | `requests.exceptions.ProxyError ... openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken` in `test_token_aware_chunking` | **tiktoken downloads its tokenizer file at runtime** on first use. Restricted-egress networks (corporate proxies, private subnets) block it | Pre-download during the image build or CI (`python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"`) with `TIKTOKEN_CACHE_DIR` set to a directory shipped with the app, or allow the host in the egress policy |
| 4 | `422 Unprocessable Entity` | Request body does not match the Pydantic model (missing field, wrong type) | Read the `detail` array in the response; it names the exact field. Check `/docs` for the schema |
| 5 | `405 Method Not Allowed` | Using `GET` on a `POST` endpoint (all `/v1/...` routes are POST) | Use `curl -X POST` |
| 6 | `/v1/rag/topology` returns 422 `service_name field required` when sending JSON | The endpoint reads `service_name` from the **query string** | `POST /v1/rag/topology?service_name=api-gateway` |
| 7 ✅ | `/v1/telemetry/ingest` returns `NORMAL` even for `latency_ms: 999999` | The anomaly engine was never fitted, so each value was compared with itself (z = 0) | **Fixed:** rolling per-service baseline (`TELEMETRY_WARMUP_EVENTS = 20`); the response reports `WARMING_UP` until it is ready, and anomalous events never enter the baseline |
| 8 ✅ | RCA report lists error logs and commits from **other** services | Filter used `service == X OR level == ERROR`; untagged commit fallback used substring matching | **Fixed:** logs must belong to the service and be ERROR/CRITICAL; commits compared exactly |
| 9 | `[CRITICAL] WORKER TIMEOUT (pid:...)` in gunicorn logs | A request ran longer than `--timeout 60` (for example a heavy eval endpoint), so gunicorn killed the worker | Make long jobs asynchronous (queue + worker, return a job ID), or raise `--timeout` for that deployment |
| 10 | `[ERROR] Worker (pid:7) was sent SIGTERM!` on shutdown | Normal gunicorn message during graceful shutdown | Nothing to fix; it appears after `Application shutdown complete` |
| 11 | Browser console: `CORS policy: No 'Access-Control-Allow-Origin'` | Front-end origin not in `AEGIS_CORS_ORIGINS` | Add the exact origin (scheme + host + port) to `AEGIS_CORS_ORIGINS`. The API never sends credentialed CORS responses |
| 12 | Different pods return different incident IDs / HITL approval "lost" | State is **in memory per process**: `RootCauseAnalysisAgent.incident_counter`, LangGraph `MemorySaver`, retriever index | Move shared state to Postgres or Redis (for example LangGraph `PostgresSaver`, DB sequences for IDs). Until then, scaling replicas changes behaviour; see INTERVIEW_PREP "Known limitations" |

### Lint / CI errors

| # | Symptom | Cause | Fix |
| :--- | :--- | :--- | :--- |
| 13 ✅ | CI fails at `ruff check .` with `E501 Line too long` / `I001` in `scripts/*.py`, and `ruff format --check` says `4 files would be reformatted` | Files were committed without running the formatter; CI on `main` was **red** | **Fixed** with `ruff check --fix . && ruff format .`. Prevent it with a pre-commit hook: `pip install pre-commit`, then add a ruff hook |
| 14 ✅ | Running tests modifies `data/analytics/daily_service_metrics.parquet` | ETL tests write to a tracked file | `git checkout data/` before committing; long-term, write to `tmp_path` |
| 15 | `Error response from daemon: denied` when pushing to GHCR | Workflow lacks `packages: write`, or the package is linked to another repo | Keep `permissions: packages: write` on the job; in the package settings, grant this repo access |
| 16a ✅ | Trivy fails with HIGH CVEs in `urllib3`, `msgpack`, `setuptools` that `requirements-prod.txt` never installs | The CVEs are in libraries **vendored inside pip** (`pip/_vendor`), which newer Trivy versions scan | Remove pip from the runtime image (the service never installs packages at runtime); see the `Dockerfile`. Find a package's origin with `docker run --rm --entrypoint sh <img> -c 'grep -r <pkg> /opt/venv/lib/python3.12/site-packages/*/_vendor/vendor.txt'` |
| 16b ✅ | SonarCloud quality gate fails (Security Rating C): *"Use full commit SHA hash for this dependency"* on `uses:` lines | Actions referenced by a movable tag (`@v3`) can be silently re-pointed to malicious code (a real supply-chain attack pattern) | Pin every action to its full commit SHA and keep the version as a comment: `uses: docker/login-action@<40-char-sha> # v3.7.0`. Look up SHAs with `git ls-remote https://github.com/<owner>/<action> 'refs/tags/v3.7.0^{}'`; let Dependabot keep them updated |
| 16 | Trivy step fails with a CVE list | A base-image or library CVE with a fix available | Rebuild (newer `python:3.12-slim` patch), bump the library version, or document an accepted risk in `.trivyignore` with an expiry date |

### Docker errors

| # | Symptom | Cause | Fix |
| :--- | :--- | :--- | :--- |
| 17 | `failed to connect to the docker API ... docker.sock` / `error during connect` | Docker daemon / Docker Desktop not running | Start Docker Desktop (Windows: `scripts/fix_docker_desktop.ps1` resets stuck processes) or `sudo systemctl start docker` |
| 18 | `Bind for 0.0.0.0:8000 failed: port is already allocated` | Another process uses the port | `docker ps`, `lsof -i :8000` / `netstat -ano \| findstr :8000`; stop it or map another port `-p 8080:8000` |
| 19 ✅ | `PermissionError: [Errno 13] Permission denied: 'data/analytics'` | Read-only root FS + tmpfs owned by root, while the app runs as UID 10001 | `--tmpfs /app/data:uid=10001,gid=10001` (Docker) / `fsGroup: 10001` + `emptyDir` (Kubernetes) |
| 20 ✅ | `SSL: CERTIFICATE_VERIFY_FAILED ... self-signed certificate in certificate chain` during `pip install` in `docker build` | Corporate TLS-inspecting proxy; the build container does not trust the proxy CA | Mount the CA as a BuildKit secret: `RUN --mount=type=secret,id=ca,target=/ca.crt PIP_CERT=/ca.crt pip install ...` and `docker build --secret id=ca,src=corp-ca.crt`. Never use `--trusted-host` / disable verification |
| 21 ✅ | Prometheus target `host.docker.internal:8000` is **DOWN** on Linux | That hostname only exists by default on Docker Desktop (Windows/macOS) | **Fixed** in `docker/docker-compose.yml`: `extra_hosts: ["host.docker.internal:host-gateway"]`. In the prod compose, Prometheus scrapes `api:8000` over the compose network |
| 22 | Container `Exited (137)` | Killed by the OOM killer (137 = 128 + SIGKILL) | Raise the memory limit, reduce `WEB_CONCURRENCY` (each worker loads the app), check `docker stats` |
| 23 | Image is 5+ GB, slow to push and pull | Built from `requirements.txt` (torch, CUDA wheels) | Use `requirements-prod.txt` (as the Dockerfile does) |

### Kubernetes errors

| # | Symptom | Cause | Fix |
| :--- | :--- | :--- | :--- |
| 24 | Pod `ImagePullBackOff` / `ErrImagePull` | Wrong image name or tag, or a **private GHCR package** without credentials. Also: image repository names must be lowercase | `kubectl describe pod <pod>` (Events). Make the package public, or `kubectl create secret docker-registry ghcr --docker-server=ghcr.io --docker-username=<user> --docker-password=<PAT with read:packages>` and set `imagePullSecrets: [{name: ghcr}]` |
| 25 | Pod `CrashLoopBackOff` | App exits at startup (import error, bad env var, permission error) | `kubectl logs <pod> --previous` shows the crash of the last attempt |
| 26 | Pod `Running` but `READY 0/1`, Ingress returns **502/503** | Readiness probe failing, so the pod is not in Service endpoints | `kubectl describe pod` (probe failures), `kubectl get endpoints <svc>`; check the probe path and port |
| 27 | `OOMKilled` in `kubectl describe pod` | Container exceeded `resources.limits.memory` | Raise the limit or lower `WEB_CONCURRENCY`; measure with `kubectl top pod` |
| 28 | Pod `Pending`, event `Insufficient cpu` | Requests exceed free node capacity | Lower `resources.requests`, add nodes, or enable the cluster autoscaler |
| 28b ✅ | SonarCloud: *"Specify a storage limit for this container"*; or in a cluster, pod `Evicted` with `The node was low on resource: ephemeral-storage` | No `ephemeral-storage` limit, so one pod's logs or temp files can fill the node disk and get **every** pod on that node evicted | Set `resources.requests/limits.ephemeral-storage` (256Mi / 1Gi in `values.yaml`) and `emptyDir.sizeLimit` on scratch volumes. Now only the offending pod is evicted |
| 29 | `kubectl get hpa` shows `<unknown>/75%` | **metrics-server** not installed (or pods have no CPU requests) | Install metrics-server (Phase 6B.1); keep `resources.requests` set |
| 30 ✅ | HTTPS never works; `kubectl get certificate` shows nothing | The Ingress had cert-manager annotations but **no `tls:` block**, so cert-manager had nothing to issue | **Fixed:** `ingress.tls` in `values.yaml` and the template |
| 31 | Certificate stuck `READY False` | DNS does not point at the ingress yet, or port 80 is blocked (HTTP-01 challenge) | `kubectl describe challenge -A`; fix DNS and firewall, then wait |
| 32 ✅ | ArgoCD app `ComparisonError: repository not found` | `repoURL` pointed to `UmaNagallaa/...` instead of the real `Umanagalla27/...` | **Fixed** in `k8s/argocd/application.yaml` (also `targetRevision: main` instead of `HEAD`) |
| 33 | ArgoCD shows `OutOfSync` right after a manual `kubectl edit` | Self-heal reverts manual changes, by design | Change Git, not the cluster |
| 34 | `Error: container has runAsNonRoot and image will run as root` | Image without `USER` and pod with `runAsNonRoot: true` | The Dockerfile sets `USER aegis` (UID 10001); keep `runAsUser: 10001` aligned |

### Terraform / AWS errors

| # | Symptom | Cause | Fix |
| :--- | :--- | :--- | :--- |
| 35 | `Error: No valid credential sources found` | AWS credentials not configured | `aws configure` / SSO login; in CI use OIDC (`aws-actions/configure-aws-credentials`) |
| 36 | ECS task `STOPPED (ResourceInitializationError: unable to pull secrets or registry auth)` | Missing task execution role or no network path to ECR (private subnet without NAT or VPC endpoints) | Add the execution role, plus a NAT gateway or ECR/S3/Logs VPC endpoints |
| 37 | `ClientException: ... log group does not exist` | `awslogs-group` not created | Add `aws_cloudwatch_log_group` |
| 38 | `Error acquiring the state lock` | Another `apply` running, or a crashed run left the lock | Wait; if certain it is stale: `terraform force-unlock <id>` |
| 39 | Budget alarm emails right after deploy | `$5` budget is below Fargate + ALB cost | Expected for a demo; raise the budget or `terraform destroy` after recording a demo |

### Debugging method (what interviewers want to hear)

1. **Reproduce** (exact request, exact version and SHA).
2. **Observe:** logs (`kubectl logs`, `docker logs`), events (`kubectl describe`), metrics (error rate, latency).
3. **Isolate:** is it the code, the config, the infrastructure, or a dependency? Compare with the last good version.
4. **Mitigate first:** roll back or scale out, so users stop hurting.
5. **Fix the root cause** plus a **regression test**, deploy through the normal pipeline.
6. **Postmortem** with action items.

---

## Production-readiness checklist

- [x] Dockerfile: multi-stage, slim, non-root, healthcheck, graceful shutdown
- [x] CI: lint, tests, eval gates, image build, smoke test, vulnerability scan, push by SHA
- [x] Helm: probes (startup/readiness/liveness), resources, HPA, non-root + read-only security context, TLS Ingress
- [x] GitOps: ArgoCD application with automated sync and self-heal
- [x] Metrics endpoint with bounded label cardinality
- [x] CORS configured from the environment
- [ ] **Authentication/authorization** on `/v1/*` (API key or OAuth2/JWT); today anyone who can reach the API can trigger rollbacks and heavy eval jobs
- [ ] Rate limiting (at the ingress or with `slowapi`)
- [ ] Persistent shared state (Postgres/Redis) for incidents, HITL checkpoints and the retriever index
- [ ] Structured JSON logs with request IDs, plus OTLP tracing
- [ ] Alert rules (error rate, p95 latency) with runbook links
- [ ] Complete Terraform (VPC, ALB, ECS service, IAM, logs, remote state) or EKS module
- [ ] PodDisruptionBudget, NetworkPolicy, per-environment values files
- [ ] Pinned dependency lock file (`pip-compile` / `uv lock`) for reproducible builds
