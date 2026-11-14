import { ArrowRight, ChevronDown, ChevronRight, ClipboardCheck, Inbox, ListChecks, Play, Search, X, Zap } from 'lucide-react';
import { useEffect, useState } from 'react';
import { API_URL } from '../api/client';
import { useQueue } from '../api/hooks';
import { OUTCOMES } from '../lib/meta';
import { fmtScore } from '../lib/score';
import type { Outcome, QueueCase } from '../lib/types';
import { ScoreMeter } from './Cards';
import { TYPE_ICON } from './icons';
import { BandPill, CountUp, Empty, OutcomeTag } from './ui';

type Filter = 'all' | Outcome;

const OUTCOME_ICON = { fast_track: Zap, standard_review: ClipboardCheck, antifraud_referral: Search } as const;
const goTo = (id: string) => requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }));

export function Queue() {
  const { rows, error } = useQueue();
  const [filter, setFilter] = useState<Filter>('all');
  const [peek, setPeek] = useState<QueueCase | null>(null);
  const [showReady, setShowReady] = useState(true);

  useEffect(() => {
    if (!peek) return;
    const on = (e: KeyboardEvent) => e.key === 'Escape' && setPeek(null);
    window.addEventListener('keydown', on);
    return () => window.removeEventListener('keydown', on);
  }, [peek]);

  if (error && !rows)
    return (
      <div className="page queue">
        <div className="card">
          <Empty title="The backend is not answering" body={`${error} Start it (see backend/README.md), then reload this page. The address is set by VITE_API_URL, now ${API_URL}.`} />
        </div>
      </div>
    );
  if (!rows)
    return (
      <div className="page queue">
        <div className="card loading-card">
          <span className="spinner" /> Loading claims
        </div>
      </div>
    );

  // "New" = not investigated yet, or being investigated right now. "Verdict ready" = the run is over.
  const fresh = rows.filter((r) => r.status === 'received' || r.status === 'investigating');
  const ready = rows.filter((r) => r.status === 'awaiting_decision' || r.status === 'decided').sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  const visible = ready.filter((r) => filter === 'all' || r.outcome === filter);
  const count = (o: Outcome) => ready.filter((x) => x.outcome === o).length;

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
            <button
              type="button"
              className={`side-btn${showReady && filter === 'all' ? ' is-on' : ''}`}
              aria-expanded={showReady}
              onClick={() => {
                setFilter('all');
                setShowReady(filter !== 'all' || !showReady);
                goTo('verdict-section');
              }}
            >
              <ListChecks size={16} />
              <span className="side-name">Verdict ready</span>
              <span className="side-meta">{ready.length}</span>
            </button>
          </div>
          <div className="side-group" role="group" aria-label="Filter by outcome">
            <p className="side-label">By route</p>
            {(Object.keys(OUTCOMES) as Outcome[]).map((f) => {
              const Icon = OUTCOME_ICON[f];
              const on = showReady && filter === f;
              return (
                <button
                  type="button"
                  key={f}
                  className={`side-btn${on ? ' is-on' : ''}`}
                  aria-pressed={on}
                  onClick={() => {
                    setFilter(on ? 'all' : f);
                    setShowReady(true);
                    goTo('verdict-section');
                  }}
                >
                  <Icon size={16} />
                  <span className="side-name">{OUTCOMES[f].label}</span>
                  <span className="side-meta">{count(f)}</span>
                </button>
              );
            })}
          </div>
        </nav>
        <div className="case-main">
          <header className="page-head">
            <h1>
              Strongest claims, <span className="hl">paid first.</span>
            </h1>
            <ul className="stats">
              <li className="stat" style={{ '--i': 0 } as React.CSSProperties}>
                <span className="stat-label">Claims</span>
                <b className="stat-num">
                  <CountUp value={rows.length} />
                </b>
                <span className="stat-sub">on your desk</span>
              </li>
              <li className="stat s-accent" style={{ '--i': 1 } as React.CSSProperties}>
                <span className="stat-label">Waiting</span>
                <b className="stat-num">
                  <CountUp value={fresh.length} />
                </b>
                <span className="stat-sub">no verdict yet</span>
              </li>
              <li className="stat s-good" style={{ '--i': 2 } as React.CSSProperties}>
                <span className="stat-label">Fast-track</span>
                <b className="stat-num">
                  <CountUp value={count('fast_track')} />
                </b>
                <span className="stat-sub">ready to pay</span>
              </li>
              <li className="stat s-bad" style={{ '--i': 3 } as React.CSSProperties}>
                <span className="stat-label">Flagged</span>
                <b className="stat-num">
                  <CountUp value={count('antifraud_referral')} />
                </b>
                <span className="stat-sub">need a closer look</span>
              </li>
            </ul>
          </header>

          {rows.length === 0 && (
            <div className="card">
              <Empty title="No claims yet" body="The backend has no claims. Demo claims are loaded from demo/cases when it starts." />
            </div>
          )}

          {fresh.length > 0 && (
            <section className="queue-section" id="new-claims">
              <div className="section-head">
                <h2>
                  <span className="sec-n">01</span>New claims
                </h2>
                <span className="chip is-accent">{fresh.length} waiting</span>
              </div>
              <div className="new-grid">
                {fresh.map((q, i) => {
                  const Icon = TYPE_ICON[q.type];
                  const running = q.status === 'investigating';
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
                      {q.description && <p className="new-desc">“{q.description}”</p>}
                      <span className="btn btn-primary">
                        <Play size={14} fill="currentColor" />
                        {running ? 'Watch the investigation' : 'Open to investigate'}
                      </span>
                    </a>
                  );
                })}
              </div>
            </section>
          )}

          {rows.length > 0 && (
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
                {showReady && filter !== 'all' && <span className="chip is-accent">{OUTCOMES[filter].label} only</span>}
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
                            <span>{q.score !== undefined && q.band ? <BandPill score={q.score} band={q.band} /> : <span className="row-sub">No score</span>}</span>
                            <span>
                              {q.outcome && <OutcomeTag outcome={q.outcome} />}
                              {q.decided && <span className="row-sub"> · decided</span>}
                            </span>
                            <ChevronRight size={16} className="q-chev" />
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                  {visible.length === 0 && <p className="table-empty">{ready.length ? 'No claims on this route right now.' : 'No claim has a verdict yet.'}</p>}
                </div>
              )}
            </section>
          )}
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
            {peek.description && <p className="new-desc">“{peek.description}”</p>}
            {peek.score !== undefined && peek.band && (
              <>
                <div className="drawer-score">
                  <span className="score-num">{fmtScore(peek.score)}</span>
                  <div>
                    <BandPill score={peek.score} band={peek.band} />
                    {peek.outcome && (
                      <p className="row-sub">
                        {peek.decided ? 'Decided' : 'Recommended'}: {OUTCOMES[peek.outcome].action.toLowerCase()}
                      </p>
                    )}
                  </div>
                </div>
                <ScoreMeter score={peek.score} band={peek.band} />
              </>
            )}
            {peek.signals.length > 0 && (
              <>
                <h3>Strongest signals</h3>
                <ul className="signals">
                  {peek.signals.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </>
            )}
            <a className="btn btn-primary" href={`#/case/${peek.id}?tab=report`}>
              Open the case
              <ArrowRight size={14} />
            </a>
          </aside>
        </div>
      )}
    </div>
  );
}
