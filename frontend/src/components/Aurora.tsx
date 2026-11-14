import { useEffect, useRef, useState } from 'react';

export type Tone = 'accent' | 'good' | 'warn' | 'bad';

// Violet light. The ground is indigo with a faint green haze; the pool of light under the rail takes the colour of
// the run's state: lavender while working, mint when the evidence supports the claim, amber or rose when it does not.
type RGB = [number, number, number];
const mix = (a: RGB, b: RGB, k: number): RGB => [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k];
const VIOLET: RGB = [0.5, 0.42, 0.96];
const INDIGO: RGB = [0.3, 0.24, 0.78];
const HAZE: RGB = [0.3, 0.72, 0.5];
const TONES: Record<Tone, RGB> = {
  accent: VIOLET,
  good: [0.36, 0.8, 0.58],
  warn: [0.9, 0.68, 0.38],
  bad: [0.94, 0.45, 0.6],
};
function palette(tone: Tone, dark: boolean): number[][] {
  const lead = mix(VIOLET, TONES[tone], tone === 'accent' ? 0 : 0.7);
  // On the light theme the light is pastel, so it tints the page instead of darkening it.
  return dark ? [lead, INDIGO, mix(INDIGO, HAZE, 0.55)] : [mix(lead, [1, 1, 1], 0.25), mix(INDIGO, [1, 1, 1], 0.35), mix(HAZE, [1, 1, 1], 0.3)];
}

const VERT = `attribute vec2 p; void main(){ gl_Position = vec4(p, 0.0, 1.0); }`;

// Soft silk light: slow domain-warped noise shaped into wide ribbons, plus a pool of light at a focus point.
const FRAG = `
precision mediump float;
uniform vec2 u_res; uniform float u_time; uniform vec2 u_focus; uniform float u_spread;
uniform vec3 u_c1; uniform vec3 u_c2; uniform vec3 u_c3; uniform float u_gain; uniform float u_ambient;
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){
  vec2 i = floor(p), f = fract(p); f = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}
float fbm(vec2 p){ float v = 0.0, a = 0.5; for (int i = 0; i < 3; i++){ v += a * noise(p); p = p * 1.9 + 7.3; a *= 0.5; } return v; }
void main(){
  vec2 uv = gl_FragCoord.xy / u_res;
  float ar = u_res.x / u_res.y;
  vec2 p = vec2(uv.x * ar, uv.y);
  vec2 f = vec2(u_focus.x * ar, u_focus.y);
  float t = u_time * 0.045;
  vec2 q = p * 0.85;
  vec2 w = vec2(fbm(q + vec2(t, 0.3)), fbm(q + vec2(4.1, -t)));
  float n = fbm(q * 1.15 + 1.7 * w);
  float ribbon = 0.5 + 0.5 * sin(p.y * 2.6 + w.x * 4.2 + n * 2.4 + t * 5.0);
  ribbon = smoothstep(0.15, 0.95, ribbon);
  vec2 d = (p - f) * vec2(1.0, 1.5);
  float pool = exp(-dot(d, d) * u_spread);
  float a = pool * (0.5 + 0.7 * n) + u_ambient * ribbon * (0.25 + 0.75 * n);
  vec3 col = mix(u_c1, u_c2, smoothstep(0.3, 0.75, w.y));
  col = mix(col, u_c3, smoothstep(0.55, 0.95, ribbon * w.x * 1.6));
  a = clamp(a * u_gain, 0.0, 0.85);
  a += (hash(gl_FragCoord.xy + fract(u_time)) - 0.5) * 0.012;
  a = max(a, 0.0);
  gl_FragColor = vec4(col * a, a);
}`;

interface Props {
  /** Focus point, 0..1 from the left and from the top. */
  x?: number;
  y?: number;
  /** Higher is tighter. */
  spread?: number;
  tone?: Tone;
  /** Overall strength, 0..1. */
  gain?: number;
  /** Page ground: no pool of light, only the slow ribbons. */
  ground?: boolean;
}

export function Aurora({ x = 0.5, y = 0.5, spread = 2.4, tone = 'accent', gain = 1, ground = false }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const target = useRef({ x, y, spread, tone, gain });
  target.current = { x, y, spread, tone, gain };
  const [fallback, setFallback] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current!;
    const gl = canvas.getContext('webgl', { premultipliedAlpha: true, alpha: true, antialias: false });
    if (!gl) {
      setFallback(true);
      return;
    }
    const compile = (type: number, src: string) => {
      const s = gl.createShader(type)!;
      gl.shaderSource(s, src);
      gl.compileShader(s);
      return s;
    };
    const prog = gl.createProgram()!;
    gl.attachShader(prog, compile(gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      setFallback(true);
      return;
    }
    gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, 'p');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const u = (n: string) => gl.getUniformLocation(prog, n);
    const U = { res: u('u_res'), time: u('u_time'), focus: u('u_focus'), spread: u('u_spread'), c1: u('u_c1'), c2: u('u_c2'), c3: u('u_c3'), gain: u('u_gain'), ambient: u('u_ambient') };

    const isDark = () => document.documentElement.dataset.theme !== 'light';
    const cur = { ...target.current, c: palette(tone, isDark()).map((c) => [...c]) };
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    // The page ground is large and slow, so it renders smaller and at a third of the frame rate.
    const scale = ground ? 0.2 : 0.5;
    let visible = true;
    let raf = 0;
    let frame = 0;
    const start = performance.now();

    const resize = () => {
      const w = Math.max(2, Math.round(canvas.clientWidth * scale));
      const h = Math.max(2, Math.round(canvas.clientHeight * scale));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
        gl.viewport(0, 0, w, h);
      }
    };
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    const io = new IntersectionObserver(([e]) => (visible = e.isIntersecting));
    io.observe(canvas);
    resize();

    const draw = (now: number) => {
      raf = requestAnimationFrame(draw);
      frame++;
      if (!visible || document.hidden || (ground && frame % 3)) return;
      const tg = target.current;
      const k = reduce ? 1 : 0.05;
      cur.x += (tg.x - cur.x) * k;
      cur.y += (tg.y - cur.y) * k;
      cur.spread += (tg.spread - cur.spread) * k;
      cur.gain += (tg.gain - cur.gain) * k;
      const dark = isDark();
      palette(tg.tone, dark).forEach((c, j) => c.forEach((v, i) => (cur.c[j][i] += (v - cur.c[j][i]) * k)));
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform2f(U.res, canvas.width, canvas.height);
      gl.uniform1f(U.time, reduce ? 14 : (now - start) / 1000);
      gl.uniform2f(U.focus, cur.x, 1 - cur.y);
      gl.uniform1f(U.spread, ground ? 60 : cur.spread);
      gl.uniform3fv(U.c1, cur.c[0]);
      gl.uniform3fv(U.c2, cur.c[1]);
      gl.uniform3fv(U.c3, cur.c[2]);
      gl.uniform1f(U.gain, cur.gain * (ground ? (dark ? 0.34 : 0.16) : dark ? 0.46 : 0.3));
      gl.uniform1f(U.ambient, ground ? 1 : 0.3);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    };
    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      io.disconnect();
      gl.getExtension('WEBGL_lose_context')?.loseContext();
    };
    // The shader is set up once; props flow in through `target`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className={`aurora tone-${tone}${ground ? ' is-ground' : ''}${fallback ? ' is-fallback' : ''}`}
      style={{ '--fx': `${x * 100}%`, '--fy': `${y * 100}%` } as React.CSSProperties}
      aria-hidden="true"
    >
      <canvas ref={canvasRef} />
    </div>
  );
}
