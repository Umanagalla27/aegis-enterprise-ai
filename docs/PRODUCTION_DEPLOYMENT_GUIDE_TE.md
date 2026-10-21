# Aegis Enterprise AI: Production Deployment Guide (తెలుగు)

ఇది [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md) కి తెలుగు వివరణ. Commands, file names, technical terms (Docker, CI, Pod లాంటివి) English లోనే ఉంచాము. Interviews లో, companies లో అవే పదాలు వాడతారు. పూర్తి commands మరియు 39+ errors ఉన్న troubleshooting catalog కోసం English guide చూడండి.

Interview preparation కోసం: [INTERVIEW_PREP.md](INTERVIEW_PREP.md)

---

## విషయ సూచిక

- [Phase 0: Companies software ని ఎలా ship చేస్తాయి](#phase-0-companies-software-ని-ఎలా-ship-చేస్తాయి)
- [Phase 1: Local Development Setup](#phase-1-local-development-setup)
- [Phase 2: Git Workflow & Code Review](#phase-2-git-workflow--code-review)
- [Phase 3: Code Quality, Tests, Evaluation Gates](#phase-3-code-quality-tests-evaluation-gates)
- [Phase 4: Docker (Containerization)](#phase-4-docker-containerization)
- [Phase 5: CI/CD Pipeline](#phase-5-cicd-pipeline)
- [Phase 6: Deployment: 3 Options](#phase-6-deployment-3-options)
- [Phase 7: Configuration & Secrets](#phase-7-configuration--secrets)
- [Phase 8: Observability (Monitoring)](#phase-8-observability-monitoring)
- [Phase 9: Releases & Rollbacks](#phase-9-releases--rollbacks)
- [Phase 10: Production లో Operate చేయడం](#phase-10-production-లో-operate-చేయడం)
- [Troubleshooting: ముఖ్యమైన Errors](#troubleshooting-ముఖ్యమైన-errors)
- [Production-Readiness Checklist](#production-readiness-checklist)

---

## Phase 0: Companies software ని ఎలా ship చేస్తాయి

```
Requirement → Design → Code (feature branch) → Pull Request + Review
→ CI (lint, test, build, scan) → Artifact (Docker image)
→ Staging → Production → Monitoring → Incident → Postmortem
```

### ముఖ్యమైన concepts

| Concept | అర్థం |
| :--- | :--- |
| **Environments** | `dev` (మీ laptop), `staging` (production కి copy), `prod` (నిజమైన users) |
| **Artifact** | Deploy చేసే వస్తువు, ఇక్కడ **Docker image**. ఒక్కసారే build చేసి, అదే image ని అన్ని environments కి పంపుతారు |
| **Immutable tag** | Image కి `latest` కాకుండా **git commit SHA** tag పెడతారు (ఉదా: `:a1b2c3d`). అప్పుడు ఏ code నడుస్తోందో exact గా తెలుస్తుంది, rollback కూడా సులభం |
| **IaC (Infrastructure as Code)** | Servers, networks ని code files లో (Terraform) రాస్తారు, code లాగానే review చేస్తారు |
| **GitOps** | Git లో ఏది ఉంటే అదే cluster లో నడుస్తుంది. ArgoCD అనే tool sync చేస్తుంది |
| **12-Factor config** | Settings ని code లో hard-code చేయరు, **environment variables** ద్వారా ఇస్తారు |

### Companies లో checks ఎక్కడ run అవుతాయి

```
Laptop → CI (shared runners) → DEV → QA/TEST → STAGING → PRODUCTION
```

- **Local:** fast feedback కోసం మాత్రమే
- **CI:** అసలైన gate. **Branch protection** వల్ల ఎవరూ skip చేయలేరు
- **Same image** (same commit SHA) అన్ని environments గుండా వెళ్తుంది. Config మాత్రమే మారుతుంది

**Interview line:**
> "ప్రతి commit కి CI లో ఒక immutable image build చేసి, scan చేసి, registry కి push చేస్తాం. అదే image ని staging నుండి prod కి promote చేస్తాం. Environments మధ్య config మాత్రమే మారుతుంది, code మారదు."

---

## Phase 1: Local Development Setup

### 1.1 కావాల్సిన tools

| Tool | Check చేసే command |
| :--- | :--- |
| Python 3.12 | `python --version` |
| Git | `git --version` |
| Docker Desktop | `docker version` (**Server** section కనిపించాలి) |

### 1.2 Clone చేసి virtual environment తయారు చేయండి

```bash
git clone https://github.com/Umanagalla27/aegis-enterprise-ai.git
cd aegis-enterprise-ai
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell
# source .venv/bin/activate         # Linux / macOS
pip install -r requirements.txt
```

**venv ఎందుకు?** ఈ project packages వేరే projects తో కలవకుండా వేరుగా ఉంచుతుంది. "నా machine లో పని చేస్తుంది, మీ దాంట్లో పని చేయదు" అనే problems ఎక్కువగా global installs వల్లే వస్తాయి.

### 1.3 Backing services start చేయండి

```bash
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml ps
```

ఇది Postgres, Redis, Prometheus, Grafana ని start చేస్తుంది. Ports కావాలనే వేరుగా పెట్టారు (5435, 6382, 9091, 3001), వేరే projects తో clash అవ్వకుండా.

### 1.4 API run చేయండి

```bash
uvicorn src.api.main:app --reload --port 8000
```

⚠️ ఎప్పుడూ **repo root folder** నుండే run చేయండి. లేకపోతే `ModuleNotFoundError: No module named 'src'` వస్తుంది.

Browser లో open చేయాల్సినవి:
- `http://localhost:8000`: Dashboard
- `http://localhost:8000/docs`: Swagger UI (అన్ని APIs ని ఇక్కడే test చేయవచ్చు)
- `http://localhost:8000/metrics`: Prometheus metrics
- `http://localhost:9091`: Prometheus, `http://localhost:3001`: Grafana (admin/admin, local లో మాత్రమే)

### 1.5 Anomaly detection warm-up

`/v1/telemetry/ingest` ప్రతి service కి వేరుగా baseline నేర్చుకుంటుంది:
- మొదటి **20 events** కి `"status": "WARMING_UP"` వస్తుంది (ఇంకా నేర్చుకుంటోంది)
- 21వ event నుండి `"status": "SCORED"`, అంటే ఇప్పుడు spike వస్తే `CRITICAL` అని చూపిస్తుంది
- Anomaly events baseline లోకి వెళ్ళవు, కాబట్టి ఒక spike baseline ని పాడు చేయలేదు

---

## Phase 2: Git Workflow & Code Review

```bash
git checkout main && git pull
git checkout -b feat/my-feature          # ప్రతి change కి కొత్త branch
# ... code మార్చండి ...
ruff check . && ruff format --check . && pytest -q   # push ముందు checks
git add -p                                           # changes ని జాగ్రత్తగా stage చేయండి
git commit -m "fix(api): short description"
git push -u origin feat/my-feature
# GitHub లో Pull Request open → CI → Review → Merge
```

| Practice | ఎందుకు |
| :--- | :--- |
| **Branch protection** (Settings → Branches) | Test కాని code ఎవరూ `main` లోకి push చేయలేరు |
| **Conventional commits** (`feat:`, `fix:`, `docs:`) | History చదవడం సులభం |
| **Small PRs** | Review సులభం, rollback సులభం |
| **CODEOWNERS** | ప్రతి folder కి సరైన reviewer ని auto-request చేస్తుంది |
| **Secrets commit చేయవద్దు** | `.env`, `*.tfvars`, `*.tfstate` అన్నీ `.gitignore` లో ఉన్నాయి |

### PR ముందు checklist

1. `main` తో update చేయండి (`git merge main`)
2. `ruff check . --fix` మరియు `ruff format .`
3. `pytest -q` మరియు `python eval/run_aiops_eval.py`
4. App ని run చేసి మార్చిన endpoints ని manual గా test చేయండి
5. Dockerfile / dependencies మారిస్తే: `docker build` + Trivy scan
6. Kubernetes files మారిస్తే: `helm lint`
7. Security: SonarLint IDE extension, actions SHA pinning, secrets లేవని check చేయండి
8. `git diff main` తో మీ changes ని మీరే review చేయండి
9. Commit + push
10. మంచి PR description రాయండి (ఏమి, ఎందుకు, ఎలా test చేశారు, rollback ఎలా)

---

## Phase 3: Code Quality, Tests, Evaluation Gates

```bash
ruff check .                     # Lint: unused imports, తప్పుడు syntax, import order
ruff format --check .            # Formatting (ఏ file అయినా మారితే CI fail అవుతుంది)
pytest -q                        # అన్ని tests
python eval/run_aiops_eval.py    # 20-fault chaos test (>= 95% రావాలి)
```

| Test file | ఏమి check చేస్తుంది |
| :--- | :--- |
| `tests/test_phase2.py` | Transformer, chunking, BM25 + RRF retrieval, Graph RAG |
| `tests/test_phase3.py` | LangGraph workflow, HITL, PII redaction, injection defense |
| `tests/test_phase4.py` | Kafka partitioning, DLQ, aggregator, dbt, Airflow SLA gate |
| `tests/test_phase5.py` | Anomaly engine, RCA agent, FastAPI, Prometheus metrics |
| `tests/test_regressions.py` | ఇంతకుముందు fix చేసిన bugs మళ్ళీ రాకుండా |
| `eval/test_eval_gates.py` | Faithfulness >= 0.85, recall >= 0.80, agent accuracy >= 90% |

**Testing pyramid (companies వాడేది):**
- చాలా ఎక్కువ **unit tests** (fast)
- కొన్ని **integration tests** (FastAPI `TestClient`)
- కొద్దిగా **end-to-end tests** (CI లో smoke test ఒకటి)

**Regression test rule:** ప్రతి bug fix తో ఒక test రాయాలి. ఆ test **fix ముందు fail అవ్వాలి, fix తర్వాత pass అవ్వాలి**.

⚠️ Tests run చేసినప్పుడు `data/analytics/daily_service_metrics.parquet` file మారుతుంది. Commit ముందు `git checkout data/` run చేయండి.

---

## Phase 4: Docker (Containerization)

### Build & Run

```bash
docker build -t aegis-api:local .
docker run --rm -p 8000:8000 --read-only --tmpfs /tmp \
  --tmpfs /app/data:uid=10001,gid=10001 \
  -e AEGIS_CORS_ORIGINS=http://localhost:8000 \
  aegis-api:local
curl localhost:8000/health
```

### Dockerfile లో ప్రతి నిర్ణయం ఎందుకు?

| నిర్ణయం | ఎందుకు |
| :--- | :--- |
| **Multi-stage build** | Build tools final image లోకి రావు, image చిన్నగా, safe గా ఉంటుంది |
| **`python:3.12-slim`** | CI లో ఉన్న Python version, అనవసరమైన ~800 MB OS packages ఉండవు |
| **`requirements-prod.txt`** | API కి torch అవసరం లేదు. దాన్ని తీసేయడం వల్ల image **~233 MB** మాత్రమే (లేకపోతే కొన్ని GB అయ్యేది) |
| **Non-root user (UID 10001)** | Hacker app లోకి వచ్చినా root access ఉండదు |
| **Code root-owned** | App user code ని చదవగలడు, మార్చలేడు |
| **pip తీసేశాం** | pip లోపల bundle అయిన libraries లో 4 HIGH vulnerabilities ఉన్నాయి. Runtime లో pip అవసరం లేదు |
| **`PYTHONUNBUFFERED=1`** | Logs వెంటనే `docker logs` లో కనిపిస్తాయి |
| **`HEALTHCHECK`** | `/health` respond చేయకపోతే Docker `unhealthy` అని mark చేస్తుంది |
| **gunicorn + uvicorn** | Worker crash అయితే gunicorn మళ్ళీ start చేస్తుంది, `SIGTERM` వస్తే graceful shutdown చేస్తుంది |
| **`exec` in CMD** | Server PID 1 అవుతుంది, `SIGTERM` నేరుగా అందుతుంది |
| **Read-only filesystem** | Hacker disk మీద code మార్చలేడు. `/tmp`, `/app/data` మాత్రమే writable |

### నిజంగా వచ్చిన error

Read-only mode లో `/v1/airflow/run-etl` crash అయ్యింది: `PermissionError: [Errno 13] Permission denied: 'data/analytics'`.
- **Cause:** tmpfs folder root కి చెందినది, కానీ app UID 10001 తో నడుస్తుంది
- **Fix:** Docker లో `--tmpfs /app/data:uid=10001,gid=10001`. Kubernetes లో `fsGroup: 10001` + `emptyDir` (Helm chart లో ఇప్పటికే ఉంది)

### ఉపయోగకరమైన Docker commands

```bash
docker images aegis-api                  # image size
docker logs -f <container>               # logs
docker exec -it <container> sh           # container లోపలికి
docker stats                             # live CPU / memory
```

---

## Phase 5: CI/CD Pipeline

File: `.github/workflows/ci.yml`. `main` కి push, ప్రతి Pull Request, manual (`workflow_dispatch`) మీద run అవుతుంది.

```
Job 1: lint-and-test                Job 2: build-and-push-image (Job 1 pass అయ్యాక)
├─ Postgres + Redis containers     ├─ Docker image build (cache తో)
├─ ruff check + format             ├─ Smoke test (read-only, /health)
├─ pytest (అన్ని phases)           ├─ Trivy security scan
├─ RAGAS / agent eval gates        ├─ GHCR login (PR లో కాదు)
└─ 20-fault chaos test             └─ Push :<sha> (main లో :latest కూడా)
```

| Stage | ఎందుకు |
| :--- | :--- |
| **ముందు lint** | చవకైన check ముందు, CI time ఆదా |
| **Service containers** | CI లో నిజమైన Postgres / Redis, mocks కాదు |
| **`concurrency: cancel-in-progress`** | కొత్త push వస్తే పాత run cancel అవుతుంది |
| **Smoke test** | Unit tests pass అయినా container start అవుతుందని గ్యారంటీ లేదు (missing dependency, తప్పు CMD, permissions) |
| **Trivy scan** | తెలిసిన vulnerabilities ఉన్న packages prod కి వెళ్ళకుండా ఆపుతుంది |
| **PR లో push చేయదు** | Forks నుండి వచ్చే PRs కి registry credentials ఇవ్వకూడదు |
| **Actions SHA pinning** | `@v3` tag ని attacker మార్చగలడు, commit SHA ని మార్చలేడు |
| **`permissions: contents: read`** | Token కి కనీస permissions మాత్రమే |
| **`persist-credentials: false`** | Git credentials build machine మీద మిగిలిపోవు |

**Merge తర్వాత మీరు ఒక్కసారి చేయాల్సింది:** GitHub profile → **Packages** → `aegis-enterprise-ai` → **Package settings** → **Public**. లేకపోతే మీ server login లేకుండా image download చేయలేదు.

**Continuous Deployment:** Image push అయ్యాక, CI ఒక PR తో `values.yaml` లో `image.tag` మారుస్తుంది (లేదా ArgoCD Image Updater చేస్తుంది). PR merge అయ్యాక ArgoCD deploy చేస్తుంది. ప్రతి production change ఒక reviewed Git commit అవుతుంది.

---

## Phase 6: Deployment: 3 Options

### 🅰️ Option A: ఒక VM + Docker Compose + HTTPS (Recommend చేసేది)

**ఎందుకు?** చవక, నిజమైన domain, నిజమైన HTTPS, live link resume లో పెట్టవచ్చు. Kubernetes వాడే image నే వాడుతుంది.

Files: `docker/docker-compose.prod.yml`, `docker/Caddyfile`, `docker/prometheus.prod.yml`, `docker/.env.example`

```
Internet ──443──> Caddy (auto Let's Encrypt HTTPS) ──> api:8000 ──> Prometheus ← Grafana (127.0.0.1 మాత్రమే)
```

**Steps:**

1. **VM create చేయండి:** Ubuntu 24.04, 2 vCPU / 2 GB RAM (AWS `t3.small`, Hetzner CX22, Oracle free tier)
2. **Firewall:** 22 (SSH, మీ IP నుండి మాత్రమే), 80, 443 open చేయండి. 8000, 9090, 3001 **open చేయవద్దు**
3. **DNS:** `aegis.yourdomain.com` → VM IP కి `A` record (DuckDNS free subdomain కూడా సరిపోతుంది)
4. **Docker install:**
   ```bash
   ssh ubuntu@<vm-ip>
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER && exit      # మళ్ళీ login అవ్వండి
   ```
5. **Configure:**
   ```bash
   git clone https://github.com/Umanagalla27/aegis-enterprise-ai.git
   cd aegis-enterprise-ai/docker
   cp .env.example .env && nano .env      # DOMAIN, AEGIS_CORS_ORIGINS, GRAFANA_ADMIN_PASSWORD, IMAGE_TAG
   chmod 600 .env
   ```
6. **Start:**
   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env up -d
   docker compose -f docker-compose.prod.yml ps
   docker compose -f docker-compose.prod.yml logs -f caddy    # certificate issue అవ్వడం చూడండి
   ```
7. **Verify:** `curl https://aegis.yourdomain.com/health` run చేస్తే `HEALTHY` రావాలి. Grafana కోసం SSH tunnel: `ssh -L 3001:localhost:3001 ubuntu@<vm-ip>`, తర్వాత `http://localhost:3001`
8. **కొత్త version:** `.env` లో `IMAGE_TAG=<new sha>` మార్చి `docker compose ... pull api && docker compose ... up -d api`
9. **Rollback:** పాత SHA పెట్టి మళ్ళీ అదే command

### 🅱️ Option B: Kubernetes + Helm + ArgoCD (Companies ఎక్కువగా వాడేది)

**Files ఏమి చేస్తాయి:**

| File | పని |
| :--- | :--- |
| `templates/deployment.yaml` | Pods: image, env, probes, resources, non-root + read-only security, storage limits |
| `templates/service.yaml` | Pods ముందు stable internal IP మరియు DNS name |
| `templates/ingress.yaml` | బయటి నుండి HTTPS traffic లోపలికి (cert-manager కోసం `tls:` block తో) |
| `templates/hpa.yaml` | Load పెరిగితే 3 నుండి 10 pods వరకు auto-scale |
| `values.yaml` | అన్ని settings. ప్రతి environment కి వేరే values file పెట్టవచ్చు |
| `k8s/argocd/application.yaml` | ArgoCD `main` ని watch చేసి cluster ని sync చేస్తుంది |

**Probes (Interview లో తప్పకుండా అడుగుతారు):**

| Probe | Fail అయితే ఏమి జరుగుతుంది |
| :--- | :--- |
| **startupProbe** | App boot అవ్వడానికి 120 seconds వరకు time ఇస్తుంది, ఆ తర్వాతే మిగతా probes మొదలవుతాయి |
| **readinessProbe** | Pod కి **traffic ఆపేస్తుంది**, restart చేయదు |
| **livenessProbe** | 3 సార్లు fail అయితే container ని **restart** చేస్తుంది (deadlocks కోసం) |

⚠️ సాధారణ తప్పు: liveness probe లో database ని check చేయడం. DB కొంచెం slow అయితే అన్ని pods restart అవుతాయి, outage పెద్దది అవుతుంది.

**Free practice (kind తో మీ laptop లోనే):**

```bash
kind create cluster --name aegis
docker build -t ghcr.io/umanagalla27/aegis-enterprise-ai:dev .
kind load docker-image ghcr.io/umanagalla27/aegis-enterprise-ai:dev --name aegis
helm lint k8s/helm/aegis-platform
helm upgrade --install aegis k8s/helm/aegis-platform -n aegis --create-namespace \
  --set image.tag=dev --set ingress.enabled=false
kubectl -n aegis get pods -w
kubectl -n aegis port-forward svc/aegis-aegis-platform 8000:8000
curl localhost:8000/health
```

HPA పని చేయాలంటే **metrics-server** install చేయాలి (English guide లో commands ఉన్నాయి).

**Real cluster (EKS లాంటిది) కోసం:** ingress-nginx, cert-manager + Let's Encrypt ClusterIssuer, ArgoCD install చేసి `kubectl apply -f k8s/argocd/application.yaml`. పూర్తి commands English guide Phase 6B.2 లో ఉన్నాయి.

**GitOps లో deploy అంటే** `values.yaml` లో image tag మార్చి PR merge చేయడం. **Rollback అంటే** `git revert`.

**ఇంకా add చేయవచ్చు:** PodDisruptionBudget, NetworkPolicy, staging / prod కి వేరే values files, ServiceMonitor.

### 🅲 Option C: AWS ECS Fargate + Terraform

⚠️ **నిజాయితీగా చెప్పాలంటే, ఇది incomplete.** Cluster, task definition, budget alarm మాత్రమే ఉన్నాయి. ఇవి missing:

| Missing | ఎందుకు కావాలి |
| :--- | :--- |
| `aws_ecs_service` | ఇది లేకుండా ఏ task కూడా run అవ్వదు |
| IAM execution role | Image pull చేయడానికి, logs రాయడానికి |
| CloudWatch log group | లేకపోతే `awslogs` driver fail అవుతుంది |
| VPC, subnets, security groups, ALB, ACM certificate | Network మరియు HTTPS |
| ECR repository | Task definition లో placeholder account `123456789012` ఉంది |
| Remote state (S3 + DynamoDB) | Team తో share చేయడానికి, locking కోసం |

**Cost గమనిక:** Budget $5 గా ఉంది, కానీ ఒక Fargate task (~$18) + ALB (~$16) కలిపి నెలకు ~$34 అవుతుంది. కాబట్టి alarm తప్పకుండా వస్తుంది. Demo తర్వాత `terraform destroy` చేయండి.

```bash
cd terraform
terraform init
terraform fmt -check && terraform validate
terraform plan -out tfplan       # ఏమి మారుతుందో ముందే చూడండి
terraform apply tfplan
terraform destroy                # billing ఆపడానికి
```

---

## Phase 7: Configuration & Secrets

| Setting | ఎక్కడ చదువుతుంది | ఉదాహరణ |
| :--- | :--- | :--- |
| `AEGIS_CORS_ORIGINS` | `src/api/main.py` | `https://aegis.yourdomain.com` (comma తో వేరు చేయండి; default `http://localhost:8000`) |
| `WEB_CONCURRENCY` | `Dockerfile` CMD | gunicorn workers సంఖ్య |
| `PORT` | `Dockerfile` CMD | `8000` |

**Secrets rules (companies పాటించేవి):**
1. Git లో, image లో, logs లో **ఎప్పుడూ వద్దు**
2. Local లో `.env` (git-ignored). VM లో `.env` + `chmod 600`. Kubernetes లో **Secrets** (AWS Secrets Manager / Vault నుండి External Secrets Operator ద్వారా)
3. CI లో GitHub Secrets, లేదా OIDC (static keys అసలు ఉండవు)
4. Leak అయితే **rotate చేయండి**. Git history నుండి delete చేస్తే సరిపోదు

> Local `docker/docker-compose.yml` లో `password` / `admin` ఉన్నాయి. అది laptop లో మాత్రమే సరి. Production compose `.env` నుండి చదువుతుంది.

---

## Phase 8: Observability (Monitoring)

**3 pillars:** Metrics, Logs, Traces. వాటి పైన **Alerts**.

### Metrics

`/metrics` endpoint ఇవి ఇస్తుంది:
- `aegis_http_requests_total{method, endpoint, status_code}`
- `aegis_http_request_duration_seconds_bucket{endpoint, le}`

### Useful PromQL queries

```promql
# Endpoint కి requests per second
sum by (endpoint) (rate(aegis_http_requests_total[5m]))

# Error rate (5xx) %
100 * sum(rate(aegis_http_requests_total{status_code=~"5.."}[5m]))
    / sum(rate(aegis_http_requests_total[5m]))

# p95 latency
histogram_quantile(0.95, sum by (le, endpoint) (rate(aegis_http_request_duration_seconds_bucket[5m])))
```

**Golden Signals (Google SRE book):** Latency, Traffic, Errors, Saturation.

**Alert ఎప్పుడు?** Users కి నేరుగా కనిపించే symptoms మీద alert పెట్టండి (error rate > 1% 5 నిమిషాలు, p95 > 500ms). CPU 80% లాంటి causes మీద కాదు.

**Cardinality bug:** Raw URL ని label గా పెడితే ప్రతి random path (`/wp-admin`, `/.env`) కి కొత్త time series తయారవుతుంది, Prometheus memory అయిపోయి crash అవుతుంది. Fix: route template వాడండి, తెలియని paths కి `"unmatched"`.

### Logs
- Containers లో ఎప్పుడూ **stdout / stderr** కి log చేయండి. Platform (CloudWatch, Loki, ELK) collect చేస్తుంది
- తర్వాతి step: request ID తో structured JSON logs

### Traces
OpenTelemetry setup ఉంది కానీ console కి మాత్రమే, API కి connect చేయలేదు. Production లో Jaeger / Tempo కి OTLP export చేయాలి.

### SLO ఉదాహరణ (Interview కోసం)
> "30 రోజులకి 99.5% availability SLO అంటే ~3.6 hours error budget. Budget త్వరగా అయిపోతే feature deploys ఆపి reliability మీద పని చేస్తాం."

---

## Phase 9: Releases & Rollbacks

| Strategy | ఎలా | ఎప్పుడు వాడతారు |
| :--- | :--- | :--- |
| **Rolling update** | కొత్త pods ready అయ్యాకే పాతవి తీసేస్తారు | చాలా deploys (Kubernetes default) |
| **Blue/Green** | రెండు పూర్తి environments, load balancer ని ఒక్కసారిగా switch చేస్తారు | Risky changes, instant rollback |
| **Canary** | 5% → 25% → 100% traffic, ప్రతి step లో errors చూస్తూ | ఎక్కువ traffic ఉన్న services |
| **Feature flags** | Code deploy అయినా feature off లో ఉంటుంది | Deploy మరియు release ని వేరు చేయడానికి |

**Zero-downtime కోసం ఈ repo లో ఉన్నవి:**
- Readiness probe (ready కాని pods కి traffic రాదు)
- `terminationGracePeriodSeconds: 40` (gunicorn graceful timeout 30 కంటే ఎక్కువ, కాబట్టి నడుస్తున్న requests పూర్తవుతాయి)
- కనీసం 3 replicas
- `exec` వల్ల `SIGTERM` gunicorn కి చేరుతుంది

**Rollback commands:**

```bash
helm -n aegis history aegis && helm -n aegis rollback aegis <revision>   # Helm
git revert <bad-commit> && git push                                      # GitOps (ArgoCD sync చేస్తుంది)
kubectl -n aegis rollout undo deploy/aegis-aegis-platform                 # Emergency మాత్రమే
IMAGE_TAG=<old-sha> docker compose -f docker-compose.prod.yml up -d api   # VM
```

**Database migrations:** Expand-and-contract pattern. కొత్త column add చేయండి, రెండింటిలో write చేసే code deploy చేయండి, backfill చేయండి, reads switch చేయండి, తర్వాత పాత column తీసేయండి. ప్రతి step backward compatible, కాబట్టి rollback ఎప్పుడూ break అవ్వదు.

---

## Phase 10: Production లో Operate చేయడం

1. **On-call:** Alerts PagerDuty / Opsgenie కి వెళ్తాయి. ప్రతి alert కి ఒక runbook link ఉంటుంది (ఈ project లో RAG search runbooks ని index చేసేది అందుకే)
2. **Incident flow:** Detect → Triage (P1 నుండి P4) → **ముందు mitigate** (rollback / scale out) → **తర్వాత** root cause → Status page లో communicate
3. **Blameless postmortem:** Timeline, impact, root cause, ఏది బాగా జరిగింది, action items (owners తో). ఎవరినీ blame చేయరు
4. **Cost:** నిజమైన usage (`kubectl top pods`) ఆధారంగా requests / limits సెట్ చేయండి, autoscale, budget alarms, demo environments delete చేయండి
5. **Security:** Dependabot / Renovate, CI లో Trivy, least privilege IAM, TLS everywhere, secrets rotation

---

## Troubleshooting: ముఖ్యమైన Errors

✅ ఉన్నవి ఈ repository లో నిజంగా reproduce చేసి fix చేసినవి.

### Application errors

| Error | కారణం | Fix |
| :--- | :--- | :--- |
| `ModuleNotFoundError: No module named 'src'` | Repo root నుండి run చేయలేదు | Root folder నుండి `uvicorn src.api.main:app` |
| `ModuleNotFoundError: No module named 'fastapi'` | venv activate చేయలేదు | `.venv` activate చేసి `pip install -r requirements.txt` |
| ✅ tiktoken `ProxyError` | tiktoken first use లో file download చేస్తుంది, restricted network లో block అవుతుంది | Image build లో ముందే download చేయండి (`TIKTOKEN_CACHE_DIR`) |
| `422 Unprocessable Entity` | Request body తప్పు | Response లోని `detail` చూడండి, అది ఏ field తప్పో చెప్తుంది. `/docs` లో schema చూడండి |
| `405 Method Not Allowed` | POST endpoint కి GET పంపారు | `curl -X POST` |
| ✅ Anomaly ఎప్పుడూ `NORMAL` | Engine train కాలేదు (z = 0) | Per-service rolling baseline, `WARMING_UP` status |
| `WORKER TIMEOUT` (gunicorn) | Request 60 seconds కంటే ఎక్కువ పట్టింది | Long jobs ని queue లో పెట్టండి లేదా `--timeout` పెంచండి |
| Browser లో `CORS policy` error | Frontend origin `AEGIS_CORS_ORIGINS` లో లేదు | Exact origin (scheme + host + port) add చేయండి |
| వేరే pods వేరే incident IDs ఇస్తాయి | State memory లో ఉంది (per process) | Postgres / Redis కి మార్చాలి |

### CI errors

| Error | కారణం | Fix |
| :--- | :--- | :--- |
| ✅ `ruff check` / `ruff format --check` fail | Formatter run చేయకుండా commit చేశారు | `ruff check --fix . && ruff format .`, pre-commit hook |
| ✅ `Unable to resolve action trivy-action@0.28.0` | ఆ version tag లేదు | `v0.36.0` commit SHA కి pin చేశాం |
| ✅ Trivy HIGH CVEs (urllib3, msgpack, setuptools) | pip లోపల bundle అయిన libraries | Runtime image నుండి pip తీసేశాం |
| ✅ SonarCloud "Use full commit SHA hash" | Actions `@v3` tags వాడాయి | ప్రతి action ని full SHA కి pin చేశాం |
| GHCR push `denied` | `packages: write` permission లేదు | Job లో permission ఉంచండి |

### Docker errors

| Error | కారణం | Fix |
| :--- | :--- | :--- |
| `failed to connect to the docker API` | Docker Desktop run అవ్వడం లేదు | Start చేయండి (`scripts/fix_docker_desktop.ps1`) |
| `port is already allocated` | Port ఇప్పటికే వాడుకలో ఉంది | `netstat -ano \| findstr :8000` తో process ఆపండి, లేదా `-p 8080:8000` |
| ✅ `PermissionError: data/analytics` | Read-only FS + root-owned tmpfs | `--tmpfs /app/data:uid=10001,gid=10001` |
| ✅ `CERTIFICATE_VERIFY_FAILED` (docker build లో) | Corporate proxy CA | CA ని BuildKit secret గా mount చేయండి. Verification disable చేయవద్దు |
| ✅ Linux లో Prometheus target DOWN | `host.docker.internal` Linux లో పని చేయదు | `extra_hosts: host-gateway` |
| `Exited (137)` | Memory అయిపోయింది (OOM) | Memory limit పెంచండి, workers తగ్గించండి |
| Image 5+ GB | `requirements.txt` (torch) తో build చేశారు | `requirements-prod.txt` వాడండి |

### Kubernetes errors

| Error | కారణం | Fix |
| :--- | :--- | :--- |
| `ImagePullBackOff` | Image private, లేదా పేరు / tag తప్పు | Package public చేయండి లేదా `imagePullSecrets` ఇవ్వండి. `kubectl describe pod` |
| `CrashLoopBackOff` | App start అవ్వగానే crash అవుతోంది | `kubectl logs <pod> --previous` |
| `Running` కానీ `READY 0/1`, 502/503 | Readiness probe fail | `kubectl describe pod`, `kubectl get endpoints` |
| `OOMKilled` | Memory limit దాటింది | Limit పెంచండి, `kubectl top pod` |
| `Pending`, `Insufficient cpu` | Node లో CPU లేదు | Requests తగ్గించండి లేదా nodes add చేయండి |
| HPA `<unknown>/75%` | metrics-server లేదు | metrics-server install చేయండి |
| ✅ HTTPS certificate రాదు | Ingress లో `tls:` block లేదు | Add చేశాం |
| Certificate `READY False` | DNS ఇంకా ingress కి point అవ్వలేదు, లేదా port 80 block | `kubectl describe challenge -A`, DNS / firewall fix |
| ✅ `Evicted: ephemeral-storage` / SonarCloud "storage limit" | Disk limit లేదు | `ephemeral-storage` limits + `emptyDir.sizeLimit` |
| ✅ ArgoCD `repository not found` | `repoURL` లో తప్పు username | `Umanagalla27` కి fix చేశాం |
| ArgoCD `OutOfSync` (manual edit తర్వాత) | Self-heal manual changes ని revert చేస్తుంది | Cluster ని కాదు, Git ని మార్చండి |
| `runAsNonRoot and image will run as root` | Image లో `USER` లేదు | Dockerfile లో `USER aegis` (UID 10001) ఉంది |

### Terraform / AWS errors

| Error | కారణం | Fix |
| :--- | :--- | :--- |
| `No valid credential sources found` | AWS credentials లేవు | `aws configure` / SSO. CI లో OIDC |
| ECS `ResourceInitializationError` | Execution role లేదు లేదా ECR కి network లేదు | Role + NAT / VPC endpoints |
| `log group does not exist` | Log group create చేయలేదు | `aws_cloudwatch_log_group` add చేయండి |
| `Error acquiring the state lock` | మరో `apply` నడుస్తోంది | వేచి ఉండండి. Stale అని ఖచ్చితంగా తెలిస్తేనే `terraform force-unlock` |
| Deploy తర్వాత వెంటనే budget email | $5 budget, cost ~$34 | Demo కి expected. Budget పెంచండి లేదా `destroy` |

### Debugging Method (Interviewers వినాలనుకునేది)

1. **Reproduce** చేయండి (exact request, exact version / SHA)
2. **Observe** చేయండి (logs, events, metrics)
3. **Isolate** చేయండి (code? config? infra? dependency? చివరి good version తో compare చేయండి)
4. **ముందు mitigate** చేయండి (rollback / scale out), users కి నొప్పి ఆపండి
5. **Root cause fix** + **regression test**, normal pipeline ద్వారా deploy
6. **Postmortem** రాయండి (action items తో)

---

## Production-Readiness Checklist

✅ **పూర్తయినవి:**
- [x] Dockerfile: multi-stage, slim, non-root, healthcheck, graceful shutdown, pip లేదు
- [x] CI: lint, tests, eval gates, image build, smoke test, Trivy scan, SHA తో push
- [x] CI security: actions SHA pinning, least-privilege token
- [x] Helm: startup / readiness / liveness probes, resources, storage limits, HPA, non-root + read-only, TLS Ingress
- [x] GitOps: ArgoCD automated sync + self-heal
- [x] Bounded label cardinality తో metrics
- [x] Environment నుండి CORS config

❌ **ఇంకా చేయాల్సినవి (Interview లో "next steps" గా చెప్పండి):**
- [ ] **Authentication / authorization:** ఇప్పుడు API reach అయిన ఎవరైనా rollbacks, heavy eval jobs trigger చేయగలరు
- [ ] Rate limiting
- [ ] Shared state (Postgres / Redis): incidents, HITL checkpoints, retriever index ఇప్పుడు memory లో ఉన్నాయి
- [ ] Request IDs తో structured JSON logs + OTLP tracing
- [ ] Runbook links తో alert rules
- [ ] Terraform complete చేయడం (VPC, ALB, ECS service, IAM, logs, remote state)
- [ ] PodDisruptionBudget, NetworkPolicy, per-environment values files
- [ ] Dependency lock file (`pip-compile` / `uv lock`)
