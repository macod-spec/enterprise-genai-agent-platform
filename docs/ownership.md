# Service ownership and escalation

Repository roles are placeholders for a real organisation and must be replaced by
named teams and paging destinations before deployment.

| Responsibility | Accountable role | Escalation trigger |
|---|---|---|
| Platform service and Kubernetes | GenAI Platform Engineering | Availability or latency budget burn |
| Agent behaviour and evaluation | AI Engineering | Evaluation regression or unsafe routing |
| Identity, MCP and supply chain | Security Engineering | Auth bypass, secret exposure or critical finding |
| Data use and retention | Data Protection Officer | Personal-data or retention-policy concern |
| Model approval | Model Risk Management | Material model/prompt/provider change |
| Business workflow | Operations Product Owner | Incorrect decision or approval backlog |
| Incident command | Production Operations | Severity 1 or cross-service incident |

Every alert needs a primary owner, secondary owner, paging route and maintenance
window before production. No single engineer may both approve a high-risk agent
change and its production release.
