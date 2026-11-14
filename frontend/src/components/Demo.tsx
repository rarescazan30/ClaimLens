import { ArrowLeft, ArrowRight, CloudRain, FileSearch, Maximize, Play, RotateCcw, Satellite, ScanSearch, Scale, ShieldCheck, Sparkles, UserCheck } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { getClaim, getTrace, rerun } from '../api/client';
import { forgetCase, prefetchCase, useCase } from '../api/hooks';
import { fmtClock } from '../lib/derive';
import { navigate, useCountUp } from '../lib/hooks';
import { APP_NAME, STAGES } from '../lib/meta';
import type { StageId } from '../lib/types';
import { CaseView } from './CaseView';

/**
 * The pitch demo at #/demo: seven chapters, driven with the arrow keys (or ?auto=1 for a hands-free run).
 * Chapter 4 is not a mock-up: it starts the demo flood claim on the real backend and narrates each step as it happens.
 */

const DEMO_CLAIM = 'C-8001';

const NARRATION: Record<StageId, string> = {
  intake: 'Dosarul C-8001: inundație la Pechea, jud. Galați. Sistemul citește dosarul.',
  documents: 'Formularul de daună și polița, în PDF, sunt citite automat și comparate cu dosarul.',
  client: 'Datele asiguratului sunt verificate automat: CNP, telefon, cont bancar, adresa pe hartă.',
  policy: 'Reguli fixe, fără AI: polița era activă, riscul este acoperit, dauna a fost avizată la timp.',
  photos: 'Fotografiile: există, se pot citi, au dată și loc?',
  plan: 'Orchestratorul transformă dauna în ipoteze de verificat și alege agenții potriviți.',
  agents: 'Agenții lucrează în paralel, fiecare pe o singură sursă publică: meteo, satelit, relief, fotografii, imagini stradale, presă.',
  judge: 'Un Arbitru independent compară dovezile, caută contradicții și poate trimite agenți înapoi.',
  verdict: 'Totul devine un scor, o recomandare și un dosar cu fiecare sursă.',
  review: 'Gata. Inspectorul primește dosarul de dovezi și decide. Sistemul doar recomandă.',
};

type ChapterId = 'problem' | 'reveal' | 'how' | 'live' | 'impact' | 'trust' | 'end';
const CHAPTERS: { id: ChapterId; n: string; label: string; auto: number }[] = [
  { id: 'problem', n: '01', label: 'Problema', auto: 9000 },
  { id: 'reveal', n: '', label: APP_NAME, auto: 5000 },
  { id: 'how', n: '02', label: 'Cum funcționează', auto: 9000 },
  { id: 'live', n: '03', label: 'În direct', auto: 0 },
  { id: 'impact', n: '04', label: 'Impactul', auto: 9000 },
  { id: 'trust', n: '05', label: 'Încredere', auto: 8000 },
  { id: 'end', n: '', label: 'Final', auto: 0 },
];

function Count({ to, suffix = '', ms = 1400 }: { to: number; suffix?: string; ms?: number }) {
  const v = useCountUp(to, ms);
  return (
    <>
      {Math.round(v).toLocaleString('ro-RO')}
      {suffix}
    </>
  );
}

function Tag({ n, label }: { n: string; label: string }) {
  return (
    <p className="demo-tag">
      <span>{n}</span>
      {label}
    </p>
  );
}

