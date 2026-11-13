# Working together

Deadline: **Saturday 14 November 2026, 14:00**. Keep `main` demo-ready at all times.

## Branches and PRs
- Branch from `main`: `<initials>/<short-topic>` (e.g. `rc/meteo-agent`).
- Small PRs, merged fast. One teammate glances at it; don't block on long reviews tonight.
- Never commit secrets. API keys go in a local `.env` (git-ignored).

## Where things go
| Folder | Owner (role) | What |
| --- | --- | --- |
| `maestro/` | A — Maestro + IXP | Case / BPMN definitions, IXP extraction, F1 rules |
| `agents/` | B — agents | One folder per specialist agent |
| `orchestrator/` | B — agents | Orchestrator + Judge loop |
| `ui/` | C — UI | Adjuster app: queue, case screen, trace, map |
| `data-fabric/` | A + C | Entity definitions |
| `demo/` | All | Demo cases, cached API responses, backup video |
| `docs/` | D — pitch | Proposal, contracts, architecture, pitch and Q&A |

## Rules for tonight
- Each agent works in isolation before it is wired into the loop.
- Cache every API response the demo uses, so it does not depend on Wi-Fi.
- Formats in [`docs/contracts.md`](docs/contracts.md) are shared — announce changes before making them.
- Be honest in the pitch about which agents are live and which use pre-captured data.
- Sleep in shifts.
