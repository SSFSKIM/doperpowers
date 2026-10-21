# application-agents/

`triaging-feedback/` is this directory's; `infra/worker-host/` is at the repository's root.

Deployed agent applications that are not skills — nothing invokes them by name from a session. `triaging-feedback/`: the feedback→triage poller (TypeScript, its own `npm test`), its worker protocol, and setup docs; `infra/worker-host/` describes the host that ran it (none runs today).
