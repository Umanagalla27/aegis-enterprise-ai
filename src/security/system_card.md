# AegisAI: Responsible AI System Card

- **Intended Use:** Autonomous monitoring, triage, and root cause analysis of IT infrastructure incidents.
- **Human Oversight:** High-impact remediation actions (rollbacks, pod restarts) require human authorization via HITL.
- **Fairness & Bias:** Incident severity is determined strictly from technical metrics (error codes, latency) rather than user metadata.
- **Security & Privacy:** Inputs are scrubbed of PII (SSNs, card numbers, emails, phone numbers, API keys) with regex patterns; prompt injections matching known signatures trigger immediate quarantine. `/v1` endpoints require an API key in production.
