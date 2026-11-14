import { describe, expect, it } from 'vitest';
import type { ApiClaimDetail, ApiTraceStep } from '../lib/types';
import { buildCase, buildQueueRow, OPEN } from './build';
import flood from './fixtures/flood.json';
import paused from './fixtures/paused.json';
import storm from './fixtures/storm.json';

/**
 * The fixtures are real responses of the backend (GET /claims/{id} and /trace) for the two demo claims,
 * recorded from a backend running on saved responses. Long previews were cut; nothing else was changed.
 */
const load = (f: unknown) => structuredClone(f) as { detail: ApiClaimDetail; trace: ApiTraceStep[] };

describe('buildCase: flood claim C-1042 (three rounds)', () => {
  const { detail, trace } = load(flood);
  const c = buildCase(detail, trace);

  it('shows the scores the backend computed, round by round, and nothing else', () => {
    expect(c.scores.map((s) => s.score)).toEqual(detail.score_history.map((h) => h.score));
    expect(c.scores.map((s) => s.band)).toEqual(detail.score_history.map((h) => h.band));
    expect(c.scores[c.scores.length - 1].recommendation).toBe(detail.score!.recommendation);
  });

  it('lays the stages end to end with no gap, in the order the backend ran them', () => {
    expect(c.windows.map((w) => w.stage)).toEqual(['intake', 'policy', 'plan', 'agents', 'judge', 'agents', 'judge', 'agents', 'judge', 'verdict']);
    for (let i = 1; i < c.windows.length; i++) expect(c.windows[i].at).toBe(c.windows[i - 1].at + c.windows[i - 1].dur);
    expect(c.duration).toBe(c.windows[c.windows.length - 1].at + c.windows[c.windows.length - 1].dur);
  });

  it('paces a run that was answered from saved responses so it can be watched', () => {
    expect(c.paced).toBe(true);
    expect(c.duration).toBeGreaterThan(20_000);
    expect(c.duration).toBeLessThan(90_000);
  });

  it('has one run per agent per round, each ending inside its round', () => {
    expect(c.runs.filter((r) => r.round === 1).map((r) => r.agent).sort()).toEqual(['meteo', 'news', 'photo_forensics', 'risk_zones', 'satellite', 'street_view']);
    expect(c.runs.filter((r) => r.round === 2).map((r) => r.agent).sort()).toEqual(['meteo', 'risk_zones']);
    for (const r of c.runs) {
      const w = c.windows.find((x) => x.stage === 'agents' && x.round === r.round)!;
      expect(r.at).toBeGreaterThanOrEqual(w.at);
      expect(r.at + r.dur).toBeLessThanOrEqual(w.at + w.dur);
    }
  });

  it('keeps an agent that reported without calling any source (no photos on file)', () => {
    const run = c.runs.find((r) => r.agent === 'photo_forensics')!;
    expect(run.calls).toEqual([]);
    expect(run.verdict).toBe('inconclusive');
    expect(run.short).toBe('Fără fotografii');
  });

  it('reads the key numbers from the measured findings', () => {
    expect(c.runs.find((r) => r.agent === 'satellite' && r.round === 1)!.short).toBe('La 150 m de zona inundată');
    expect(c.runs.find((r) => r.agent === 'risk_zones' && r.round === 2)!.short).toBe('13 m peste nivelul apei');
    expect(c.runs.find((r) => r.agent === 'meteo' && r.round === 1)!.short).toBe('47,9 mm în 24 h');
  });

  it('marks a source that failed as failed', () => {
    const gdelt = c.runs.find((r) => r.agent === 'news' && r.round === 1)!.calls[0];
    expect(gdelt.tool).toBe('GDELT');
    expect(gdelt.status).toBe('fail');
  });

  it('carries every evidence row with its backend id', () => {
    expect(c.evidence.map((e) => e.id)).toEqual(detail.evidence.map((e) => e.id));
    for (const e of c.evidence) expect(e.at).toBeLessThanOrEqual(c.duration);
  });

  it('reads the Judge decisions: send agents back twice, then stop', () => {
    expect(c.judge.map((j) => !!j.redispatch)).toEqual([true, true, false]);
    expect(c.judge[0].redispatch!.map((r) => r.agent)).toEqual(['risk_zones', 'meteo']);
    expect(c.judge[2].stop).toBe('Limita de 3 runde a fost atinsă.');
    expect(c.judge[0].hypotheses.find((h) => h.id === 'H2')!.mark).toBe('conflicting');
  });

  it('a stopped Judge shows what it concluded, not only why it stopped', () => {
    expect(c.judge[2].summary).toContain('Clientul declară');
    expect(c.judge[2].summary).toContain('Limita de 3 runde');
  });

  it('has real map data: house outside the mapped flood, 13 m higher', () => {
    expect(c.map).toBeDefined();
    expect(c.map!.inside).toBe(false);
    expect(Math.round(c.map!.distanceM!)).toBe(150);
    expect(c.map!.elevationDiffM).toBe(13);
    expect(c.map!.water!.name).toBe('Suhurlui');
    expect(c.map!.elevationAt!).toBeGreaterThan(c.map!.zoneAt);
  });

  it('shows the five policy rules as the backend judged them', () => {
    expect(c.details.policy!.map((i) => i.status)).toEqual(['ok', 'ok', 'ok', 'ok', 'ok']);
    expect(c.rulesPassed).toBe(true);
    expect(c.flags).toEqual([]);
  });
});