function Problem() {
  return (
    <div className="demo-slide demo-split">
      <div>
        <Tag n="01" label="Problema" />
        <p className="demo-big">
          <Count to={34000} />
        </p>
        <p className="demo-lead">de locuințe despăgubite în România într-un singur an, cu 14% mai multe decât în anul anterior.</p>
        <p className="demo-source">Sursa: UNSAR, 2025</p>
      </div>
      <div className="demo-facts">
        <div className="demo-fact" style={{ '--d': '0.6s' } as React.CSSProperties}>
          <b>20–50 de zile</b>
          <span>durează de obicei de la daună la plată după o catastrofă naturală.</span>
          <i>Sursa: Tractable</i>
        </div>
        <div className="demo-fact" style={{ '--d': '1.1s' } as React.CSSProperties}>
          <b>6.000–7.000</b>
          <span>de locuințe afectate de inundațiile din Galați și Vaslui, septembrie 2024.</span>
          <i>Sursa: PAID, prin presa economică</i>
        </div>
        <div className="demo-fact" style={{ '--d': '1.6s' } as React.CSSProperties}>
          <b>Ore pe dosar</b>
          <span>pierdute căutând dovezi: arhive meteo, hărți de inundație, presă, verificarea fotografiilor.</span>
          <i>Estimarea echipei</i>
        </div>
      </div>
    </div>
  );
}

function Reveal() {
  return (
    <div className="demo-slide demo-center">
      <span className="demo-logo">
        <Sparkles size={44} strokeWidth={1.7} />
      </span>
      <h1 className="demo-title">{APP_NAME}</h1>
      <p className="demo-lead is-center">Inspectorul nu mai caută dovezi. Primește un dosar cu surse și decide.</p>
    </div>
  );
}

const HOW = [
  { icon: FileSearch, title: 'Dosarul depus', text: 'Formularul de daună și polița, în PDF, citite automat.' },
  { icon: ShieldCheck, title: 'Verificări fără AI', text: 'Documente, datele clientului, condițiile poliței, fotografiile.' },
  { icon: Satellite, title: 'Șase agenți', text: 'Meteo, satelit, relief, fotografii, imagini stradale, presă. Fiecare pe o sursă publică.' },
  { icon: Scale, title: 'Arbitru independent', text: 'Caută contradicții și trimite agenți înapoi când lipsește ceva.' },
  { icon: UserCheck, title: 'Inspectorul decide', text: 'Primește scorul, recomandarea și fiecare sursă. Nimic nu se plătește fără el.' },
];

