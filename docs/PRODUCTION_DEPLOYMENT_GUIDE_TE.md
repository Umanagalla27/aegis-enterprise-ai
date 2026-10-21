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

API వీటి లేకుండా కూడా నడుస్తుంది (అప్పుడు state process memory లో ఉంటుంది). Production లాగా వాడాలంటే:

```bash
export AEGIS_DATABASE_URL=postgresql://uma@localhost:5435/aegis_db           # HITL checkpoints
export PGPASSWORD=password                                                      # read by libpq; keeps it out of the URL
export AEGIS_REDIS_URL=redis://localhost:6382/0                                # baselines, rate limits
export AEGIS_API_KEY=dev-key                                                    # optional: /v1 కి X-API-Key కావాలి
```

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
- `AEGIS_REDIS_URL` set చేస్తే baseline అన్ని workers / pods కి ఒకటే, restart అయినా పోదు

### 1.6 Authentication, rate limits, human approval

- `AEGIS_API_KEY` set చేస్తే ప్రతి `/v1` call కి `-H "X-API-Key: <key>"` కావాలి (లేకపోతే `401`). `/health`, `/metrics`, dashboard page open గానే ఉంటాయి; dashboard ఒక్కసారి key అడుగుతుంది.
- Eval, pipeline, agent-start endpoints కి `AEGIS_HEAVY_RATE_LIMIT` (default `10/minute`) limit ఉంది, దాటితే `429`.

```bash
curl -s -X POST localhost:8000/v1/agent/incidents -H "content-type: application/json" \
  -d '{"service_name":"rag-retrieval","description":"CUDA OOM critical"}'
# -> "status": "AWAITING_APPROVAL", "thread_id": "inc-..."
curl -s -X POST localhost:8000/v1/agent/incidents/<thread_id>/decision \
  -H "content-type: application/json" -d '{"approved": true, "reviewer": "sre-lead"}'
# -> "status": "COMPLETED"
```

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
| `tests/test_shared_state.py` | ఒక worker pause చేసిన incident ని **వేరే worker** approve చేయగలదా (Postgres), Redis baselines, unique incident IDs |
| `tests/test_api_security.py` | Key లేకపోతే `401`, probes open, forged approval reject, `429` rate limit |
| `tests/test_observability.py` | `X-Request-ID` మరియు JSON log lines |
| `eval/test_eval_gates.py` | Faithfulness >= 0.85, recall >= 0.80, agent accuracy >= 90% |

**Testing pyramid (companies వాడేది):**
- చాలా ఎక్కువ **unit tests** (fast)
- కొన్ని **integration tests** (FastAPI `TestClient`)
- కొద్దిగా **end-to-end tests** (CI లో smoke test ఒకటి)

**Regression test rule:** ప్రతి bug fix తో ఒక test రాయాలి. ఆ test **fix ముందు fail అవ్వాలి, fix తర్వాత pass అవ్వాలి**.

Postgres / Redis tests కోసం `AEGIS_TEST_DATABASE_URL`, `AEGIS_TEST_REDIS_URL` set చేయండి (CI చేస్తుంది; local లో set చేయకపోతే skip అవుతాయి).

