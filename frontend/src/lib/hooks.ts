import { useCallback, useEffect, useRef, useState } from 'react';
import type { Route } from '../mock/types';

/** Playback clock for a recorded (or live) run: play, pause, seek, speed. */
export function useRun(duration: number, initial = 0) {
  const [time, setTime] = useState(Math.min(initial, duration));
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const ref = useRef({ time, speed, duration });
  ref.current = { time, speed, duration };

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(now - last, 100);
      last = now;
      const next = ref.current.time + dt * ref.current.speed;
      if (next >= ref.current.duration) {
        ref.current.time = ref.current.duration;
        setTime(ref.current.duration);
        setPlaying(false);
        return;
      }
      ref.current.time = next;
      setTime(next);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing]);

  const play = useCallback(() => {
    if (ref.current.time >= ref.current.duration) setTime(0);
    setPlaying(true);
  }, []);
  const pause = useCallback(() => setPlaying(false), []);
  const toggle = useCallback(() => setPlaying((p) => {
    if (!p && ref.current.time >= ref.current.duration) setTime(0);
    return !p;
  }), []);
  const seek = useCallback((t: number) => setTime(Math.max(0, Math.min(t, ref.current.duration))), []);
  const restart = useCallback(() => {
    setTime(0);
    setPlaying(true);
  }, []);
  const finish = useCallback(() => {
    setPlaying(false);
    setTime(ref.current.duration);
  }, []);

  return { time, playing, speed, setSpeed, play, pause, toggle, seek, restart, finish };
}

export type RunClock = ReturnType<typeof useRun>;

/** Eases a displayed number toward its target so score changes read as movement, not jumps. */
export function useEased(target: number, ms = 500) {
  const [value, setValue] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    const start = performance.now();
    const a = from.current;
    if (a === target) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      from.current = target;
      setValue(target);
      return;
    }
    let raf = 0;
    const tick = (now: number) => {
      const k = Math.min(1, (now - start) / ms);
      const e = 1 - Math.pow(1 - k, 3);
      const v = a + (target - a) * e;
      from.current = v;
      setValue(v);
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return value;
}

/** Counts up from zero when a figure first appears, then eases to any later value. */
export function useCountUp(target: number, ms = 900) {
  const [goal, setGoal] = useState(0);
  useEffect(() => setGoal(target), [target]);
  return useEased(goal, ms);
}

export type Theme = 'light' | 'dark';

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const saved = localStorage.getItem('asigit-theme');
      if (saved === 'light' || saved === 'dark') return saved;
    } catch {
      /* storage can be unavailable in embedded previews */
    }
    // Deep violet is the home look; the light theme is one click away.
    return 'dark';
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem('asigit-theme', theme);
    } catch {
      /* ignore */
    }
  }, [theme]);
  return [theme, () => setTheme((t) => (t === 'light' ? 'dark' : 'light'))];
}

// Routing lives in the hash, but also in memory: some embedded previews do not pass hash changes through.
let currentHash = window.location.hash;
let lastNavigate = 0;
const routeListeners = new Set<() => void>();

export function navigate(hash: string) {
  currentHash = hash;
  lastNavigate = Date.now();
  try {
    if (window.location.hash !== hash) window.location.hash = hash;
  } catch {
    /* the in-memory route still applies */
  }
  routeListeners.forEach((l) => l());
  window.scrollTo(0, 0);
}

export function useHashRoute() {
  const [hash, setHash] = useState(currentHash);
  useEffect(() => {
    const sync = () => setHash(currentHash);
    const onHash = () => {
      const h = window.location.hash;
      // Ignore a host that rewrites the hash right after our own navigation.
      if (!h.startsWith('#/') && Date.now() - lastNavigate < 400) return;
      if (h === currentHash) return;
      currentHash = h;
      sync();
    };
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return;
      const a = (e.target as HTMLElement).closest?.('a[href^="#/"]');
      if (!a) return;
      e.preventDefault();
      navigate(a.getAttribute('href')!);
    };
    routeListeners.add(sync);
    window.addEventListener('hashchange', onHash);
    document.addEventListener('click', onClick);
    return () => {
      routeListeners.delete(sync);
      window.removeEventListener('hashchange', onHash);
      document.removeEventListener('click', onClick);
    };
  }, []);
  const [path, query = ''] = hash.replace(/^#/, '').split('?');
  return { path: path || '/', params: new URLSearchParams(query) };
}

/** Reviewer state per case, kept in memory so it survives navigating back to the queue. */
export interface Decision {
  route: Route;
  kind: 'approved' | 'overridden';
  reason?: string;
  at: string;
}
export interface CaseSession {
  time: number;
  /** True once the run has reached its verdict at least once. */
  completed?: boolean;
  decision?: Decision;
  dismissed: string[];
  requests: string[];
  edits: Record<string, string>;
}
const sessions = new Map<string, CaseSession>();
export const getSession = (id: string): CaseSession =>
  sessions.get(id) ?? { time: 0, dismissed: [], requests: [], edits: {} };
export const saveSession = (id: string, s: CaseSession) => sessions.set(id, s);
