# AegisAI: Responsible AI System Card

- **Intended Use:** Autonomous monitoring, triage, and root cause analysis of IT infrastructure incidents.
- **Human Oversight:** High-impact remediation actions (rollbacks, pod restarts) require human authorization via HITL.
- **Fairness & Bias:** Incident severity is determined strictly from technical metrics (error codes, latency) rather than user metadata.
- **Security & Privacy:** Inputs are scrubbed of PII via Microsoft Presidio patterns; prompt injections trigger immediate quarantine.