`tests/conftest.py` ప్రతి test ముందు rate-limit counters reset చేస్తుంది, ETL output ని (`AEGIS_DATA_DIR`) temp folder కి పంపుతుంది. కాబట్టి tests ఇప్పుడు tracked `data/analytics/` file ని మార్చవు.

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
scripts/smoke_test.sh http://localhost:8000          # health + 5 HITL approvals
```

### Dockerfile లో ప్రతి నిర్ణయం ఎందుకు?

| నిర్ణయం | ఎందుకు |
| :--- | :--- |
| **Multi-stage build** | Build tools final image లోకి రావు, image చిన్నగా, safe గా ఉంటుంది |
| **`python:3.12-slim`** | CI లో ఉన్న Python version, అనవసరమైన ~800 MB OS packages ఉండవు |
| **`requirements-prod.txt`** | API కి torch అవసరం లేదు. దాన్ని తీసేయడం వల్ల image కొన్ని GB నుండి చాలా చిన్నది అయ్యింది |
| **Lock file + hashes** (`requirements-prod.in` → `requirements-prod.txt`, `--require-hashes`) | ఒకే commit ఎప్పుడు build చేసినా ఒకే versions. ఎవరైనా package ని మార్చితే build fail అవుతుంది. `.in` మార్చాక: `pip-compile --generate-hashes --strip-extras requirements-prod.in -o requirements-prod.txt` (Python 3.12 తో) |
| **Non-root user (UID 10001)** | Hacker app లోకి వచ్చినా root access ఉండదు |
| **Code root-owned** | App user code ని చదవగలడు, మార్చలేడు |
| **pip తీసేశాం** | pip లోపల bundle అయిన libraries లో 4 HIGH vulnerabilities ఉన్నాయి. Runtime లో pip అవసరం లేదు |
| **`PYTHONUNBUFFERED=1`** | Logs వెంటనే `docker logs` లో కనిపిస్తాయి |
| **`HEALTHCHECK`** | `/health` respond చేయకపోతే Docker `unhealthy` అని mark చేస్తుంది |
| **gunicorn + uvicorn** | Worker crash అయితే gunicorn మళ్ళీ start చేస్తుంది, `SIGTERM` వస్తే graceful shutdown చేస్తుంది. `WEB_CONCURRENCY` default **1**: ఎక్కువ workers కి shared state (`AEGIS_DATABASE_URL`, `AEGIS_REDIS_URL`) కావాలి, production compose / Helm అవి ఇస్తాయి |
| **`AEGIS_LOG_FORMAT=json`** | ప్రతి log line ఒక JSON object, `request_id` తో |
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
├─ ruff check + format             ├─ Smoke test: 3 workers + Postgres + Redis + API key,
├─ pytest (అన్ని phases)           │   scripts/smoke_test.sh (20 HITL approvals)
├─ shared-state tests (PG/Redis)   ├─ Trivy security scan
├─ RAGAS / agent eval gates        ├─ GHCR login (PR లో కాదు)
└─ 20-fault chaos test             └─ Push :<sha>, main లో :latest, vX.Y.Z tag కి :X.Y.Z
```

| Stage | ఎందుకు |
| :--- | :--- |
| **ముందు lint** | చవకైన check ముందు, CI time ఆదా |
| **Service containers** | CI లో నిజమైన Postgres / Redis, mocks కాదు |
| **`concurrency: cancel-in-progress`** | కొత్త push వస్తే పాత run cancel అవుతుంది |
| **Smoke test** | Unit tests pass అయినా container start అవుతుందని గ్యారంటీ లేదు (missing dependency, తప్పు CMD, permissions). చాలా workers + నిజమైన Postgres / Redis తో run చేస్తేనే multi-worker bugs దొరుకుతాయి |
| **Release tags** (`git tag v1.0.0 && git push origin v1.0.0`) | `:1.0.0` image publish అవుతుంది. Helm chart, `.env.example` ఇదే tag deploy చేస్తాయి |
| **Dependabot** | ప్రతి వారం Python packages, GitHub Actions (SHA pins), base image updates కి PRs |
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

Files: `docker/docker-compose.prod.yml`, `docker/Caddyfile`, `docker/prometheus.prod.yml`, `docker/prometheus/alerts.yml`, `docker/grafana/`, `docker/.env.example`

```
Internet ──443──> Caddy (auto HTTPS) ──> api:8000 (2 workers) ──> Postgres (HITL) + Redis (baselines, limits)
                                            ▲
                         Prometheus (alerts)┘ ← Grafana (127.0.0.1 మాత్రమే, dashboard ready)
```

`.env` లో `IMAGE_TAG`, `DOMAIN`, `AEGIS_CORS_ORIGINS`, `AEGIS_API_KEY`, `POSTGRES_PASSWORD`, `GRAFANA_ADMIN_PASSWORD` లేకపోతే stack start అవ్వదు (కావాలనే).

