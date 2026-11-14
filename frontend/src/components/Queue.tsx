import { ArrowRight, ChevronDown, ChevronRight, ClipboardCheck, Inbox, ListChecks, Play, Search, X, Zap } from 'lucide-react';
import { useEffect, useState } from 'react';
import { API_URL } from '../api/client';
import { useQueue } from '../api/hooks';
import { verdictRows, withHistory } from '../lib/demoHistory';
import { isNewClaim } from '../lib/early';
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
  const { rows: liveRows, error } = useQueue();
  const rows = liveRows ? withHistory(liveRows) : liveRows;
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
          <Empty title="Serverul nu răspunde" body={`${error} Porniți serverul (vezi backend/README.md), apoi reîncărcați pagina. Adresa se setează în VITE_API_URL (acum ${API_URL}).`} />
        </div>
      </div>
    );
  if (!rows)
    return (
      <div className="page queue">
        <div className="card loading-card">
          <span className="spinner" /> Se încarcă dosarele
        </div>
      </div>
    );

  // "New" = not investigated yet, or being investigated right now. "Verdict ready" = the run is over.
  const fresh = rows.filter((r) => isNewClaim(r.status));
  const ready = verdictRows(rows);
  const visible = ready.filter((r) => filter === 'all' || r.outcome === filter);
  const count = (o: Outcome) => ready.filter((x) => x.outcome === o).length;

  return (
    <div className="page queue">
      <div className="case-layout">
        <nav className="side-nav" aria-label="Secțiunile listei">
          <div className="side-group">
            <p className="side-label">Dosare</p>
            {fresh.length > 0 && (
              <button type="button" className="side-btn" onClick={() => goTo('new-claims')}>
                <Inbox size={16} />
                <span className="side-name">Noi</span>
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
              <span className="side-name">Cu verdict</span>
              <span className="side-meta">{ready.length}</span>
            </button>
          </div>
          <div className="side-group" role="group" aria-label="Filtrați după recomandare">
            <p className="side-label">După recomandare</p>
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
              Dosarele cele mai sigure, <span className="hl">primele la plată.</span>
            </h1>
            <ul className="stats">
              <li className="stat" style={{ '--i': 0 } as React.CSSProperties}>
                <span className="stat-label">Dosare</span>
                <b className="stat-num">
                  <CountUp value={rows.length} />
                </b>
                <span className="stat-sub">în total</span>
              </li>
              <li className="stat s-accent" style={{ '--i': 1 } as React.CSSProperties}>
                <span className="stat-label">De investigat</span>
                <b className="stat-num">
                  <CountUp value={fresh.length} />
                </b>
                <span className="stat-sub">fără verdict</span>
              </li>
              <li className="stat s-good" style={{ '--i': 2 } as React.CSSProperties}>
                <span className="stat-label">Plată rapidă</span>
                <b className="stat-num">
                  <CountUp value={count('fast_track')} />
                </b>
                <span className="stat-sub">gata de plată</span>
              </li>
              <li className="stat s-bad" style={{ '--i': 3 } as React.CSSProperties}>
                <span className="stat-label">Antifraudă</span>
                <b className="stat-num">
                  <CountUp value={count('antifraud_referral')} />
                </b>
                <span className="stat-sub">de verificat atent</span>
              </li>
            </ul>
          </header>

          {rows.length === 0 && (
            <div className="card">
              <Empty title="Niciun dosar" body="Serverul nu are dosare. Dosarele demo se încarcă din demo/cases la pornire." />
            </div>
          )}

          {fresh.length > 0 && (
            <section className="queue-section" id="new-claims">
              <div className="section-head">
                <h2>
                  <span className="sec-n">01</span>Dosare noi
                </h2>
                <span className="chip is-accent">{fresh.length === 1 ? '1 nou' : `${fresh.length} noi`}</span>
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
                        {q.status === 'paused' && <span className="chip c-paused">Oprit</span>}
                        <span className="chip">Avizat {q.filed}</span>
                      </div>
                      {q.description && <p className="new-desc">“{q.description}”</p>}
                      <span className="btn btn-primary">
                        <Play size={14} fill="currentColor" />
                        {running ? 'Urmăriți investigația' : q.status === 'paused' ? 'Deschideți pentru a continua sau a decide' : 'Deschideți dosarul'}
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
                    Dosare cu verdict
                    <span className="chip">{ready.length}</span>
                    <ChevronDown size={18} className="section-chev" aria-hidden="true" />
                  </button>
                </h2>
                {showReady && filter !== 'all' && <span className="chip is-accent">Filtru: {OUTCOMES[filter].label.toLowerCase()}</span>}
              </div>
              {showReady && (
                <div className="card table-card" id="verdict-ready">
                  <div className="q-row q-head" aria-hidden="true">
                    <span>Asigurat</span>
                    <span>Daună</span>
                    <span>Scor</span>
                    <span>Recomandare</span>
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
                              <span className="row-sub">Avizat {q.filed}</span>
                            </span>
                            <span>{q.score !== undefined && q.band ? <BandPill score={q.score} band={q.band} /> : <span className="row-sub">Fără scor</span>}</span>
                            <span>
                              {q.outcome && <OutcomeTag outcome={q.outcome} />}
                              {q.decided && <span className="row-sub"> · decis</span>}
                            </span>
                            <ChevronRight size={16} className="q-chev" />
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                  {visible.length === 0 && <p className="table-empty">{ready.length ? 'Niciun dosar nu are această recomandare.' : 'Încă niciun dosar nu are verdict.'}</p>}
                </div>
              )}
            </section>
          )}
        </div>
      </div>

      {peek && (
        <div className="drawer-wrap" onClick={() => setPeek(null)}>
          <aside className="drawer" role="dialog" aria-modal="true" aria-label={`Rezumat: ${peek.claimant}`} onClick={(e) => e.stopPropagation()}>
            <header>
              <div>
                <p className="eyebrow">{peek.id}</p>
                <h2>{peek.claimant}</h2>
                <p className="row-sub">
                  {peek.typeLabel} · {peek.place} · avizat {peek.filed}
                </p>
              </div>
              <button type="button" className="icon-btn" aria-label="Închideți rezumatul" autoFocus onClick={() => setPeek(null)}>
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
                        {peek.decided ? 'Decis' : 'Recomandare'}: {OUTCOMES[peek.outcome].action.toLowerCase()}
                      </p>
                    )}
                  </div>
                </div>
                <ScoreMeter score={peek.score} band={peek.band} />
              </>
            )}
            {peek.signals.length > 0 && (
              <>
                <h3>Cele mai puternice dovezi</h3>
                <ul className="signals">
                  {peek.signals.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </>
            )}
            {peek.mock ? (
              <p className="row-sub archived-note">Dosar arhivat</p>
            ) : (
              <a className="btn btn-primary" href={`#/case/${peek.id}?tab=report`}>
                Deschideți dosarul
                <ArrowRight size={14} />
              </a>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
