import { ArrowRight, ChevronDown, ChevronRight, ClipboardCheck, Database, Inbox, ListChecks, Play, Search, X, Zap } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { getSession } from '../lib/hooks';
import { computeScore, routeFor } from '../lib/score';
import { getCase, listQueue } from '../mock/api';
import { ROUTES } from '../mock/meta';
import type { CaseFile, QueueCase, Route } from '../mock/types';
import { ScoreMeter } from './Cards';
import { TYPE_ICON } from './icons';
import { BandPill, CountUp, RouteTag } from './ui';

type Filter = 'all' | Route;

const ROUTE_ICON = { 'fast-track': Zap, standard: ClipboardCheck, investigate: Search } as const;
const goTo = (id: string) => requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }));

export function Queue() {
  const [queue, setQueue] = useState<QueueCase[]>([]);
  const [files, setFiles] = useState<Record<string, CaseFile>>({});
  const [filter, setFilter] = useState<Filter>('all');
  const [peek, setPeek] = useState<QueueCase | null>(null);
  const [showEvent, setShowEvent] = useState(false);
  const [showReady, setShowReady] = useState(false);

  useEffect(() => {
    listQueue().then(async (q) => {
      setQueue(q);
      const full = await Promise.all(q.filter((x) => x.status === 'new').map((x) => getCase(x.id)));
      setFiles(Object.fromEntries(full.filter(Boolean).map((f) => [f!.id, f!])));
    });
  }, []);

  useEffect(() => {
    if (!peek) return;
    const on = (e: KeyboardEvent) => e.key === 'Escape' && setPeek(null);
    window.addEventListener('keydown', on);
    return () => window.removeEventListener('keydown', on);
  }, [peek]);

  // Demo cases that have been run in this session move from "new" to "verdict ready".
  const rows = useMemo(
    () =>
      queue.map((q) => {
        const f = files[q.id];
        const s = getSession(q.id);
        if (q.status !== 'new' || !f || !s.completed) return q;
        const live = f.evidence.filter((e) => !s.dismissed.includes(e.id));
        const score = computeScore(f.p0, live);
        const gate = !!f.gate && !s.dismissed.includes(f.gate.evidence);
        return { ...q, status: 'verdict' as const, score, route: s.decision?.route ?? routeFor(score, gate), signals: live.slice(0, 3).map((e) => `${e.title}: ${e.value}`) };
      }),
    [queue, files],
  );

  const fresh = rows.filter((r) => r.status === 'new');
  const ready = rows.filter((r) => r.status === 'verdict').sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  const visible = ready.filter((r) => filter === 'all' || r.route === filter);
  const count = (r: Route) => ready.filter((x) => x.route === r).length;

  return (
    <div className="page queue">
      <div className="case-layout">
      <nav className="side-nav" aria-label="Queue sections">
        <div className="side-group">
          <p className="side-label">Queue</p>
          {fresh.length > 0 && (
            <button type="button" className="side-btn" onClick={() => goTo('new-claims')}>
              <Inbox size={16} />
              <span className="side-name">New claims</span>
              <span className="side-meta">{fresh.length}</span>
            </button>
          )}
          <button type="button" className={`side-btn${showReady && filter === 'all' ? ' is-on' : ''}`} aria-expanded={showReady} onClick={() => { setFilter('all'); setShowReady(filter !== 'all' || !showReady); goTo('verdict-section'); }}>
            <ListChecks size={16} />
            <span className="side-name">Verdict ready</span>
            <span className="side-meta">{ready.length}</span>
          </button>
        </div>
        <div className="side-group" role="group" aria-label="Filter by route">
          <p className="side-label">By route</p>
          {(['fast-track', 'standard', 'investigate'] as Route[]).map((f) => {
            const Icon = ROUTE_ICON[f];
            const on = showReady && filter === f;
            return (
              <button type="button" key={f} className={`side-btn${on ? ' is-on' : ''}`} aria-pressed={on} onClick={() => { setFilter(on ? 'all' : f); setShowReady(true); goTo('verdict-section'); }}>
                <Icon size={16} />
                <span className="side-name">{ROUTES[f].label}</span>
                <span className="side-meta">{count(f)}</span>
              </button>
            );
          })}
        </div>
        <div className="side-group">
          <p className="side-label">Reference</p>
          <button type="button" className={`side-btn${showEvent ? ' is-on' : ''}`} aria-expanded={showEvent} onClick={() => setShowEvent(!showEvent)}>
            <Database size={16} />
            <span className="side-name">Event footprint</span>
          </button>
        </div>
      </nav>
      <div className="case-main">
      <header className="page-head">
        <h1>
          Strongest claims, <span className="hl">paid first.</span>
        </h1>
        <ul className="stats">
          <li className="stat" style={{ '--i': 0 } as React.CSSProperties}>
            <span className="stat-label">Open claims</span>
            <b className="stat-num"><CountUp value={rows.length} /></b>
            <span className="stat-sub">in your queue today</span>
          </li>
          <li className="stat s-accent" style={{ '--i': 1 } as React.CSSProperties}>
            <span className="stat-label">Waiting</span>
            <b className="stat-num"><CountUp value={fresh.length} /></b>
            <span className="stat-sub">not investigated yet</span>
          </li>
          <li className="stat s-good" style={{ '--i': 2 } as React.CSSProperties}>
            <span className="stat-label">Fast-track</span>
            <b className="stat-num"><CountUp value={count('fast-track')} /></b>
            <span className="stat-sub">ready to pay</span>
          </li>
          <li className="stat s-bad" style={{ '--i': 3 } as React.CSSProperties}>
            <span className="stat-label">Flagged</span>
            <b className="stat-num"><CountUp value={count('investigate')} /></b>
            <span className="stat-sub">need a closer look</span>
          </li>
        </ul>
      </header>

      {showEvent && (
      <section className="card event-card">
          <span className="event-ico">
            <Database size={18} />
          </span>
          <div className="event-main">
            <p className="eyebrow">Event footprint · version 3</p>
            <h2>Galați county flood, 14 Sep 2024</h2>
            <p>Investigated once, reused for every claim in the area.</p>
          </div>
          <dl className="event-stats">
            <div>
              <dt>Linked claims</dt>
              <dd>37</dd>
            </div>
            <div>
              <dt>Checks answered from the footprint</dt>
              <dd>
                81%
                <span className="mini-bar">
                  <span style={{ width: '81%' }} />
                </span>
              </dd>
            </div>
          </dl>
        </section>
      )}

      {fresh.length > 0 && (
        <section className="queue-section" id="new-claims">
          <div className="section-head">
            <h2><span className="sec-n">01</span>New claims</h2>
            <span className="chip is-accent">{fresh.length} waiting</span>
          </div>
          <div className="new-grid">
            {fresh.map((q, i) => {
              const Icon = TYPE_ICON[q.type];
              const inProgress = getSession(q.id).time > 0;
              return (
                <a key={q.id} className="card new-card" href={`#/case/${q.id}`} style={{ '--i': i } as React.CSSProperties}>
                  <div className="new-top">
                    <span className="type-ico">
                      <Icon size={18} />
                    </span>
                    <div>
                      <h3>{q.claimant}</h3>
                      <p className="row-sub">
                        <span className="mono-value">{q.id}</span> · {q.typeLabel} · {q.place}
                      </p>
                    </div>
                    <span className="chip">Filed {q.filed}</span>
                  </div>
                  <p className="new-desc">“{q.description}”</p>
                  <span className="btn btn-primary">
                    <Play size={14} fill="currentColor" />
                    {inProgress ? 'Continue investigation' : 'Start investigation'}
                  </span>
                </a>
              );
            })}
          </div>
        </section>
      )}

      <section className="queue-section" id="verdict-section">
        <div className="section-head">
          <h2>
            <button type="button" className="section-toggle" aria-expanded={showReady} aria-controls="verdict-ready" onClick={() => setShowReady(!showReady)}>
              <span className="sec-n">{fresh.length > 0 ? '02' : '01'}</span>
              Verdict ready
              <span className="chip">{ready.length}</span>
              <ChevronDown size={18} className="section-chev" aria-hidden="true" />
            </button>
          </h2>
          {showReady && filter !== 'all' && <span className="chip is-accent">{ROUTES[filter].label} only</span>}
        </div>
        {showReady && (
        <div className="card table-card" id="verdict-ready">
          <div className="q-row q-head" aria-hidden="true">
            <span>Claimant</span>
            <span>Claim</span>
            <span>Score</span>
            <span>Route</span>
            <span />
          </div>
          <ul>
            {visible.map((q, i) => {
              const Icon = TYPE_ICON[q.type];
              return (
                <li key={q.id} style={{ '--i': i } as React.CSSProperties}>
                  <button type="button" className="q-row" onClick={() => setPeek(q)}>
                    <span className="q-who">
                      <b>{q.claimant}</b>
                      <span className="row-sub">
                        <span className="mono-value">{q.id}</span> · {q.place}
                      </span>
                    </span>
                    <span className="q-claim">
                      <span className="q-type">
                        <Icon size={14} />
                        {q.typeLabel}
                      </span>
                      <span className="row-sub">Filed {q.filed}</span>
                    </span>
                    <span>
                      <BandPill score={q.score!} />
                    </span>
                    <span>
                      <RouteTag route={q.route!} />
                    </span>
                    <ChevronRight size={16} className="q-chev" />
                  </button>
                </li>
              );
            })}
          </ul>
          {visible.length === 0 && <p className="table-empty">No claims on this route right now.</p>}
        </div>
        )}
      </section>

      </div>
      </div>

      {peek && (
        <div className="drawer-wrap" onClick={() => setPeek(null)}>
          <aside className="drawer" role="dialog" aria-modal="true" aria-label={`Summary for ${peek.claimant}`} onClick={(e) => e.stopPropagation()}>
            <header>
              <div>
                <p className="eyebrow">{peek.id}</p>
                <h2>{peek.claimant}</h2>
                <p className="row-sub">
                  {peek.typeLabel} · {peek.place} · filed {peek.filed}
                </p>
              </div>
              <button type="button" className="icon-btn" aria-label="Close summary" autoFocus onClick={() => setPeek(null)}>
                <X size={16} />
              </button>
            </header>
            <p className="new-desc">“{peek.description}”</p>
            <div className="drawer-score">
              <span className="score-num">{peek.score}</span>
              <div>
                <BandPill score={peek.score!} />
                <p className="row-sub">Recommended: {ROUTES[peek.route!].action.toLowerCase()}</p>
              </div>
            </div>
            <ScoreMeter score={peek.score!} />
            <h3>Strongest signals</h3>
            <ul className="signals">
              {peek.signals?.map((s) => <li key={s}>{s}</li>)}
            </ul>
            {files[peek.id] ? (
              <a className="btn btn-primary" href={`#/case/${peek.id}?tab=report`}>
                Open the case
                <ArrowRight size={14} />
              </a>
            ) : (
              <p className="card-note">This mock carries full traces for C-1042 and C-1047. Other rows show the summary only.</p>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