**Steps:**

1. **VM create చేయండి:** Ubuntu 24.04, 2 vCPU / 2 GB RAM (AWS `t3.small`, Hetzner CX22, Oracle free tier). Terraform తో steps 1, 2, 4 automatic: Option C చూడండి
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
   cp .env.example .env && nano .env      # అన్ని values; secrets: openssl rand -hex 32
   chmod 600 .env
   ```
6. **Start:**
   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env up -d
   docker compose -f docker-compose.prod.yml ps
   docker compose -f docker-compose.prod.yml logs -f caddy    # certificate issue అవ్వడం చూడండి
   ```
7. **Verify:** `scripts/smoke_test.sh https://aegis.yourdomain.com "$AEGIS_API_KEY"` (health, key లేకపోతే `401`, HITL approvals). Grafana కోసం SSH tunnel: `ssh -L 3001:localhost:3001 ubuntu@<vm-ip>`, తర్వాత `http://localhost:3001` ("Aegis API - Golden Signals" dashboard ముందే ఉంటుంది)
8. **కొత్త version:** `.env` లో `IMAGE_TAG=<new version / sha>` మార్చి `docker compose ... pull api && docker compose ... up -d api`, తర్వాత మళ్ళీ smoke test
9. **Rollback:** పాత SHA పెట్టి మళ్ళీ అదే command

### 🅱️ Option B: Kubernetes + Helm + ArgoCD (Companies ఎక్కువగా వాడేది)

**Files ఏమి చేస్తాయి:**

| File | పని |
| :--- | :--- |
| `templates/deployment.yaml` | Pods: image, env, secrets (API key, database / Redis URLs), probes, resources (measure చేసినవి: idle ~400 MiB, load లో ~475 MiB, అందుకే 512Mi / 1Gi), non-root + read-only, storage limits. Secret లేకుండా ఎక్కువ replicas కి **render అవ్వదు** |
| `templates/service.yaml` | Pods ముందు stable internal IP మరియు DNS name |
| `templates/ingress.yaml` | బయటి నుండి HTTPS traffic లోపలికి (cert-manager కోసం `tls:` block తో) |
| `templates/hpa.yaml` | Load పెరిగితే 3 నుండి 10 pods వరకు auto-scale |
| `templates/pdb.yaml` | PodDisruptionBudget: node maintenance లో కనీసం 2 pods ఉంటాయి |
| `templates/networkpolicy.yaml` | Ingress controller, Prometheus మాత్రమే pods కి connect అవ్వగలవు |
| `values.yaml` / `values-staging.yaml` | Production values, దాని పైన staging overrides |
| `k8s/argocd/application.yaml`, `application-staging.yaml` | ArgoCD `main` ని `aegis-production`, `aegis-staging` లోకి sync చేస్తుంది |

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
# Postgres / Redis లేకుండా 1 replica మాత్రమే (ఎక్కువ కి chart secret అడుగుతుంది)
helm upgrade --install aegis k8s/helm/aegis-platform -n aegis --create-namespace \
  --set image.tag=dev --set ingress.enabled=false --set networkPolicy.enabled=false \
  --set secrets.existingSecret= --set replicaCount=1 --set autoscaling.enabled=false
kubectl -n aegis get pods -w
kubectl -n aegis port-forward svc/aegis-aegis-platform 8000:8000
curl localhost:8000/health
```

HPA పని చేయాలంటే **metrics-server** install చేయాలి (English guide లో commands ఉన్నాయి).

**Real cluster (EKS లాంటిది) కోసం:** ingress-nginx, cert-manager + Let's Encrypt ClusterIssuer, తర్వాత ప్రతి namespace లో secret:

```bash
kubectl -n aegis-production create secret generic aegis-secrets \
  --from-literal=api-key="$(openssl rand -hex 32)" \
  --from-literal=database-url="$AEGIS_DATABASE_URL" \
  --from-literal=redis-url='redis://HOST:6379/0'
