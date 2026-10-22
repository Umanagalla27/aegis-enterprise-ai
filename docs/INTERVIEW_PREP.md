# Aegis Enterprise AI: Resume and Interview Preparation

Companion to [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md).

---

## 1. Read this first: what is real and what is simulated

Interviewers **will** go deep on anything on your resume. The README uses big names (vLLM, Presidio, PySpark, Kafka, MLflow, RAGAS). In this codebase several of them are **lightweight in-process simulations of the pattern, not the real tool**. If you claim "built Kafka streaming with PySpark" and the interviewer asks about Spark executors or consumer-group rebalancing, the mismatch will cost you more than an honest description would.

| README / resume wording | What the code actually does | How to describe it honestly (and still impressively) |
| :--- | :--- | :--- |
| Transformer self-attention from scratch | ✅ Real PyTorch multi-head attention + Pre-LN block (`src/models/transformer_scratch.py`) | "Implemented multi-head scaled dot-product attention from scratch in PyTorch" |
| Hybrid RAG with BM25 + dense + RRF | ✅ Real BM25Plus (`rank_bm25`) and real RRF. ⚠️ The "dense" side is **token-set cosine overlap**, not neural embeddings | "Hybrid lexical retrieval fused with Reciprocal Rank Fusion; designed so the dense scorer can be swapped for sentence-transformer embeddings" |
| Graph RAG blast radius | ✅ Real NetworkX DiGraph, descendants on the reversed graph | As is |
| LangGraph multi-agent + HITL | ✅ Real LangGraph `StateGraph`, `interrupt()`, **Postgres checkpoints** shared by all workers/pods. Agent "reasoning" is **rule-based** (keywords), no LLM call | "Stateful LangGraph workflow with human-in-the-loop approval gates and Postgres-backed checkpoints; deterministic rule-based agents" |
| FastMCP tool server | ✅ Real `mcp` FastMCP tool registration. The rollback tool returns a string (no real Kubernetes call) | "Exposed tools over Model Context Protocol; rollback is simulated" |
| Presidio PII redaction | ⚠️ **Regex-based** redactor (`pii_redactor.py`; it was misleadingly named `presidio_redactor.py` and has been renamed) | "Regex PII redaction (SSN, card, email, phone, API keys) and prompt-injection signature detection" |
| Kafka with DLQ and consumer groups | ⚠️ **In-memory simulation**: partitions are Python lists; MD5 partitioning, Pydantic validation, DLQ and offsets are modelled | "Modelled Kafka semantics (key-hash partitioning, DLQ, offset commits) in an in-process simulator" |
| PySpark quantile aggregation | ⚠️ **pandas/numpy**, no Spark | "Batch aggregation of p50/p95/p99 and availability SLAs (pandas), written to Parquet" |
| dbt marts | ⚠️ Executes the dbt **SQL model files on SQLite** through a Python runner, not the dbt CLI | "Staging and mart SQL models in dbt layout, executed on SQLite" |
| Airflow DAG | ⚠️ Plain Python task functions; no Airflow scheduler | "ETL pipeline structured as Airflow-style tasks with an SLA gate" |
| vLLM serving | ⚠️ **Stub** that returns a hard-coded JSON string | Do not claim it. At most: "interface for a vLLM serving backend (stubbed)" |
| MLflow tracking | ⚠️ In-memory dict (`AegisMLflowTracker`), not `mlflow` | Do not claim MLflow unless you wire in the real `mlflow` client |
| RAGAS evaluation | ⚠️ Custom heuristic scorer modelled on RAGAS metric names, not the `ragas` library | "RAGAS-style faithfulness/recall gates enforced in CI" |
| Isolation Forest + Z-score | ✅ Real scikit-learn `IsolationForest` + Z-score | As is |
| FastAPI + Prometheus | ✅ Real | As is |
| Docker, CI/CD, Helm, ArgoCD | ✅ Real and production-hardened (this project's deployment work); Helm validated with `helm lint`, not applied to a live cluster | As is |
| API key auth, rate limits, JSON logs, alerts | ✅ Real (`src/api/security.py`, `logging_config.py`, `docker/prometheus/alerts.yml`) | As is |
| Terraform | ✅ Complete single-VM AWS deployment (EC2, security group, Elastic IP, S3 remote state, budget alarm); `terraform validate` passes, not applied to a real account | "Wrote Terraform for a single-VM AWS deployment with remote state and a budget alarm" (say "validated", not "running in production", unless you apply it) |

**Best strategy:** pick 2–3 simulated components and make them real before applying (see section 7). Even one real integration ("swapped the token-overlap scorer for `sentence-transformers` embeddings and measured the recall change") is a strong interview story.

---

## 2. Resume bullets (honest, metric-driven)

Pick 3–5:

- Built an **AIOps incident-response platform** in Python/FastAPI combining hybrid retrieval (BM25 + Reciprocal Rank Fusion), a NetworkX service-dependency graph for blast-radius analysis, and Z-score + Isolation Forest anomaly detection.
- Designed a **LangGraph multi-agent workflow** (security, triage, research, RCA, action planning, execution) with **human-in-the-loop interrupts** that block P1/P2 rollbacks until a reviewer approves, plus role-based tool allowlists and prompt-injection/PII guardrails.
- **Productionized the service:** multi-stage, non-root, read-only Docker image (**~233 MB**, down from multi-GB by splitting runtime from research dependencies) with **0 HIGH/CRITICAL CVEs** (Trivy).
- Built a **GitHub Actions CI/CD pipeline** (lint, 20+ tests, evaluation gates, 20-fault chaos benchmark, container smoke test, vulnerability scan) that publishes SHA-tagged images to GHCR. Deployed with **Helm + ArgoCD GitOps** (HPA 3–10 replicas, startup/readiness/liveness probes, cert-manager TLS).
- **Found and fixed production bugs**, each with a regression test: an anomaly detector that never fired (an unfitted baseline compared each value with itself), unbounded **Prometheus label cardinality** from raw URL paths, and RCA mis-attribution of other services' logs.
- **Made the service horizontally scalable:** human-approval requests failed with 404 in 30% of tries once the API ran several gunicorn workers (state in process memory). Moved LangGraph checkpoints to **Postgres** and anomaly baselines / rate-limit counters to **Redis** (20/20 approvals across 4 workers, survives restarts), and fixed a startup race in schema creation with a Postgres advisory lock.
- **Secured and instrumented the API:** API key auth, Redis-backed rate limits, JSON logs with request IDs, OpenTelemetry tracing, Prometheus alert rules and a provisioned Grafana dashboard; hashed dependency lock file and Dependabot.

---

## 3. The pitch

### 30 seconds

> "Aegis is an AIOps platform for SRE teams. When latency spikes, it detects the anomaly statistically, correlates logs and recent commits to suggest a root cause, retrieves the matching runbook with hybrid search, and computes the blast radius from a service-dependency graph. Remediations like rollbacks go through a LangGraph workflow with a mandatory human approval step for high-severity incidents. I containerized it, built the CI/CD pipeline, and deployed it with Helm and ArgoCD."

### 2 minutes (structure)

1. **Problem:** alert fatigue and slow manual root-cause analysis (MTTR); but letting an LLM roll back production unsupervised is dangerous.
2. **Architecture:** FastAPI gateway, then (a) anomaly engine, (b) retrieval layer (BM25 + RRF, Graph RAG), (c) agent workflow with guardrails and HITL, (d) data pipeline for daily SLA reporting.
3. **One deep technical choice:** RRF, because BM25 scores and similarity scores live on different scales; RRF fuses by *rank*, so no score normalization is needed.
4. **Production work:** Docker, CI, Helm/ArgoCD, observability, and the bugs found while doing it.
5. **What I'd do next:** per-user identity (OIDC) for approvals, real embeddings, an LLM behind the agents with evals.

---

## 4. Architecture walkthrough: "why" for every component

| Component | Why this choice | Trade-off you should mention |
| :--- | :--- | :--- |
| **FastAPI** | Async, Pydantic validation, auto OpenAPI docs | Sync endpoints run in a threadpool; CPU-heavy work still needs background workers |
| **BM25Plus** instead of BM25Okapi | Okapi IDF can go to zero or negative on tiny corpora (term in every doc), so scores vanish; Plus adds a lower bound | Slightly different ranking on large corpora |
| **RRF (k = 60)** | Scale-free fusion; robust; the standard default from the original RRF paper | Ignores score magnitude (a very confident hit is treated like rank 1 anyway) |
| **Graph RAG with reversed DiGraph** | Edges mean "A depends on B"; whoever depends on a failing node is impacted, so you take descendants in the reversed graph | Static topology; in production, derive it from service mesh or tracing data |
| **Z-score + Isolation Forest** | Z-score: instant, explainable univariate spikes. Isolation Forest: multivariate patterns (CPU + memory + latency together) without labels | Z-score assumes roughly normal data; IF needs a clean baseline and retraining |
| **LangGraph + PostgresSaver** | Explicit state machine, checkpoints, `interrupt()` for HITL, deterministic edges for auditability; Postgres so any worker/pod can resume a paused incident | Every step writes a checkpoint (more DB load); falls back to in-memory `MemorySaver` (single worker only) when no database is configured |
| **Redis for baselines and rate limits** | One shared window per service and one counter per client across all workers/pods | Another stateful dependency to run; Redis down means degraded scoring |
| **HITL for P1/P2** | Blast radius of a wrong rollback is high; humans approve, the agent does the toil | Slower mitigation; mitigate with good defaults and one-click approvals |
| **Tool allowlist per agent role** | Least privilege: the research agent cannot call rollback even if prompt-injected | Static lists must be maintained |
| **Regex PII + injection signatures** | Fast, deterministic, no ML dependency | Easy to bypass (paraphrasing, Unicode); production layers an ML classifier and output filtering |
| **gunicorn + uvicorn workers** | Process supervision and graceful shutdown | Each worker is a separate process: anything kept in memory is per worker (the cause of Bug 11) |
| **API key (not OAuth) auth** | Simple, one header, enough for service-to-service and a demo | One shared key: no per-user identity; `reviewer` in approvals is self-reported |
| **Helm + ArgoCD** | Templated manifests; Git as the source of truth; drift self-heals; rollback = `git revert` | More moving parts than `kubectl apply` |

---

## 5. Bugs I found and fixed (STAR format)

These are real, reproducible and fixed on this branch. Tell them as **Situation, Task, Action, Result**.

### Bug 1: the anomaly detector could never fire (silent failure)

- **Situation:** `POST /v1/telemetry/ingest` with `latency_ms: 999999` returned `severity: NORMAL`.
- **Root cause:** the API created `HybridAnomalyEngine()` but never called `fit_baseline()`. With no baseline, `detect_zscore` used the value itself as the mean: `z = (value - value) / 1 = 0`. Unit tests passed because they fitted the engine manually; **the integration path was untested**.
- **Action:** `src/api/main.py` now keeps a rolling baseline **per service** (`deque(maxlen=500)`). The first 20 events only build the baseline and the response says `WARMING_UP` instead of a silent `NORMAL`. After that, latency, CPU and memory are each scored against that service's own history, and anomalous events are kept out of the window so a spike cannot poison the baseline. The engine also reports `baseline_ready: false` if it is ever called without a baseline. Regression tests cover it.
- **Result:** a spike after warm-up returns `is_anomaly: true, severity: CRITICAL (z = 442)`.
- **Lesson:** *"Unit tests passing doesn't mean the feature works. Test the real entry point. And never fail silently: surface 'I don't know yet'."*

```python
# Before: detect_zscore with an empty baseline
stats = self.baseline_stats.get(metric_name, {"mean": value, "std": 1.0})  # mean == value -> z == 0
# After: explicit readiness flag + API-side rolling baseline
baseline_ready = metric_name in self.baseline_stats
```

### Bug 2: Prometheus label cardinality explosion

- **Situation:** requesting `/random-0`, `/random-1`, ... each created a new `aegis_http_requests_total{endpoint="/random-N"}` series.
- **Root cause:** the middleware used `request.url.path` as a label. Scanners hit thousands of random paths, and each unique label set is a time series held in Prometheus memory, so this is a **denial-of-service vector against your monitoring**.
- **Action:** label with the matched **route template** (`request.scope["route"].path`), and use `"unmatched"` for 404s. Also switched to `time.perf_counter()` (monotonic) for durations.
- **Lesson:** *"Metric labels must be bounded: never user IDs, raw URLs or emails."*

### Bug 3: RCA blamed the wrong service

- **Situation:** diagnosing `api-gateway` included an `ERROR` log from `billing`.
- **Root cause:** the filter was `service == X **or** level in (ERROR, CRITICAL)`, so any error from any service matched. Commits used substring matching (`service_name in c["service"]`).
- **Action:** logs must belong to the service **and** be ERROR/CRITICAL; commits are compared exactly (untagged commits are still kept as candidates). Added a regression test.
- **Lesson:** *"Boolean precedence and OR-vs-AND bugs are classic. Write the test with a negative case."*

### Bug 4: CI on `main` was red

- `ruff check` failed (`E501`, `I001` in `scripts/`) and `ruff format --check` reported 4 unformatted files, including `src/api/main.py`. Fixed, and the recommendation is a **pre-commit hook** so it cannot recur.

### Bug 5: container crashed on a read-only filesystem

- With `--read-only` + `--tmpfs /app/data`, `POST /v1/airflow/run-etl` threw `PermissionError: 'data/analytics'`. The tmpfs was root-owned while the app runs as UID 10001. Fixed with `uid=10001,gid=10001` (Docker) and `fsGroup` + `emptyDir` (Kubernetes).
- **Lesson:** *"Hardening (non-root, read-only) surfaces hidden assumptions about writable paths. Test the hardened container in CI, which is why the pipeline smoke test runs read-only."*

### Bug 6: TLS never issued in Kubernetes

- The Ingress had `cert-manager.io/cluster-issuer` and `ssl-redirect` annotations but **no `tls:` section**, so cert-manager never created a Certificate and HTTPS failed. Added `ingress.tls` to the values and the template.

### Bug 7: ArgoCD could not find the repository

- `repoURL` pointed at `UmaNagallaa/aegis-enterprise-ai` (wrong owner). Fixed to `Umanagalla27`, and `targetRevision: HEAD` changed to `main` (explicit is better than implicit).

### Bug 8: CORS misconfiguration

- `allow_origins=["*"]` with `allow_credentials=True` is a combination browsers reject for credentialed requests, and it is a security smell. Origins now come from `AEGIS_CORS_ORIGINS` (default `http://localhost:8000`), and credentials are disabled.

### Bug 9: Prometheus could not scrape the API on Linux

- `host.docker.internal` only resolves by default on Docker Desktop. Added `extra_hosts: host-gateway`; the production stack scrapes `api:8000` on the compose network instead.

### Bug 10: runtime network dependency in tiktoken

- `tiktoken.get_encoding("cl100k_base")` downloads a file on first use. In a locked-down network the chunking test failed with `ProxyError`. Fix: pre-fetch at build time with `TIKTOKEN_CACHE_DIR`. *"Any runtime download is a hidden dependency that breaks in air-gapped prod."* (The API image does not use the chunker, so it is not affected.)

### Bug 11: human approvals failed 30% of the time with several workers (the best story)

- **Situation:** the Docker image ran 2 gunicorn workers. Starting an incident and then approving it returned **404 "Unknown incident thread"** in 3 of 10 tries.
- **Root cause:** LangGraph's `MemorySaver` and the list of known threads lived in **one process's memory**. The approval request was load-balanced to the other worker, which had never seen the incident. With Kubernetes (3 pods × 2 workers) it gets worse. The same flaw duplicated incident IDs (each process counted from `INC-0001`) and gave every worker its own anomaly baseline.
- **Action:** `AEGIS_DATABASE_URL` switches the checkpointer to **`PostgresSaver`** (`src/agents/checkpointing.py`); "does this incident exist?" is now a checkpoint lookup. Baselines and rate-limit counters moved to **Redis**; incident IDs are random. The image defaults to 1 worker when no database is configured, and the Helm chart refuses to render several replicas without the secret.
- **Result:** **20/20** approvals across 4 workers; a paused incident survives a full restart. CI now runs the image with 3 workers against real Postgres/Redis (`scripts/smoke_test.sh`), and `tests/test_shared_state.py` resumes an incident from a second graph instance.
- **Lesson:** *"Workers and pods share nothing. Stateless app processes, state in a shared store. And test with more than one worker, because one worker hides this whole class of bugs."*

### Bug 12: worker startup race, then a deadlock (two rounds)

- **Round 1, situation:** with 4 workers, one crashed on boot: `psycopg.errors.UniqueViolation: duplicate key value violates unique constraint "pg_type_typname_nsp_index"`. Every worker ran the checkpoint schema setup (`CREATE TABLE ...`) at the same instant.
- **Round 1, action:** wrapped setup in `pg_advisory_lock()`. Tests passed.
- **Round 2, situation:** the full production stack on a **fresh** database came up `unhealthy`: every worker hung at startup until gunicorn killed it. `pg_stat_activity` showed one session in `CREATE INDEX CONCURRENTLY` and the others waiting in `pg_advisory_lock`.
- **Root cause:** a deadlock Postgres cannot detect. `CREATE INDEX CONCURRENTLY` waits for every open transaction to finish, and a worker *blocked inside* `pg_advisory_lock()` is an open transaction that waits for the lock holder. My first fix had only passed because of lucky timing.
- **Action:** waiting workers now **poll** `pg_try_advisory_lock()` with a short sleep, so they hold no transaction while waiting. A regression test starts 4 workers at once on a fresh schema: it fails ("worker startup deadlocked") on the old code and passes on the new one.
- **Lesson:** *"A fix that passes once isn't proven: concurrency bugs depend on timing. Reproduce them deterministically in a test, and look at `pg_stat_activity` / wait events instead of guessing. In larger systems, run migrations as a one-off job before the rollout instead of in every replica."*

### Bug 12b: a misleading "Worker exited with code 1"

- Gunicorn logged `Worker (pid:21) exited with code 1` at startup, yet both workers kept running. Taking `/proc` snapshots during boot showed pid 21 was Docker's **HEALTHCHECK** probe: it ran before the app was ready, exited 1, and was re-parented to PID 1, which was gunicorn. Fix: `init: true` (tini as PID 1). *"Containers need a real init as PID 1, or something else ends up reaping zombies."*

### Bug 13: `terraform validate` caught an apply-time failure

- The new security group description contained an apostrophe ("Let's Encrypt"), which AWS rejects. `terraform validate` flagged it without any AWS account; `apply` would have failed halfway. *"Run fmt and validate in CI; they are free and catch real errors."*

### Bug 14: supply-chain and CI findings (from the PR review)

- Trivy found 4 HIGH CVEs in `urllib3`/`msgpack`/`setuptools`, which the app never installs: they were **vendored inside pip**. Fix: remove pip from the runtime image.
- SonarCloud: actions referenced by movable tags (`@v3`), so every action is now pinned to a full commit SHA; and no `ephemeral-storage` limits, so limits were added.
- A teammate's PR landed first; after merging `main`, the container smoke test caught a missing `langgraph` dependency in the production image before it shipped.
- A `requirements.txt` produced by `pip freeze` on Windows (UTF-16, with `pywin32`) broke `pip install` on the Linux runner. Fix: a curated `requirements.txt` plus a `pip-compile` lock for the image. Re-running the failed job could never pass, because a re-run tests the same commit.

### Bug 15: the whole dashboard was dead, while every API test passed

- Clicking a tab in the web portal did nothing. The browser console showed `SyntaxError: Identifier 'anomaly' has already been declared`: a merge had left `const anomaly = ...` twice in one function. One syntax error makes the browser drop the **entire** `<script>`, so `switchTab` and every button handler were undefined.
- API tests use `TestClient` and never run the page's JavaScript, so CI stayed green. Found by clicking through the page in a headless Chromium (Playwright). Fix: remove the duplicate; a regression test now runs `node --check` on every inline script of `/`.
- *"Green API tests don't prove the UI works. Test what the user actually runs, at least a syntax check plus one browser smoke test."*

---

## 6. Known limitations (say these before the interviewer finds them)

1. **One shared API key, no per-user identity.** Anyone with the key can approve a rollback, and `reviewer` is whatever the caller sends. Next step: OIDC/JWT login and RBAC so only on-call SREs can approve, with the reviewer taken from the token.
2. **Heavy work runs inside requests** (`/v1/eval/*`, `/v1/airflow/run-etl`). Measured at ~1.4 s at most, so a job queue would be over-engineering today; rate limits stop abuse. If jobs grow, the pattern is a queue + workers returning `202 Accepted` and a job ID.
3. **Simulated components** (section 1).
4. **Not applied to a real cloud:** Helm and Terraform are validated (`helm lint`, `terraform validate`), but not run against a live cluster/account in this repo.
5. The retriever index is rebuilt in memory at startup and RCA reports are returned, not stored.

---

## 7. Upgrades that make the project stronger (pick 1–2)

| Upgrade | Effort | Interview value |
| :--- | :--- | :--- |
| Real embeddings (`sentence-transformers/all-MiniLM-L6-v2`) or pgvector for the dense side; measure recall@k before and after | 1–2 days | Very high: real RAG evaluation numbers |
| Real LLM call (Claude or an open model) in the RCA/triage node, with structured output (`StructuredTriageOutput` already exists) + eval gate | 1–2 days | Very high for GenAI roles |
| OIDC login (per-user approvals with RBAC) | 1–2 days | High: real authorization story |
| Real `mlflow` client logging eval runs | half a day | Medium |
| Deploy Option A (VM + domain + HTTPS) and put the live URL on your resume | half a day | High: recruiters can click it |

---

## 8. Interview questions and model answers

### System design and architecture

**Q: Walk me through a request to `/v1/incidents/diagnose`.**
Pydantic validates the body (otherwise 422). The handler sets severity from latency (> 1000 ms is CRITICAL). `RootCauseAnalysisAgent` filters error logs for that service, correlates recent commits, sets P1/P2, builds a root-cause hypothesis and action plan, picks a runbook, and computes the blast radius. The middleware records count and latency metrics. JSON comes back.

**Q: How would you scale this to 10× traffic?**
The pods are already stateless (HITL state in Postgres, baselines and rate limits in Redis), so the HPA can add replicas (3 to 10). Then: load-test with k6 or Locust to find the real bottleneck, watch Postgres connections (pool size × pods; add PgBouncer), cache retrieval results in Redis, and move any job that grows beyond a few seconds to a queue.

**Q: Why did you need human-in-the-loop?**
A wrong rollback during a P1 can extend the outage. The agent does the toil (correlation, runbook lookup, plan) and a human makes the irreversible decision. LangGraph `interrupt()` pauses the graph with checkpointed state; `Command(resume={"approved": True})` continues it.

**Q: What is Reciprocal Rank Fusion?**
`score(d) = Σ 1 / (k + rank_m(d))` across retrievers, with k = 60. It fuses by rank, so BM25 scores (unbounded) and cosine scores (0 to 1) need no normalization, and a document ranked well by both retrievers rises.

**Q: How does the blast radius work?**
Edges point from dependent to dependency (`api-gateway → auth-service`). The services impacted when X fails are those that (transitively) depend on X: `nx.descendants(graph.reverse(), X)`. For `aegis-postgres` that gives rag-retrieval, db-writer, auth-service and api-gateway.

### ML / AI

**Q: Explain scaled dot-product attention. Why divide by √dₖ?**
`softmax(QKᵀ/√dₖ)V`. Dot products grow with dimension, and large logits saturate softmax (tiny gradients). Scaling keeps the variance around 1.

**Q: Pre-LN vs Post-LN?**
Pre-LN normalizes before each sublayer (`x + f(LN(x))`). Gradients flow through the residual path unnormalized, so training is more stable without long warm-up.

**Q: Isolation Forest intuition?**
Anomalies are few and different, so random splits isolate them in fewer steps (shorter average path length gives a more anomalous score). `contamination` sets the expected outlier fraction, which sets the threshold.

**Q: How would you evaluate the RAG system?**
Retrieval: recall@k / MRR on a labelled query-to-runbook set. Generation: faithfulness (claims supported by context), answer relevance. Gate them in CI (this project gates faithfulness ≥ 0.85, recall ≥ 0.80) and track them over time.

**Q: How do you defend against prompt injection?**
Defense in depth: input signature detection (here), tool allowlists per agent role (the agent cannot call what it is not allowed to, even if tricked), HITL on destructive tools, output filtering, and never putting secrets in prompts. Regex alone is bypassable; layering matters.

### DevOps / production

**Q: Walk me through your CI/CD pipeline.**
See deployment guide Phase 5: lint, tests (including Postgres/Redis tests against service containers), eval gates, chaos benchmark, then build the image from a hashed lock file, run it read-only with 3 workers against Postgres/Redis and run the smoke test (20 approvals), scan with Trivy, push `:<sha>` (and `:X.Y.Z` on release tags) to GHCR. ArgoCD deploys what Git says: staging first, then the same tag to production.

**Q: Why tag images with the commit SHA instead of `latest`?**
`latest` is mutable: you cannot tell what is running, rollbacks are ambiguous, and nodes may cache different `latest`s. A SHA is immutable and traceable to the exact code.

**Q: Liveness vs readiness vs startup probes?**
Startup: protects slow boots. Readiness: controls whether the pod gets traffic. Liveness: restarts a stuck container. Common mistake: a liveness probe that checks the database, so a DB blip restarts every pod (cascading failure). Liveness should only check the process itself.

**Q: A deploy went out and the error rate jumped. What do you do?**
Mitigate first: roll back (`git revert`, so ArgoCD syncs, or `helm rollback`). Then investigate with logs, the diff between versions, and metrics per endpoint. Fix it with a regression test, redeploy through the pipeline, write a blameless postmortem.

**Q: Pod is in CrashLoopBackOff. Steps?**
`kubectl describe pod` (events, exit code; 137 means OOM), `kubectl logs --previous` (the crash output), check env/config/secrets, then reproduce locally with the same image tag.

**Q: How do you manage secrets?**
Never in Git or the image. Kubernetes Secrets synced from a manager (AWS Secrets Manager or Vault via External Secrets), OIDC for CI instead of static keys, least privilege, rotation.

**Q: What would you monitor?**
Golden signals: p95/p99 latency, RPS, 5xx rate, CPU/memory saturation, plus domain metrics (anomalies detected, HITL approvals pending, time-to-approval). Alert on SLO burn rate, not raw CPU.

**Q: What is high cardinality, and have you hit it?**
Yes, Bug 2 above.

### Python / coding

**Q: Why might a FastAPI endpoint block the server?**
`async def` handlers run on the event loop: blocking calls in them (CPU work, `time.sleep`, sync DB drivers) freeze all requests. Plain `def` handlers run in a threadpool (which is why this project's CPU-bound handlers are `def`). Very heavy work belongs in background workers.

**Q: Is your rolling baseline safe with concurrent requests and several workers?**
Yes. With Redis, each sample is appended with `LPUSH` + `LTRIM` in one pipeline, so the window is capped atomically and shared by every worker and pod. Each request fits a fresh engine from a snapshot of the window, so there is no shared model object to corrupt. Two concurrent requests may read windows that differ by one sample, which is fine for a statistical baseline.

**Q: How do you secure the API?**
`X-API-Key` on every `/v1` route via a global FastAPI dependency (constant-time comparison); `/health` and `/metrics` stay open for probes and Prometheus. Heavy endpoints are rate limited per client with counters in Redis, so the limit holds across workers. Behind a proxy, `FORWARDED_ALLOW_IPS` makes the limiter see the real client IP. Next step: OIDC with per-user RBAC for approvals.

**Q: A user says "I got an error". How do you find it?**
Ask for the `X-Request-ID` from the response, then search the JSON logs for it: every line written while handling that request carries the ID. With tracing on, the same request is a trace in Jaeger/Tempo.

**Q: What does Pydantic give you here?**
Request validation and automatic 422 errors with field-level messages, type coercion, OpenAPI schema generation, and in the Kafka producer, schema enforcement that routes bad events to the DLQ.

---

## 9. Practice drills (do these before interviews)

1. Break it on purpose, then fix it: delete `USER aegis` from the Dockerfile and set `runAsNonRoot: true`. Observe `CreateContainerConfigError` in kind, explain it, fix it.
2. Set the readiness probe path to `/healthz`, deploy, and watch the Service lose endpoints (`kubectl get endpoints`). Explain the 503.
3. Set `resources.limits.memory: 64Mi` and watch `OOMKilled`.
4. Revert the cardinality fix locally, hit 1,000 random URLs, and look at `/metrics` size before and after.
5. Run the warm-up `curl` loop from deployment guide Phase 1.5 and explain why the 21st request for a service is the first one with `"status": "SCORED"`.
6. Run the image with `-e WEB_CONCURRENCY=2` and **no** `AEGIS_DATABASE_URL`, run `scripts/smoke_test.sh http://localhost:8000 "" 10`, and watch approvals fail. Then add Postgres and watch them pass. Explain why.
7. Set `AEGIS_API_KEY`, call `/v1/rag/search` without the header (`401`), then with it; call `/v1/eval/ragas` 11 times in a minute (`429`).
