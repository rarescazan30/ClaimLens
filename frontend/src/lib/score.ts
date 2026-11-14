import type { ApiScore } from './types';

/**
 * The score, the band and the recommendation always come from the backend
 * (logit(P) = logit(P0) + sum of contributions, computed in backend/engine/score.py).
 * The helpers here only turn the backend's own numbers into "points" for the charts.
 */

const logit = (p: number) => Math.log(p / (1 - p));
const sigmoid = (x: number) => 1 / (1 + Math.exp(-x));
const clamp = (score: number) => Math.min(99.9, Math.max(0.1, score)) / 100;

/** How many points one contribution is worth: the score with it, minus the score without it. */
export function pointsOf(score: number, deltaLogit: number): number {
  if (!deltaLogit) return 0;
  return Math.round(score - sigmoid(logit(clamp(score)) - deltaLogit) * 100);
}

/** Where the score starts before any evidence: the backend's score with every contribution taken out. */
export function baseOf(s: ApiScore): number {
  const sum = s.contributions.reduce((a, c) => a + c.delta_logit, 0);
  return Math.round(sigmoid(logit(clamp(s.score)) - sum) * 100);
}

/** 34.4 -> "34.4", 80 -> "80". */
export const fmtScore = (score: number) => score.toFixed(1).replace(/\.0$/, '');
