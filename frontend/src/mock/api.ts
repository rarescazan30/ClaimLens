import { CASES, QUEUE } from './data';
import { agentName } from './meta';
import type { CaseFile, QueueCase, TraceEvent } from './types';

/**
 * The only file the UI talks to for data.
 * To connect the real backend, replace the bodies of these functions with fetch calls
 * (or an SSE / WebSocket stream for `getTrace`) and keep the return types.
 */

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function listQueue(): Promise<QueueCase[]> {
  await wait(60);
  return QUEUE;
}

export async function getCase(id: string): Promise<CaseFile | undefined> {
  await wait(60);
  return CASES[id];
}

/** The same run flattened into the trace-event format from the workflow doc. */
export async function getTrace(id: string): Promise<TraceEvent[]> {
  const c = CASES[id];
  if (!c) return [];
  const events: TraceEvent[] = [];
  for (const w of c.windows) {
    events.push({
      case_id: c.id,
      step_id: w.round ? `r${w.round}.${w.stage}` : w.stage,
      actor: w.stage === 'judge' ? 'agent:judge' : w.stage === 'plan' ? 'agent:orchestrator' : 'system',
      type: 'stage',
      summary: w.stage,
      status: 'done',
      started_at: w.at,
      ended_at: w.at + w.dur,
    });
  }
  for (const r of c.runs) {
    events.push({
      case_id: c.id,
      step_id: r.id,
      parent: `r${r.round}.agents`,
      actor: `agent:${r.agent}`,
      type: 'observation',
      summary: r.finding,
      outputs: { verdict: r.verdict, agent: agentName(r.agent) },
      status: 'done',
      started_at: r.at,
      ended_at: r.at + r.dur,
    });
    r.calls.forEach((call, i) =>
      events.push({
        case_id: c.id,
        step_id: `${r.id}.${i + 1}`,
        parent: r.id,
        actor: `agent:${r.agent}`,
        type: 'tool_call',
        summary: `${call.tool}: ${call.summary}`,
        sources: [call.tool],
        status: call.status === 'ok' ? 'done' : 'failed',
        started_at: call.at,
        ended_at: call.at + call.dur,
      }),
    );
  }
  for (const j of c.judge) {
    events.push({
      case_id: c.id,
      step_id: `r${j.round}.judge.decision`,
      parent: `r${j.round}.judge`,
      actor: 'agent:judge',
      type: j.redispatch ? 'escalation' : 'decision',
      summary: j.summary,
      status: 'done',
      started_at: j.at,
      ended_at: j.at + j.dur,
    });
  }
  return events.sort((a, b) => a.started_at - b.started_at);
}