```

తర్వాత ArgoCD install చేసి `kubectl apply -f k8s/argocd/application.yaml -f k8s/argocd/application-staging.yaml`. పూర్తి commands English guide Phase 6B.2 లో ఉన్నాయి.

**GitOps లో deploy అంటే:** కొత్త tag ని ముందు `values-staging.yaml` లో పెట్టి staging లో smoke test, తర్వాత అదే tag ని `values.yaml` (production) లోకి promote. **Rollback అంటే** `git revert`.

### 🅲 Option C: Terraform (AWS VM)

`terraform/` Option A కోసం VM ని AWS లో **code తో** create చేస్తుంది (console లో click చేయనవసరం లేదు). ఇంతకుముందు ఉన్న ECS config లో service, IAM, network, load balancer లేవు, అది ఎప్పటికీ run అవ్వదు. దాన్ని దీనితో మార్చాం.

| File | ఏమి create చేస్తుంది |
| :--- | :--- |
| `main.tf` | Ubuntu 24.04 AMI, security group (SSH మీ IP నుండి మాత్రమే; 80/443 public), key pair, EC2 (IMDSv2, encrypted disk), Elastic IP |
| `user_data.sh` | First boot లో Docker install, repo `/opt/aegis` కి clone (secrets మీరు SSH తో పెడతారు, Terraform లో కాదు) |
| `budget_alarm.tf` | `monthly_budget_usd` (default 25) లో 80% / 100% దాటితే email |
| `providers.tf` | AWS provider + **S3 remote state, native locking** (`use_lockfile`, Terraform >= 1.10) |
| `outputs.tf` | DNS కోసం public IP, SSH command |

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars     # మీ IP/32, SSH public key, alert email
cp backend.hcl.example backend.hcl               # మీ state bucket
terraform init -backend-config=backend.hcl
terraform fmt -check && terraform validate
terraform plan -out tfplan                       # ఏమి మారుతుందో ముందే చూడండి
terraform apply tfplan                           # public_ip, ssh_command print అవుతాయి
# DNS A record -> public_ip, తర్వాత VM లో Option A steps 5-7 (/opt/aegis/docker)
terraform destroy                                # billing ఆపడానికి
```

**Cost:** `t3.small` + 30 GB disk + Elastic IP నెలకు ~**$20** (us-east-1), అందుకే budget default $25. `ssh_allowed_cidr` ఎప్పుడూ `0.0.0.0/0` అవ్వకుండా validation ఉంది. `terraform validate` pass అయ్యింది. అది ఒక security group description లోని apostrophe ని పట్టుకుంది, AWS apply సమయంలో reject చేసేది.

---

## Phase 7: Configuration & Secrets

| Setting | ఎక్కడ చదువుతుంది | ఉదాహరణ |
| :--- | :--- | :--- |
| `AEGIS_API_KEY` | `src/api/security.py` | Secret. Set చేస్తే `/v1` కి `X-API-Key` కావాలి. Production compose, Helm లో తప్పనిసరి |
| `AEGIS_DATABASE_URL` | `src/agents/checkpointing.py` | `postgresql://...`: HITL checkpoints, అన్ని workers / pods కి ఒకటే |
| `AEGIS_REDIS_URL` | `baseline_store.py`, `security.py` | `redis://...`: anomaly baselines, rate-limit counters |
| `AEGIS_HEAVY_RATE_LIMIT` | `src/api/security.py` | Default `10/minute` (ఒక్కో client కి) |
| `AEGIS_CORS_ORIGINS` | `src/api/main.py` | `https://aegis.yourdomain.com` (comma తో వేరు చేయండి; default `http://localhost:8000`) |
| `AEGIS_LOG_FORMAT` / `AEGIS_LOG_LEVEL` | `logging_config.py` | Image లో `json`, local లో `text` / `INFO` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `otel_instrumentation.py` | Jaeger / Tempo URL; set చేయకపోతే tracing off |
| `AEGIS_DATA_DIR` | `batch_aggregator.py` | ETL output folder (default `data`) |
| `FORWARDED_ALLOW_IPS` | uvicorn | Caddy / ingress వెనుక `*`, అప్పుడు rate limit నిజమైన client IP చూస్తుంది |
| `WEB_CONCURRENCY` | `Dockerfile` CMD | gunicorn workers; default 1, database / Redis URLs ఉంటేనే పెంచండి |
| `PORT` | `Dockerfile` CMD | `8000` |

