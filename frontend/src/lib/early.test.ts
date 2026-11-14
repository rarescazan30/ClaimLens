import { describe, expect, it } from 'vitest';
import { contributionTitle, failedPolicyRules, flagLine, isNewClaim, runModeText } from './early';
import type { ApiFlag } from './types';

const flag = (over: Partial<ApiFlag> = {}): ApiFlag => ({ step: 'policy', code: 'policy_active', field: null, severity: 'fail', reason: 'Policy not active', ...over });

describe('early checks helpers', () => {
  it('lists a paused claim with the new ones', () => {
    expect(['received', 'investigating', 'paused'].every((s) => isNewClaim(s as never))).toBe(true);
    expect(isNewClaim('awaiting_decision')).toBe(false);
    expect(isNewClaim('decided')).toBe(false);
  });

  it('words the run mode', () => {
    expect(runModeText('live')).toBe('Live run');
    expect(runModeText('record')).toBe('Live run');
    expect(runModeText('replay')).toBe('Replayed from saved answers');
    expect(runModeText(null)).toBeNull();
  });

  it('names a client score line by its reason and an agent line by the agent', () => {
    expect(contributionTitle({ agent: 'client', reason: 'phone number is invalid' })).toBe('Client data: phone number is invalid');
    expect(contributionTitle({ agent: 'meteo', reason: null })).toBe('Weather');
  });

  it('takes the failed policy rules from the check items, else from the flags', () => {
    const items = [
      { id: 'a', at: 0, label: 'Policy active', status: 'fail' as const, note: 'Expired' },
      { id: 'b', at: 0, label: 'Peril covered', status: 'ok' as const },
    ];
    expect(failedPolicyRules({ details: { policy: items }, flags: [] })).toEqual([{ label: 'Policy active', reason: 'Expired' }]);
    expect(failedPolicyRules({ details: {}, flags: [flag(), flag({ step: 'client', reason: 'x' })] })).toEqual([{ label: 'policy_active', reason: 'Policy not active' }]);
  });

  it('writes a flag as "[step] reason"', () => {
    expect(flagLine(flag({ step: 'client', reason: 'CNP checksum fails' }))).toBe('[client] CNP checksum fails');
  });
});
