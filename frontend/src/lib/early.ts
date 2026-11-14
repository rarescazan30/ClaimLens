import type { ApiContribution, ApiFlag, CaseFile, ClaimStatus } from './types';
import { agentName, STAGES } from './meta';

/** Claims that still wait for the adjuster to start or continue them: new, running, or paused after a failed rule. */
export const isNewClaim = (status: ClaimStatus) => status === 'received' || status === 'investigating' || status === 'paused';

/** The chip next to the case header: how the run was served. Nothing when the backend did not say. */
export function runModeText(mode: CaseFile['runMode']): string | null {
  if (mode === 'live' || mode === 'record') return 'Rulare live';
  if (mode === 'replay') return 'Răspunsuri salvate';
  return null;
}

/** Name of a score line: a `client` line carries its own reason from the backend, any other is an agent. */
export function contributionTitle(k: Pick<ApiContribution, 'agent' | 'reason'>): string {
  return k.agent === 'client' ? `Date client: ${k.reason ?? 'verificările datelor clientului'}` : agentName(k.agent);
}

export interface FailedRule {
  label: string;
  reason: string;
}

/** The policy rules that failed, as the backend reported them: failed check items first, else the policy flags. */
export function failedPolicyRules(c: Pick<CaseFile, 'details' | 'flags'>): FailedRule[] {
  const items = (c.details.policy ?? []).filter((i) => i.status === 'fail');
  if (items.length) return items.map((i) => ({ label: i.label, reason: i.note ?? i.value ?? '' }));
  return c.flags.filter((f) => f.step === 'policy').map((f) => ({ label: f.field ?? f.code, reason: f.reason }));
}

export const stepName = (step: string) => STAGES.find((s) => s.id === step)?.short ?? step;

/** One line of a flag for the Arbitru list: "[Pas] motiv". */
export const flagLine = (f: ApiFlag) => `[${stepName(f.step)}] ${f.reason}`;