**Secrets rules (companies పాటించేవి):**
1. Git లో, image లో, logs లో **ఎప్పుడూ వద్దు**
2. Local లో `.env` (git-ignored). VM లో `.env` + `chmod 600`. Kubernetes లో **Secrets** (AWS Secrets Manager / Vault నుండి External Secrets Operator ద్వారా)
3. CI లో GitHub Secrets, లేదా OIDC (static keys అసలు ఉండవు)
4. Leak అయితే **rotate చేయండి**. Git history నుండి delete చేస్తే సరిపోదు

> Local `docker/docker-compose.yml` default గా `password` / `admin` వాడుతుంది (`POSTGRES_PASSWORD` / `GRAFANA_ADMIN_PASSWORD` తో మార్చవచ్చు). అది laptop లో మాత్రమే సరి. Production compose లో defaults లేవు, values లేకపోతే start అవ్వదు.

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

### Alerts & Dashboards (production compose stack లో)

`docker/prometheus/alerts.yml` (`promtool check rules` pass):

| Alert | ఎప్పుడు fire అవుతుంది |
| :--- | :--- |
| `AegisApiDown` | 2 నిమిషాలు API scrape అవ్వకపోతే (critical) |
| `AegisHighErrorRate` | 5 నిమిషాలు 1% కంటే ఎక్కువ 5xx (critical) |
| `AegisHighLatencyP95` | 10 నిమిషాలు p95 > 500 ms (warning) |
| `AegisRateLimitedRequests` | 10 నిమిషాలు 429s ఎక్కువ (info) |
| `AegisCriticalAnomalies` | 10 నిమిషాల్లో 5 కంటే ఎక్కువ CRITICAL anomalies (warning) |

ప్రతి rule కి `runbook` annotation ఉంది. Grafana Prometheus datasource, "Aegis API - Golden Signals" dashboard తో ముందే ready గా start అవుతుంది. Notifications కావాలంటే Alertmanager + Slack / PagerDuty add చేయండి.

### Logs

Image **ప్రతి line ఒక JSON object** గా stdout కి log చేస్తుంది. ప్రతి request కి `X-Request-ID` (caller ఇచ్చింది లేదా కొత్తది) వస్తుంది: response header లో, ఆ request handle చేసేటప్పుడు వచ్చే ప్రతి log line లో:

```json
{"ts": "...", "level": "INFO", "logger": "aegis.access", "message": "request", "request_id": "c2c5f044...", "method": "POST", "path": "/v1/agent/incidents/{thread_id}/decision", "status": 200, "duration_ms": 28.74}
```

User error report చేస్తే `X-Request-ID` అడిగి, logs లో దాన్ని వెతకండి.

### Traces

`OTEL_EXPORTER_OTLP_ENDPOINT` (ఉదా: `http://jaeger:4318`) set చేస్తే ప్రతి request ఒక span గా OTLP తో export అవుతుంది. Set చేయకపోతే tracing off.

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

**Releases:** `git tag v1.1.0 && git push origin v1.1.0` → `:1.1.0` image. ముందు staging (`values-staging.yaml`) లో deploy చేసి `scripts/smoke_test.sh` run చేయండి, తర్వాత అదే tag ని production కి promote చేయండి.

