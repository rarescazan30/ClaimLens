import { describe, expect, it } from 'vitest';
import { DEMO_HISTORY, isOpenable, verdictRows, withHistory } from './demoHistory';

describe('archived demo claims', () => {
  it('are grouped under verdict and cannot be opened', () => {
    const ids = verdictRows(withHistory([])).map((r) => r.id);
    expect(ids).toEqual(['C-7001', 'C-7002', 'C-7003']);
    expect(DEMO_HISTORY.some(isOpenable)).toBe(false);
  });
});
