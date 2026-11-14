import { AGENTS, ORDER } from '../mock/meta';
import type { AgentId, AgentRun, CaseFile, StageId, Verdict } from '../mock/types';

export type StageStatus = 'pending' | 'running' | 'done' | 'flag' | 'requeued';

/** Status of every stage at timeline offset `t` (t < 0 means the run has not started). */
export function stageStatuses(c: CaseFile, t: number, decided: boolean): Record<StageId, StageStatus> {
  const out = {} as Record<StageId, StageStatus>;
  for (const id of ORDER) {
    if (id === 'review') {
      out.review = t < c.duration ? 'pending' : decided ? 'done' : 'running';
      continue;
    }
    const ws = c.windows.filter((w) => w.stage === id);
    if (ws.some((w) => t >= w.at && t < w.at + w.dur)) {
      out[id] = 'running';
      continue;
    }
    const ended = ws.filter((w) => w.at + w.dur <= t);
    if (!ended.length) {
      out[id] = 'pending';
      continue;
    }
    // An earlier stage that restarted after this one last ran sends it back to waiting (the Judge loop).
    const lastStart = Math.max(...ended.map((w) => w.at));
    const idx = ORDER.indexOf(id);
    const restarted = c.windows.some((w) => ORDER.indexOf(w.stage) < idx && w.at > lastStart && w.at <= t);
    out[id] = restarted ? 'requeued' : c.flags.includes(id) ? 'flag' : 'done';
  }
  return out;
}

export function activeStage(status: Record<StageId, StageStatus>): StageId | null {
  return ORDER.find((id) => status[id] === 'running') ?? null;
}

export interface LaneState {
  state: 'idle' | 'skipped' | 'queued' | 'running' | 'done';
  verdict?: Verdict;
  short?: string;
  round?: number;
  reason?: string;
}

export function laneStates(c: CaseFile, t: number): Record<AgentId, LaneState> {
  const planWindow = c.windows.find((w) => w.stage === 'plan')!;
  const planned = t >= planWindow.at + planWindow.dur;
  const out = {} as Record<AgentId, LaneState>;
  for (const { id } of AGENTS) {
    const d = c.plan.dispatch.find((x) => x.agent === id);
    if (d?.skipped) {
      out[id] = planned ? { state: 'skipped', reason: d.skipped } : { state: 'idle' };
      continue;
    }
    const started = c.runs.filter((r) => r.agent === id && r.at <= t);
    const last = started[started.length - 1];
    if (!last) {
      out[id] = { state: planned ? 'queued' : 'idle' };
    } else if (t < last.at + last.dur) {
      out[id] = { state: 'running', round: last.round };
    } else {
      out[id] = { state: 'done', verdict: last.verdict, short: last.short, round: last.round };
    }
  }
  return out;
}

export function currentRound(c: CaseFile, t: number): number {
  const started = c.windows.filter((w) => w.round && w.at <= t);
  return started.length ? Math.max(...started.map((w) => w.round!)) : 1;
}

export function runsStarted(c: CaseFile, t: number): AgentRun[] {
  return c.runs.filter((r) => r.at <= t);
}

/** True while the Judge has asked for another round and the pipeline is looping back. */
export function loopState(c: CaseFile, t: number): 'unused' | 'active' | 'used' {
  const second = c.windows.find((w) => w.stage === 'agents' && (w.round ?? 1) > 1);
  if (!second) return 'unused';
  const firstJudge = c.windows.find((w) => w.stage === 'judge' && (w.round ?? 1) === 1)!;
  if (t < firstJudge.at + firstJudge.dur - 900) return 'unused';
  if (t < second.at + 1600) return 'active';
  return 'used';
}

export const fmtClock = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
};