**Database migrations:** LangGraph checkpoint tables startup లో Postgres advisory lock తో create అవుతాయి. మీ సొంత tables కి Expand-and-contract pattern. కొత్త column add చేయండి, రెండింటిలో write చేసే code deploy చేయండి, backfill చేయండి, reads switch చేయండి, తర్వాత పాత column తీసేయండి. ప్రతి step backward compatible, కాబట్టి rollback ఎప్పుడూ break అవ్వదు.

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
| `WORKER TIMEOUT` (gunicorn) | Request 60 seconds కంటే ఎక్కువ పట్టింది | Measure చేశాం: heaviest endpoint ~1.4 s. ఇంకా పెద్ద jobs అయితే queue లో పెట్టండి |
| Browser లో `CORS policy` error | Frontend origin `AEGIS_CORS_ORIGINS` లో లేదు | Exact origin (scheme + host + port) add చేయండి |
| ✅ Approval కి **404 "Unknown incident thread"** (2 workers తో 10 లో 3 సార్లు) | Paused incident ఒక worker memory (`MemorySaver`) లో ఉంది, approval వేరే worker కి వెళ్ళింది | **Fixed:** `AEGIS_DATABASE_URL` → `PostgresSaver`. 4 workers తో 20/20, restart తర్వాత కూడా పని చేస్తుంది. Incident IDs random, baselines Redis లో |
| ✅ Startup లో worker crash: `UniqueViolation ... pg_type_typname_nsp_index` | చాలా workers ఒకేసారి `CREATE TABLE` run చేశాయి | **Fixed:** advisory lock ఉన్న worker మాత్రమే tables create చేస్తుంది |
| ✅ **Fresh database** మీద అన్ని workers hang, container `unhealthy` | **Deadlock:** `CREATE INDEX CONCURRENTLY` అన్ని open transactions కోసం ఆగుతుంది, `pg_advisory_lock()` లో ఆగిన workers కూడా open transactions | **Fixed:** వేచి ఉండే workers `pg_try_advisory_lock()` తో poll చేస్తాయి (transaction లేకుండా) |
| ✅ `Worker (pid:21) exited with code 1` కానీ workers నడుస్తున్నాయి | Docker HEALTHCHECK probe startup లో exit 1 అయ్యింది, PID 1 (gunicorn) దాన్ని worker అనుకుని log చేసింది | **Fixed:** compose లో `init: true` (tini PID 1 అవుతుంది) |
| `401 Missing or invalid API key` | `AEGIS_API_KEY` set అయ్యింది, header లేదు / తప్పు | `-H "X-API-Key: <key>"`; dashboard లో page reload చేసి key ఇవ్వండి |
| `429 Too Many Requests` | Heavy endpoints కి limit దాటారు | ఒక నిమిషం ఆగండి. Proxy వెనుక `FORWARDED_ALLOW_IPS` set చేయండి |

### CI errors

