import { useCallback, useEffect, useRef, useState } from 'react';
import type { ApiClaimDetail, CaseFile, Outcome, QueueCase } from '../lib/types';
import { buildCase, buildQueueRow } from './build';
import * as api from './client';

// ---------------------------------------------------------------- queue

let queueCache: { at: number; rows: Promise<QueueCase[]> } | null = null;

/**
 * Every claim, for the queue and the claim switcher.
 * GET /claims carries no claimant name or description, so each claim's detail is fetched too.
 * Calls made within two seconds of each other share one round of requests.
 */
export function listQueue(fresh = false): Promise<QueueCase[]> {
  if (!fresh && queueCache && Date.now() - queueCache.at < 2000) return queueCache.rows;
  const rows = api.listClaims().then(async (list) => {
    const details = await Promise.all(list.map((r) => api.getClaim(r.id).catch(() => undefined as ApiClaimDetail | undefined)));
    return list.map((r, i) => buildQueueRow(r, details[i]));
  });
  queueCache = { at: Date.now(), rows };
  rows.catch(() => (queueCache = null));
  return rows;
}

/** The queue, refreshed every few seconds while any claim is being investigated. */
export function useQueue() {
  const [rows, setRows] = useState<QueueCase[] | undefined>(undefined);
  const [error, setError] = useState('');
  useEffect(() => {
    let on = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = (fresh: boolean) =>
      listQueue(fresh)
        .then((r) => {
          if (!on) return;
          setRows(r);
          setError('');
          if (r.some((x) => x.status === 'investigating')) timer = setTimeout(() => load(true), 3000);
        })
        .catch((e: Error) => on && setError(e.message));
    load(true);
    return () => {
      on = false;
      clearTimeout(timer);
    };
  }, []);
  return { rows, error };
}

// ---------------------------------------------------------------- one case

export interface CaseActions {
  /** Start (or start over) the investigation: POST /rerun. */
  start: () => Promise<void>;
  /** Ask the agents one more question: POST /question. */
  ask: (question: string) => Promise<void>;
  /** Record the adjuster's decision: POST /decision. */
  decide: (body: { decision: 'approve' } | { decision: 'modify'; outcome: Outcome; reason: string }) => Promise<void>;
  /** Set a finding aside: POST /evidence/{id}/reject. */
  reject: (evidenceId: number) => Promise<void>;
}

/**
 * One claim, kept in step with the backend.
 * While the claim is being investigated the live stream is open and the case is rebuilt as steps arrive.
 * `c` is undefined while loading and null when the claim does not exist.
 */
export function useCase(id: string) {
  const [c, setC] = useState<CaseFile | null | undefined>(undefined);
  const [live, setLive] = useState(false);
  const [error, setError] = useState('');
  const ref = useRef<{ es?: EventSource; timer?: ReturnType<typeof setTimeout>; poll?: ReturnType<typeof setInterval>; on: boolean }>({ on: true });

  const load = useCallback(async () => {
    const [detail, trace] = await Promise.all([api.getClaim(id), api.getTrace(id)]);
    const built = buildCase(detail, trace);
    if (ref.current.on) setC(built);
    return built;
  }, [id]);

  const stopWatching = useCallback(() => {
    ref.current.es?.close();
    ref.current.es = undefined;
    clearTimeout(ref.current.timer);
    clearInterval(ref.current.poll);
  }, []);

  /** Follow a running investigation until the backend says it is over. */
  const watch = useCallback(() => {
    stopWatching();
    setLive(true);
    const finish = () => {
      stopWatching();
      load()
        .catch((e: Error) => setError(e.message))
        .finally(() => ref.current.on && setLive(false));
    };
    const soon = () => {
      clearTimeout(ref.current.timer);
      ref.current.timer = setTimeout(() => load().catch(() => undefined), 150);
    };
    const es = api.openStream(id);
    ref.current.es = es;
    for (const kind of ['trace', 'evidence', 'score']) es.addEventListener(kind, soon);
    // The backend closes the stream after the status that ends a run. Close our side too, or the browser reconnects.
    es.addEventListener('status', (e) => {
      try {
        if (JSON.parse((e as MessageEvent).data).status !== 'investigating') finish();
      } catch {
        finish();
      }
    });
    es.onerror = () => {
      // Stream lost: fall back to asking every two seconds until the run is over.
      es.close();
      clearInterval(ref.current.poll);
      ref.current.poll = setInterval(() => {
        load()
          .then((built) => built.status !== 'investigating' && finish())
          .catch(() => undefined);
      }, 2000);
    };
  }, [id, load, stopWatching]);

  useEffect(() => {
    ref.current.on = true;
    setC(undefined);
    setLive(false);
    setError('');
    load()
      .then((built) => built.status === 'investigating' && watch())
      .catch((e: api.ApiError) => {
        if (!ref.current.on) return;
        if (e.status === 404) setC(null);
        else setError(e.message);
      });
    return () => {
      ref.current.on = false;
      stopWatching();
    };
  }, [id, load, watch, stopWatching]);

  const actions: CaseActions = {
    start: async () => {
      await api.rerun(id);
      await load();
      watch();
    },
    ask: async (question) => {
      await api.ask(id, question);
      await load();
      watch();
    },
    decide: async (body) => {
      await api.decide(id, body);
      await load();
    },
    reject: async (evidenceId) => {
      await api.rejectEvidence(id, evidenceId);
      await load();
    },
  };

  return { c, live, error, actions };
}
