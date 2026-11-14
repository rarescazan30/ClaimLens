import { AGENTS, ORDER } from './meta';
import type { AgentId, AgentRun, CaseFile, StageId, Verdict } from './types';

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
    out[id] = restarted ? 'requeued' : c.flaggedStages.includes(id) ? 'flag' : 'done';
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
  const planWindow = c.windows.find((w) => w.stage === 'plan');
  const planned = !!planWindow && t >= planWindow.at + planWindow.dur;
  const out = {} as Record<AgentId, LaneState>;
  for (const { id } of AGENTS) {
    if (c.plan.dispatch.find((x) => x.agent === id)?.skipped) {
      out[id] = planned ? { state: 'skipped', reason: 'Nu este relevant pentru acest tip de daună' } : { state: 'idle' };
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

/** Whether the Judge has sent agents back: 'active' around the moment a later round starts, 'used' after. */
export function loopState(c: CaseFile, t: number): 'unused' | 'active' | 'used' {
  const later = c.windows.filter((w) => w.stage === 'agents' && (w.round ?? 1) > 1 && w.at - 900 <= t);
  if (!later.length) return 'unused';
  return t < later[later.length - 1].at + 1600 ? 'active' : 'used';
}

/** The backend's score at timeline offset `t`, or undefined before the first one. */
export function scoreAt(c: CaseFile, t: number) {
  const seen = c.scores.filter((s) => s.at <= t);
  return seen.length ? seen[seen.length - 1] : undefined;
}

export const fmtClock = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
};