describe('buildCase: storm claim C-1038', () => {
  const { detail, trace } = load(storm);
  const c = buildCase(detail, trace);

  it('has no map and marks the two flood-only agents as not dispatched', () => {
    expect(c.map).toBeUndefined();
    expect(c.plan.dispatch.filter((d) => d.skipped).map((d) => d.agent)).toEqual(['satellite', 'risk_zones']);
  });

  it('leads the weather finding with gusts, not rain', () => {
    expect(c.runs.find((r) => r.agent === 'meteo')!.short).toBe('Rafale de 90,4 km/h');
  });
});

describe('buildCase: states of a claim', () => {
  it('a claim that was never investigated has only the claim itself', () => {
    const { detail } = load(storm);
    detail.claim.status = 'received';
    detail.evidence = [];
    detail.score = null;
    detail.hypotheses = [];
    detail.rule_flags = [];
    const c = buildCase(detail, []);
    expect(c.windows.map((w) => w.stage)).toEqual(['intake']);
    expect(c.scores).toEqual([]);
    expect(c.runs).toEqual([]);
  });

  it('a running investigation keeps its current stage open and its unfinished agents running', () => {
    const { detail, trace } = load(flood);
    detail.claim.status = 'investigating';
    const cut = trace.findIndex((s) => s.step_id === 'r1.risk_zones.1');
    detail.evidence = detail.evidence.filter((e) => e.round === 1 && (e.agent === 'meteo' || e.agent === 'satellite'));
    detail.score = null;
    const c = buildCase(detail, trace.slice(0, cut + 1));
    const last = c.windows[c.windows.length - 1];
    expect(last.stage).toBe('agents');
    expect(last.dur).toBe(OPEN);
    expect(c.duration).toBe(OPEN);
    expect(c.paced).toBe(false);
    expect(c.runs.find((r) => r.agent === 'meteo')!.dur).toBeLessThan(OPEN);
    expect(c.runs.find((r) => r.agent === 'risk_zones')!.dur).toBe(OPEN);
    expect(c.runs.find((r) => r.agent === 'news')!.dur).toBe(OPEN);
  });

  it('a question asked much later is laid right after the first run, not minutes away', () => {
    const { detail, trace } = load(storm);
    const later = (s: string) => new Date(Date.parse(s) + 3_600_000).toISOString().replace('.000Z', 'Z');
    const extra: ApiTraceStep[] = [
      { step_id: 'r2.question', actor: 'adjuster', type: 'decision', summary: 'Întrebare', outputs: { question: 'De ce?', agent: 'meteo' } },
      { step_id: 'r3.dispatch', actor: 'orchestrator', type: 'decision', summary: 'Runda 3', outputs: { agents: [{ agent: 'meteo', question: 'De ce?' }] } },
      { step_id: 'r3.meteo.1', actor: 'agent:meteo', type: 'observation', summary: 'Răspuns', outputs: { verdict: 'supports' } },
      { step_id: 'r3.score', actor: 'score', type: 'observation', summary: 'Scor', outputs: { score: 81, band: 'likely', recommendation: 'standard_review', contributions: [], gates: [] } },
      { step_id: 'r3.judge', actor: 'judge', type: 'decision', summary: 'Stop', outputs: { marks: {}, tensions: [], action: 'stop', redispatch: [], stop_reason: 'Gata.' } },
      { step_id: 'r3.final', actor: 'engine', type: 'escalation', summary: 'Final', outputs: {} },
    ].map((s) => ({ case_id: 'C-1038', parent: null, inputs: {}, sources: [], status: 'done', started_at: later(trace[0].started_at), ended_at: later(trace[0].started_at), ...s }) as ApiTraceStep);
    const before = buildCase(detail, trace);
    const c = buildCase(detail, [...trace, ...extra]);
    expect(c.questions).toEqual([{ text: 'De ce?', agent: 'meteo', round: 3, at: before.duration }]);
    expect(c.duration - before.duration).toBeLessThan(15_000);
    expect(c.windows.filter((w) => w.stage === 'verdict')).toHaveLength(2);
  });

  it('uses the stored score once a finding was set aside', () => {
    const { detail, trace } = load(flood);
    detail.evidence.find((e) => e.agent === 'risk_zones' && e.round === 2)!.rejected_by_adjuster = true;
    detail.score = { ...detail.score!, score: 73.2, band: 'likely', recommendation: 'standard_review' };
    const c = buildCase(detail, trace);
    expect(c.scores[c.scores.length - 1].score).toBe(73.2);
    expect(c.scores[0].score).toBe(78.2);
    expect(c.evidence.filter((e) => e.rejected)).toHaveLength(1);
  });

  it('reads the decision the adjuster recorded', () => {
    const { detail, trace } = load(flood);
    detail.claim = { ...detail.claim, status: 'decided', decision: 'modify', outcome: 'standard_review', decision_reason: 'Site visit already done', decided_at: '2026-11-14T01:00:00Z' };
    const c = buildCase(detail, trace);
    expect(c.decision).toMatchObject({ kind: 'modify', outcome: 'standard_review', reason: 'Site visit already done' });
  });
});

