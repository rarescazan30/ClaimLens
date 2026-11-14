import { Check, X } from 'lucide-react';
import { useState } from 'react';

const dismissed = new Set<string>();
const wasDismissed = (id: string) => {
  if (dismissed.has(id)) return true;
  try {
    return localStorage.getItem(`asigit-guide-${id}`) === '1';
  } catch {
    return false;
  }
};

/** A three-step "you are here" strip for someone opening the screen for the first time. */
export function Guide({ id, steps, current }: { id: string; steps: { title: string; body: string }[]; current: number }) {
  const [hidden, setHidden] = useState(() => wasDismissed(id));
  if (hidden) return null;
  return (
    <section className="guide" aria-label="How this screen works">
      <ol>
        {steps.map((s, i) => (
          <li key={s.title} className={i < current ? 'is-done' : i === current ? 'is-now' : ''} aria-current={i === current ? 'step' : undefined}>
            <span className="guide-n">{i < current ? <Check size={13} strokeWidth={3} /> : i + 1}</span>
            <div>
              <p className="guide-title">{s.title}</p>
              <p>{s.body}</p>
            </div>
          </li>
        ))}
      </ol>
      <button
        type="button"
        className="icon-btn"
        aria-label="Hide this guide"
        onClick={() => {
          dismissed.add(id);
          try {
            localStorage.setItem(`asigit-guide-${id}`, '1');
          } catch {
            /* ignore */
          }
          setHidden(true);
        }}
      >
        <X size={15} />
      </button>
    </section>
  );
}
