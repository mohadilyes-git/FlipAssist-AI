// The building blocks, drawn the way AlertFlip draws them: the screen head with
// its icon tile, the blue gradient main button, the outlined second button,
// the price slider, chips and notes.
import type { CSSProperties, ReactNode } from "react";
import { money } from "./prices";

export function ScreenHead({ icon, title, sub, right }: { icon: ReactNode; title: string; sub: string; right?: ReactNode }) {
  return (
    <div className="head">
      <span className="head-icon">{icon}</span>
      <div className="head-words">
        <h1>{title}</h1>
        <p>{sub}</p>
      </div>
      {right}
    </div>
  );
}

type ButtonProps = { label: string; onClick?: () => void; disabled?: boolean; type?: "button" | "submit"; icon?: ReactNode; title?: string };

export function MainButton({ label, onClick, disabled, type = "button" }: ButtonProps) {
  return (
    <button type={type} className="main" onClick={onClick} disabled={disabled}>
      {label}
    </button>
  );
}

export function SecondButton({ label, onClick, disabled, icon, title }: ButtonProps) {
  return (
    <button type="button" className="second" onClick={onClick} disabled={disabled} title={title}>
      {icon}
      {label}
    </button>
  );
}

export function Chip({ on, label, onClick }: { on: boolean; label: string; onClick: () => void }) {
  return (
    <button type="button" className={on ? "chip on" : "chip"} aria-pressed={on} onClick={onClick}>
      {label}
    </button>
  );
}

/** The offer price, a step at a time, along a line: AlertFlip's slider, as a range input. */
export function PriceSlider({ value, min, max, step, label, onChange }: {
  value: number; min: number; max: number; step: number; label: string; onChange: (value: number) => void;
}) {
  const at = max > min ? ((value - min) / (max - min)) * 100 : 0;
  return (
    <div className="slider">
      <input type="range" min={min} max={max} step={step} value={value} aria-label={label}
        aria-valuetext={money(value)} style={{ "--at": `${at}%` } as CSSProperties}
        onChange={(e) => onChange(Number(e.target.value))} />
      <div className="ends" aria-hidden="true">
        <span>{money(min)}</span>
        <span>{money(max)}</span>
      </div>
    </div>
  );
}

export function Note({ children, tone }: { children: ReactNode; tone?: "warn" }) {
  return <p className={tone === "warn" ? "note warn" : "note"}>{children}</p>;
}

export function Warn({ children }: { children: ReactNode }) {
  return (
    <p className="warn-row" role="note">
      <WarningIcon />
      {children}
    </p>
  );
}

// ── icons ───────────────────────────────────────────────────────────────────

const svg = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2,
  strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };

export const SparkleIcon = () => (
  <svg {...svg}><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" /><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z" /></svg>
);
export const TagIcon = () => (
  <svg {...svg}><path d="M20.6 13.4l-7.2 7.2a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8z" /><circle cx="7.5" cy="7.5" r="1.5" /></svg>
);
export const MeterIcon = () => (
  <svg {...svg}><path d="M3 12a9 9 0 0 1 18 0" /><path d="M12 12l4-4" /><path d="M5 19h14" /></svg>
);
export const WarningIcon = () => (
  <svg {...svg} width={14} height={14}><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4" /><path d="M12 17h.01" /></svg>
);
export const CameraIcon = () => (
  <svg {...svg}><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" /><circle cx="12" cy="13" r="4" /></svg>
);