function How() {
  return (
    <div className="demo-slide">
      <Tag n="02" label="Cum funcționează" />
      <h2 className="demo-h2">
        De la dosar la decizie, <span className="hl">în câteva minute.</span>
      </h2>
      <ol className="demo-steps">
        {HOW.map((s, i) => (
          <li key={s.title} style={{ '--d': `${0.25 + i * 0.35}s` } as React.CSSProperties}>
            <span className="demo-step-n">{i + 1}</span>
            <s.icon size={22} strokeWidth={1.8} />
            <b>{s.title}</b>
            <span>{s.text}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

/** Chapter 3: the real claim, run on the real backend, with a caption bar that follows it step by step. */
function Live({ onMeasured, report, setReport }: { onMeasured: (ms: number) => void; report: boolean; setReport: (v: boolean) => void }) {
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');
  // Each new run remounts the tracker, so its live stream is opened after the backend has really begun the run.
  const [run, setRun] = useState<{ key: number; at: number | null }>({ key: 0, at: null });
  const selfStart = useRef(0);
  const newRun = () => {
    forgetCase(DEMO_CLAIM);
    setRun((r) => ({ key: r.key + 1, at: Date.now() }));
  };

  const start = async () => {
    setError('');
    setStarting(true);
    setReport(false);
    selfStart.current = Date.now();
    try {
      await rerun(DEMO_CLAIM);
      newRun();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(false);
    }
  };

  // A claim that was never investigated starts by itself the first time this chapter opens.
  useEffect(() => {
    getClaim(DEMO_CLAIM)
      .then((d) => {
        if (d.claim.status === 'received') start();
      })
      .catch((e: Error) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A run can also start from the case page's own "Reluați investigația". Watch the claim's status, and when a run
  // begins that this chapter did not start, reset the clock for it the same way.
  useEffect(() => {
    let last: string | null = null;
    const tick = () =>
      getClaim(DEMO_CLAIM)
        .then((d) => {
          const s = d.claim.status;
          if (last !== null && last !== 'investigating' && s === 'investigating' && Date.now() - selfStart.current > 5000) {
            setReport(false);
            newRun();
          }
          last = s;
        })
        .catch(() => undefined);
    tick();
    const id = setInterval(tick, 1500);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <LiveRun key={run.key} startedAt={run.at} starting={starting} error={error} onStart={start} onMeasured={onMeasured} report={report} setReport={setReport} />;
}

function LiveRun({ startedAt, starting, error, onStart, onMeasured, report, setReport }: {
  startedAt: number | null;
  starting: boolean;
  error: string;
  onStart: () => void;
  onMeasured: (ms: number) => void;
  report: boolean;
  setReport: (v: boolean) => void;
}) {
  const { c, live } = useCase(DEMO_CLAIM);
  const [now, setNow] = useState(Date.now());
  const [took, setTook] = useState<number | null>(null);

  const running = live || c?.status === 'investigating';
  // A run is timed only once it has really been seen running: a remembered old result must not end the clock at 00:00.
  const sawRunning = useRef(false);
  // Joining a run already under way: the clock starts from how far the backend says it has got.
  const [joinedAt, setJoinedAt] = useState<number | null>(null);
  useEffect(() => {
    if (!running) return;
    sawRunning.current = true;
    if (startedAt === null && joinedAt === null) {
      setJoinedAt(Date.now() - (c && c.edge < 1e11 ? c.edge : 0));
      // Then the exact start: the first step's timestamp from the backend.
      getTrace(DEMO_CLAIM)
        .then((t) => {
          const first = Math.min(...t.map((x) => Date.parse(x.started_at)).filter((n) => !Number.isNaN(n)));
          if (Number.isFinite(first) && first <= Date.now()) setJoinedAt(first);
        })
        .catch(() => undefined);
    }
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);
  const from = startedAt ?? joinedAt;
  useEffect(() => {
    if (!running && sawRunning.current && from !== null && took === null && c && c.status !== 'received' && c.status !== 'investigating') {
      const ms = Date.now() - from;
      setTook(ms);
      onMeasured(ms);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running, c?.status]);

  const lastStage: StageId | undefined = c?.windows.length ? c.windows[c.windows.length - 1].stage : undefined;
  const stage: StageId = !c ? 'intake' : running ? (lastStage ?? 'intake') : c.status === 'paused' ? 'policy' : 'review';
  const stepNo = STAGES.findIndex((s) => s.id === stage) + 1;
  // A run finished before this chapter opened still has its real length: the backend's own timestamps (not paced).
  const recorded = c && !running && !sawRunning.current && startedAt === null && !c.paced && c.duration > 0 && c.duration < 1e11 && (c.status === 'awaiting_decision' || c.status === 'decided') ? c.duration : null;
  useEffect(() => {
    if (took === null && recorded !== null) onMeasured(recorded);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recorded]);
  const elapsed = took ?? (from !== null ? now - from : (recorded ?? 0));
  const caption = c?.status === 'paused' ? 'O condiție a poliței nu este îndeplinită: investigația se oprește și dosarul așteaptă inspectorul.' : NARRATION[stage];
  const finished = c?.status === 'awaiting_decision' || c?.status === 'decided';

  return (
    <div className="demo-live">
      <div className="demo-live-app">
        <CaseView key={report ? 'r' : 'p'} id={DEMO_CLAIM} initialTab={report ? 'report' : undefined} />
      </div>
      <div className="demo-caption" aria-live="polite">
        <Tag n="03" label="În direct" />
        <div className="demo-caption-main">
          <p className="demo-caption-step">
            {running ? `Pasul ${stepNo} din ${STAGES.length} · ${STAGES[stepNo - 1].short}` : c?.status === 'received' || starting ? 'Pornește investigația' : 'Investigație încheiată'}
          </p>
          <p className="demo-caption-text" key={caption}>
            {error ? `Serverul a refuzat pornirea: ${error}` : starting || c?.status === 'received' ? NARRATION.intake : caption}
          </p>
        </div>
        <div className="demo-clock">
          <span>{took !== null || (recorded !== null && from === null) ? 'Durata reală' : 'Timp real'}</span>
          <b>{fmtClock(elapsed)}</b>
        </div>
        <div className="demo-caption-actions">
          {!running && finished && !report && (
            <button type="button" className="btn btn-primary" onClick={() => setReport(true)}>
              Vedeți raportul
              <ArrowRight size={14} />
            </button>
          )}
          {!running && c && c.status !== 'received' && (
            <button type="button" className="btn btn-quiet" disabled={starting} onClick={onStart}>
              <RotateCcw size={14} />
              Rulați din nou, în direct
            </button>
          )}
          {c?.status === 'received' && !starting && (
            <button type="button" className="btn btn-primary" onClick={onStart}>
              <Play size={14} fill="currentColor" />
              Porniți
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Impact({ measured }: { measured: number | null }) {
  const aiMin = measured ? measured / 60000 : 2;
  const manualMin = 150;
  const review = 10;
  const saved = Math.round((1 - (aiMin + review) / manualMin) * 100);
  return (
    <div className="demo-slide">
      <Tag n="04" label="Impactul" />
      <h2 className="demo-h2">
        Documentarea unui dosar: <span className="hl">ore devin minute.</span>
      </h2>
      <div className="demo-bars">
        <div className="demo-bar">
          <span className="demo-bar-label">Inspector, manual</span>
          <div className="demo-bar-track">
            <span className="demo-bar-fill is-manual" style={{ '--w': '100%' } as React.CSSProperties} />
          </div>
          <b>~2,5 ore</b>
        </div>
        <div className="demo-bar">
          <span className="demo-bar-label">{APP_NAME} + verificarea inspectorului</span>
          <div className="demo-bar-track">
            <span className="demo-bar-fill is-ai" style={{ '--w': `${Math.max(4, ((aiMin + review) / manualMin) * 100)}%` } as React.CSSProperties} />
          </div>
          <b>
            {measured ? fmtClock(measured) : '~2 min'} + {review} min
          </b>
        </div>
      </div>
      <p className="demo-big is-accent">
        −<Count to={saved} suffix="%" />
      </p>
      <p className="demo-lead">
        din timpul de documentare al unui dosar.{' '}
        {measured ? `Investigația de adineauri a durat ${fmtClock(measured)}, măsurat în direct.` : 'Durata investigației se măsoară în direct, în capitolul 3.'}
      </p>
      <p className="demo-source">
        Estimarea echipei pentru munca manuală: arhiva meteo, harta inundației, relieful, verificarea fotografiilor, imaginile stradale, presa locală și
        redactarea, circa 150 de minute pe dosar.
      </p>
    </div>
  );
}

const TRUST = [
  { icon: UserCheck, title: 'Omul decide', text: 'Sistemul doar recomandă. Nimic nu se plătește și nu se respinge fără inspector.' },
  { icon: ScanSearch, title: 'Fiecare cifră are o sursă', text: 'Open-Meteo, Copernicus, OpenStreetMap, Mapillary, presa. Dosarul arată de unde vine fiecare.' },
  { icon: CloudRain, title: 'Lipsa datelor nu e fraudă', text: 'Un gol de date rămâne neconcludent. Arbitrul nu acuză pe nimeni.' },
];

function Trust() {
  return (
    <div className="demo-slide">
      <Tag n="05" label="Încredere" />
      <h2 className="demo-h2">
        Mai repede, <span className="hl">fără să ia decizia în locul omului.</span>
      </h2>
      <div className="demo-trust">
        {TRUST.map((t, i) => (
          <div key={t.title} className="demo-fact" style={{ '--d': `${0.3 + i * 0.35}s` } as React.CSSProperties}>
            <t.icon size={24} strokeWidth={1.8} />
            <b>{t.title}</b>
            <span>{t.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function End() {
  return (
    <div className="demo-slide demo-center">
      <span className="demo-logo">
        <Sparkles size={40} strokeWidth={1.7} />
      </span>
      <h1 className="demo-title is-end">
        Daune plătite în zile, <span className="hl">nu în săptămâni.</span>
      </h1>
      <p className="demo-pill">{APP_NAME} · UiPath Hackathon 2026</p>
    </div>
  );
}

export function Demo({ auto }: { auto: boolean }) {
  const [i, setI] = useState(0);
  const [measured, setMeasured] = useState<number | null>(null);
  const [report, setReport] = useState(false);
  const ch = CHAPTERS[i];
  const go = (d: number) => setI((x) => Math.min(CHAPTERS.length - 1, Math.max(0, x + d)));

  // The live chapter's claim loads while the first slides play, so chapter 3 opens without a loading screen.
  useEffect(() => {
    prefetchCase(DEMO_CLAIM);
  }, []);

  // Arrow keys and space move between chapters; inside the live chapter, the first "next" after the run opens the report.
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const el = e.target instanceof Element ? e.target : null;
      if (el?.closest('input, textarea')) return;
      if (e.key === 'ArrowRight' || e.key === 'PageDown' || (e.key === ' ' && !el?.closest('button'))) {
        e.preventDefault();
        if (ch.id === 'live' && measured !== null && !report) setReport(true);
        else go(1);
      } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
        e.preventDefault();
        if (ch.id === 'live' && report) setReport(false);
        else go(-1);
      } else if (e.key === 'Escape') navigate('#/');
      else if (e.key === 'f') document.documentElement.requestFullscreen?.().catch(() => {});
    };
    window.addEventListener('keydown', on);
    return () => window.removeEventListener('keydown', on);
  });

  // Hands-free mode (?auto=1): slides advance on their own; the live chapter waits for the run, shows the report, then moves on.
  useEffect(() => {
    if (!auto) return;
    if (ch.auto) {
      const t = setTimeout(() => go(1), ch.auto);
      return () => clearTimeout(t);
    }
    if (ch.id === 'live' && measured !== null) {
      const t = setTimeout(() => (report ? go(1) : setReport(true)), report ? 12000 : 4000);
      return () => clearTimeout(t);
    }
  }, [auto, i, measured, report, ch.auto, ch.id]);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [i, report]);

  // Every chapter except the live one is exactly one screen: no scrolling in any direction.
  useEffect(() => {
    document.documentElement.classList.toggle('demo-fixed', ch.id !== 'live');
    return () => document.documentElement.classList.remove('demo-fixed');
  }, [ch.id]);

  return (
    <div className={`demo ch-${ch.id}`}>
      <div className="demo-stage" key={ch.id}>
        {ch.id === 'problem' && <Problem />}
        {ch.id === 'reveal' && <Reveal />}
        {ch.id === 'how' && <How />}
        {ch.id === 'live' && <Live onMeasured={setMeasured} report={report} setReport={setReport} />}
        {ch.id === 'impact' && <Impact measured={measured} />}
        {ch.id === 'trust' && <Trust />}
        {ch.id === 'end' && <End />}
      </div>
      <nav className="demo-nav" aria-label="Capitolele demo-ului">
        <button type="button" className="icon-btn" onClick={() => go(-1)} disabled={i === 0} aria-label="Capitolul anterior">
          <ArrowLeft size={15} />
        </button>
        <ol>
          {CHAPTERS.map((c, k) => (
            <li key={c.id}>
              <button type="button" className={k === i ? 'is-on' : k < i ? 'is-past' : ''} onClick={() => setI(k)} aria-label={c.label} aria-current={k === i}>
                <span />
              </button>
            </li>
          ))}
        </ol>
        <button type="button" className="icon-btn" onClick={() => go(1)} disabled={i === CHAPTERS.length - 1} aria-label="Capitolul următor">
          <ArrowRight size={15} />
        </button>
        <button type="button" className="icon-btn" onClick={() => document.documentElement.requestFullscreen?.().catch(() => {})} aria-label="Ecran complet">
          <Maximize size={14} />
        </button>
      </nav>
    </div>
  );
}
