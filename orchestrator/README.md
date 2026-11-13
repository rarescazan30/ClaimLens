# orchestrator/

The agentic loop: **Orchestrator** (plans hypotheses, picks agents) + **Judge** (weighs evidence,
re-dispatches one agent with one narrow question). Two separate roles on purpose.

Planned as a coded agent (Python + LangGraph via `uipath-langchain`) or a Case Manager agent.

Loop: plan → dispatch (parallel) → judge → re-dispatch … → verdict.

Judge stops when any of:
- all critical hypotheses have a verdict;
- the score moved < 5 points between rounds;
- 3 rounds done;
- time / cost budget exceeded.

Scoring (log-odds, gates F1/F2, 5 factors, bands): see [`docs/proposal.md`](../docs/proposal.md#cei-5-factori).
