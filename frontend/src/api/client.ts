import type { ApiClaimDetail, ApiClaimRow, ApiScore, ApiTraceStep, Outcome } from '../lib/types';

/**
 * Every call the UI makes to the ClaimLens backend. Nothing else in the app uses fetch.
 * The address comes from VITE_API_URL (see .env.example); the default is the local backend.
 */
export const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/+$/, '');

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, `The backend at ${API_URL} is not reachable.`);
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === 'string') detail = body.detail;
    } catch {
      /* keep the status text */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

const post = (body?: unknown): RequestInit => ({
  method: 'POST',
  headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
});

const enc = encodeURIComponent;

/** GET /claims */
export const listClaims = () => call<ApiClaimRow[]>('/claims');
/** GET /claims/{id} */
export const getClaim = (id: string) => call<ApiClaimDetail>(`/claims/${enc(id)}`);
/** GET /claims/{id}/trace */
export const getTrace = (id: string) => call<ApiTraceStep[]>(`/claims/${enc(id)}/trace`);
/** POST /claims/{id}/rerun: erases the previous run and decision, then starts a fresh investigation. */
export const rerun = (id: string) => call<{ id: string; status: string }>(`/claims/${enc(id)}/rerun`, post());
/** POST /claims/{id}/question: one more round answering the adjuster's question. */
export const ask = (id: string, question: string) => call<{ id: string; status: string }>(`/claims/${enc(id)}/question`, post({ question }));
/** POST /claims/{id}/decision: approve the recommendation, or choose another outcome with a reason. */
export const decide = (id: string, body: { decision: 'approve' } | { decision: 'modify'; outcome: Outcome; reason: string }) =>
  call<{ id: string; status: string; outcome: Outcome }>(`/claims/${enc(id)}/decision`, post(body));
/** POST /claims/{id}/evidence/{evidenceId}/reject: set a finding aside. The backend has no way to restore it. */
export const rejectEvidence = (id: string, evidenceId: number) => call<ApiScore>(`/claims/${enc(id)}/evidence/${evidenceId}/reject`, post());
/** GET /claims/{id}/flood-extent: GeoJSON of the mapped flood (404 when the claim has none). */
export const getFloodExtent = (id: string) => call<GeoJSON>(`/claims/${enc(id)}/flood-extent`);
/** GET /photos/{name} */
export const photoUrl = (name: string) => `${API_URL}/photos/${name.split('/').map(enc).join('/')}`;
/** GET /claims/{id}/stream: server-sent events while an investigation runs. */
export const openStream = (id: string) => new EventSource(`${API_URL}/claims/${enc(id)}/stream`);

export interface GeoJSON {
  features: { geometry: { type: string; coordinates: unknown } | null }[];
}