| Error | కారణం | Fix |
| :--- | :--- | :--- |
| ✅ `ruff check` / `ruff format --check` fail | Formatter run చేయకుండా commit చేశారు | `ruff check --fix . && ruff format .`, pre-commit hook |
| ✅ `Unable to resolve action trivy-action@0.28.0` | ఆ version tag లేదు | `v0.36.0` commit SHA కి pin చేశాం |
| ✅ Trivy HIGH CVEs (urllib3, msgpack, setuptools) | pip లోపల bundle అయిన libraries | Runtime image నుండి pip తీసేశాం |
| ✅ SonarCloud "Use full commit SHA hash" | Actions `@v3` tags వాడాయి | ప్రతి action ని full SHA కి pin చేశాం |
| GHCR push `denied` | `packages: write` permission లేదు | Job లో permission ఉంచండి |
| ✅ Tests `data/analytics/...parquet` file మార్చాయి | ETL output tracked file కి వెళ్ళేది | **Fixed:** `AEGIS_DATA_DIR` temp folder (conftest) |
| `THESE PACKAGES DO NOT MATCH THE HASHES` (docker build) | `requirements-prod.txt` ని చేతితో మార్చారు | `requirements-prod.in` మార్చి `pip-compile --generate-hashes` తో regenerate చేయండి |

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
| ✅ `secrets.existingSecret is required with more than one replica` | Postgres / Redis లేకుండా ఎక్కువ replicas అంటే HITL break అవుతుంది | `aegis-secrets` create చేయండి, లేదా dev కి 1 replica |
| `CreateContainerConfigError: secret "aegis-secrets" not found` | ఆ namespace లో secret లేదు | `kubectl -n <ns> create secret generic aegis-secrets ...` |
| NetworkPolicy తర్వాత 504 / timeouts | Ingress controller వేరే namespace లో ఉంది | `networkPolicy.ingressControllerNamespace` సరిచేయండి |
| ✅ ArgoCD `repository not found` | `repoURL` లో తప్పు username | `Umanagalla27` కి fix చేశాం |
| ArgoCD `OutOfSync` (manual edit తర్వాత) | Self-heal manual changes ని revert చేస్తుంది | Cluster ని కాదు, Git ని మార్చండి |
| `runAsNonRoot and image will run as root` | Image లో `USER` లేదు | Dockerfile లో `USER aegis` (UID 10001) ఉంది |

### Terraform / AWS errors

| Error | కారణం | Fix |
| :--- | :--- | :--- |
| `No valid credential sources found` | AWS credentials లేవు | `aws configure` / SSO. CI లో OIDC |
| ✅ `"egress.0.description" doesn't comply with restrictions` | Security group description లో apostrophe (AWS అంగీకరించదు) | **Fixed.** `plan` ముందు ఎప్పుడూ `terraform validate` run చేయండి |
| `... must not open SSH to the whole internet` | `ssh_allowed_cidr = "0.0.0.0/0"` | మీ IP: `curl -s https://checkip.amazonaws.com` → `x.x.x.x/32` |
| SSH `Connection timed out` | మీ IP మారింది | `ssh_allowed_cidr` update చేసి `terraform apply` |
| `Error acquiring the state lock` | మరో `apply` నడుస్తోంది | వేచి ఉండండి. Stale అని ఖచ్చితంగా తెలిస్తేనే `terraform force-unlock` |
| `Backend initialization required` | `-backend-config=backend.hcl` లేకుండా init | `terraform init -backend-config=backend.hcl` |
| Budget email | Cost `monthly_budget_usd` లో 80% దాటింది | Cost Explorer చూడండి; అవసరం లేని demo ని `destroy` చేయండి |

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
- [x] Dockerfile: multi-stage, slim, non-root, read-only, pip లేదు, healthcheck, graceful shutdown
- [x] Hashes తో lock file; Dependabot
- [x] CI: lint, tests (Postgres / Redis తో), eval gates, image build, multi-worker smoke test, Trivy, SHA / release tag push
- [x] CI security: actions SHA pinning, least-privilege token
- [x] `/v1` కి API key authentication, heavy endpoints కి rate limits
- [x] Shared state: HITL Postgres లో, baselines / rate limits Redis లో, unique incident IDs
- [x] Request IDs తో JSON logs, OTLP tracing, Prometheus alerts, Grafana dashboard
- [x] Helm: probes, measured resources, HPA, PDB, NetworkPolicy, secrets, staging values, TLS Ingress
- [x] GitOps: ArgoCD production + staging
- [x] Terraform: complete VM deployment, remote state, budget alarm (`terraform validate` pass)

❌ **ఇంకా చేయాల్సినవి (Interview లో "next steps" గా చెప్పండి):**
- [ ] Per-user login (OIDC) తో approvals: ఇప్పుడు ఒకే shared API key, `reviewer` caller పంపిందే
- [ ] Alertmanager (Slack / PagerDuty) receiver
- [ ] Helm / Terraform ని నిజమైన cloud account లో apply చేయడం (validate చేశాం, apply కాదు)
- [ ] Retriever index, incident reports Postgres లో store చేయడం