describe('buildCase: the five early steps and the pause', () => {
  const pausedFile = load(paused);
  const p = buildCase(pausedFile.detail, pausedFile.trace);

  /** The paused run continued by the adjuster: the investigation follows right after the pause. */
  const continuedFile = () => {
    const { detail, trace } = load(paused);
    detail.claim.status = 'awaiting_decision';
    const t = '2026-11-14T09:05:00Z';
    const step = (step_id: string, actor: string, type: ApiTraceStep['type'], summary: string, outputs: Record<string, unknown>) =>
      ({ case_id: 'C-1042', parent: null, inputs: {}, sources: [], status: 'done', started_at: t, ended_at: t, step_id, actor, type, summary, outputs }) as ApiTraceStep;
    const score = { score: 40, band: 'uncertain', recommendation: 'standard_review', contributions: [{ agent: 'client', round: 0, delta_logit: -0.25, reason: 'CNP-ul din cerere nu are un format valid' }], gates: [] };
    detail.score = score as ApiClaimDetail['score'];
    detail.score_history = [{ round: 1, score: 40, band: 'uncertain' }];
    return {
      detail,
      trace: [
        ...trace,
        step('continue', 'adjuster', 'decision', 'Continuare', { failed_rules: ['policy_active'] }),
        step('plan', 'orchestrator', 'decision', 'Plan', { hypotheses: [] }),
        step('r1.dispatch', 'orchestrator', 'decision', 'Runda 1', { agents: [{ agent: 'meteo', question: 'Plouă?' }] }),
        step('r1.meteo.1', 'agent:meteo', 'observation', 'Răspuns', { verdict: 'supports' }),
        step('r1.score', 'score', 'observation', 'Scor', score),
        step('r1.judge', 'judge', 'decision', 'Stop', { marks: {}, tensions: [], action: 'stop', redispatch: [], stop_reason: 'Gata.' }),
        step('final', 'engine', 'escalation', 'Final', {}),
      ],
    };
  };
  const cf = continuedFile();
  const c = buildCase(cf.detail, cf.trace);

  it('lays the five early steps before the plan', () => {
    expect(c.windows.map((w) => w.stage).slice(0, 6)).toEqual(['intake', 'documents', 'client', 'policy', 'photos', 'plan']);
    for (let i = 1; i < c.windows.length; i++) expect(c.windows[i].at).toBe(c.windows[i - 1].at + c.windows[i - 1].dur);
  });

  it('a paused claim stops after the photo check and names the failed rule', () => {
    expect(p.status).toBe('paused');
    expect(p.paused).toEqual({ rules: ['policy_active'] });
    expect(p.windows[p.windows.length - 1].stage).toBe('photos');
    expect(p.scores).toEqual([]);
    expect(p.runMode).toBe('live');
    expect(p.flaggedStages).toEqual(['client', 'policy', 'photos']);
  });

  it("shows each step's check items from the backend", () => {
    expect(p.details.client!.map((i) => i.status)).toContain('flag');
    expect(p.details.client![1]).toMatchObject({ label: 'CNP', value: '123', status: 'flag', note: 'CNP-ul din cerere nu are un format valid' });
    expect(p.details.policy!.map((i) => i.status)).toEqual(['fail', 'ok', 'ok', 'ok', 'ok']);
    expect(p.details.intake!.map((i) => i.id)).toEqual(['claim_id', 'amount', 'photos']);
    for (const stage of ['intake', 'documents', 'client', 'policy', 'photos'] as const) {
      const w = p.windows.find((x) => x.stage === stage)!;
      for (const i of p.details[stage]!) expect(i.at).toBeLessThanOrEqual(w.at + w.dur);
    }
  });

  it('carries flags, documents and the failed rule', () => {
    expect(p.flags.map((f) => f.code)).toEqual(['cnp_invalid', 'email_malformed', 'policy_active', 'no_photos']);
    expect(Object.keys(p.documents.claim_form!).length).toBeGreaterThan(0);
    expect(p.rulesPassed).toBe(false);
  });

  it('continuing lays the investigation right after the pause', () => {
    expect(c.paused).toBeUndefined();
    const stages = c.windows.map((w) => w.stage);
    expect(stages.slice(0, 7)).toEqual(['intake', 'documents', 'client', 'policy', 'photos', 'plan', 'agents']);
    expect(stages[stages.length - 1]).toBe('verdict');
    const photos = c.windows.find((w) => w.stage === 'photos')!;
    const plan = c.windows.find((w) => w.stage === 'plan')!;
    expect(plan.at).toBe(photos.at + photos.dur);
    expect(c.duration).toBeLessThan(40_000);
  });

  it('keeps the reason of a client score contribution', () => {
    expect(c.scores[0].contributions[0]).toMatchObject({ agent: 'client', reason: 'CNP-ul din cerere nu are un format valid' });
  });

  it('old runs without checks keep the synthesised intake facts and the policy rules', () => {
    const { detail, trace } = load(flood);
    const old = buildCase(detail, trace);
    expect(old.details.intake!.map((i) => i.label)).toContain('Număr dosar');
    expect(old.details.documents).toBeUndefined();
    expect(old.paused).toBeUndefined();
  });
});

describe('buildQueueRow', () => {
  it('fills the claimant, description and strongest signals from the claim detail', () => {
    const { detail } = load(flood);
    const row = buildQueueRow(
      { id: 'C-1042', address: detail.claim.address, damage_type: 'flood', event_date: '2024-09-14', status: 'awaiting_decision', score: 34.4, band: 'unlikely', recommendation: 'antifraud_referral', decision: null, outcome: null, created_at: '2026-11-14T00:48:34Z' },
      detail,
    );
    expect(row.claimant).toBe('Persoană Sintetică Unu');
    expect(row.place).toBe('Pechea, jud. Galați');
    expect(row.outcome).toBe('antifraud_referral');
    expect(row.signals[0]).toBe('Zone de risc: Casa este cu 13 m mai sus decât marginea inundației');
  });
});
