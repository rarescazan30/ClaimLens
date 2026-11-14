import type { Band, Evidence, Route } from '../mock/types';

const logit = (p: number) => Math.log(p / (1 - p));
const sigmoid = (x: number) => 1 / (1 + Math.exp(-x));

/** One finding's push on the score, in log-odds: weight × strength × quality × direction. */
export const contribution = (e: Evidence) => e.weight * e.strength * e.quality * e.direction;

/** logit(P) = logit(P0) + Σ contributions, shown as 0–100. */
export function computeScore(p0: number, evidence: Evidence[]): number {
  const x = logit(p0) + evidence.reduce((sum, e) => sum + contribution(e), 0);
  return Math.round(sigmoid(x) * 100);
}

export function bandOf(score: number): Band {
  if (score >= 85) return 'very-likely';
  if (score >= 65) return 'likely';
  if (score >= 35) return 'uncertain';
  return 'unlikely';
}

export function routeFor(score: number, gateTripped: boolean): Route {
  if (gateTripped) return 'investigate';
  const b = bandOf(score);
  if (b === 'very-likely') return 'fast-track';
  if (b === 'unlikely') return 'investigate';
  return 'standard';
}
