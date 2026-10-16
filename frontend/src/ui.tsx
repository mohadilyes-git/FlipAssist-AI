// The building blocks every screen shares, drawn the way the design draws them:
// the screen head with its icon tile, the logo, the price line you slide, chips,
// the orange warning row, the steps behind a draft, and the line icons.
import { type KeyboardEvent, type PointerEvent, type ReactNode, useRef } from "react";
import type { Attempt } from "./api";
import { cost, writerName } from "./format";
import { money } from "./prices";

export function Head({ icon, title, sub, right }: { icon: ReactNode; title: string; sub: string; right?: ReactNode }) {
  return (
    <div className="head">
      <span className="tile">{icon}</span>
      <div className="head-words">
        <h1>{title}</h1>
        <p>{sub}</p>
      </div>
      {right}
    </div>
  );
}

/** AlertFlip's bolt in its blue tile: 34px in the sidebar, 68px on Welcome. */
export function Logo({ big }: { big?: boolean }) {
  return (
    <span className={big ? "logo-tile big" : "logo-tile"} aria-hidden="true">
      <svg width={big ? 52 : 27} height={big ? 52 : 27} viewBox="0 0 100 100">
        <path d="M62 12 30 58h16l-4 30 28-40H74z" fill="rgba(255,255,255,.28)" />
        <path d="M56 14 24 60h16l-4 30 28-40H50z" fill="#fff" />
      </svg>
    </span>
  );
}

export function Chip({ on, label, onClick, hint }: { on: boolean; label: string; onClick: () => void; hint?: string }) {
  return (
    <button type="button" className="chip" aria-pressed={on} onClick={onClick} title={hint}>
      {label}
    </button>
  );
}

export function Warn({ children }: { children: ReactNode }) {
  return (
    <p className="warn-row">
      <WarningIcon size={14} stroke={2.2} />
      {children}
    </p>
  );
}

/** The offer price along a line, a step at a time: drag it, tap the line, or use the keys
 * (arrows one step, Page Up/Down five, Home/End the ends). */
export function PriceSlider({ value, min, max, step, label, onChange }: {
  value: number; min: number; max: number; step: number; label: string; onChange: (value: number) => void;
}) {
  const track = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const fit = (to: number) => Math.min(max, Math.max(min, min + Math.round((to - min) / step) * step));
  const move = (to: number) => {
    const next = fit(to);
    if (next !== value) onChange(next);
  };
  const at = (event: PointerEvent) => {
    const box = track.current?.getBoundingClientRect();
    if (!box?.width) return;
    move(min + Math.min(1, Math.max(0, (event.clientX - box.left) / box.width)) * (max - min));
  };
  const keys: Record<string, number> = {
    ArrowLeft: value - step, ArrowDown: value - step, ArrowRight: value + step, ArrowUp: value + step,
    PageDown: value - 5 * step, PageUp: value + 5 * step, Home: min, End: max,
  };
  const share = max > min ? Math.min(100, Math.max(0, ((value - min) / (max - min)) * 100)) : 0;
  return (
    <div className="slider">
      <div ref={track} className="slider-track" role="slider" tabIndex={0} aria-label={label}
        aria-valuemin={min} aria-valuemax={max} aria-valuenow={value} aria-valuetext={money(value)}
        onKeyDown={(e: KeyboardEvent) => {
          if (!(e.key in keys)) return;
          e.preventDefault();
          move(keys[e.key]);
        }}
        onPointerDown={(e) => {
          dragging.current = true;
          e.currentTarget.setPointerCapture?.(e.pointerId);
          at(e);
        }}
        onPointerMove={(e) => dragging.current && at(e)}
        onPointerUp={() => (dragging.current = false)}
        onPointerCancel={() => (dragging.current = false)}>
        <span className="slider-rail" />
        <span className="slider-fill" style={{ width: `${share}%` }} />
        <span className="slider-thumb" style={{ left: `${share}%` }} />
      </div>
      <div className="slider-ends" aria-hidden="true">
        <span>{money(min)}</span>
        <span>{money(max)}</span>
      </div>
    </div>
  );
}

/** Each step behind a draft: who tried it, whether the checks passed it, and what it took. */
/** One step behind a draft by its job and who did it (14 Oct): "Reading the listing · flip-reader-5 (on this
 * device)", "Wording the reason · flip-wording-4b (on this device)", "Checking the reason · Claude Haiku 5.5 (paid)",
 * "Fixing the reason · Claude Sonnet 5.5 (paid)", "Looking at the colour · …", "Writing the message · …" (or the
 * listing, on List on eBay). reading: the step read the listing. */
export function stepName(a: Attempt, reading: boolean, writing: "message" | "listing" = "message"): string {
  const who = writerName(a.model);
  if (reading) return `Reading the listing · ${who}`;
  if (a.colour_only) return `Looking at the colour · ${who}`;
  if (a.job === "reason") {
    const what = a.model.startsWith("claude-haiku") ? "Checking the reason" : a.model.startsWith("claude-sonnet")
      ? "Fixing the reason" : "Wording the reason";
    return `${what} · ${who}`;
  }
  return `Writing the ${writing} · ${who}`;
}

/** The steps behind a draft. readings: how many of the first attempts read the listing; flagged: Claude Haiku 5.5
 * flagged the reason (it was fixed, or kept as written), so its check says that, not "passed". */
export function Steps({ attempts, readings = 0, flagged = false, writing = "message" }: { attempts: Attempt[];
  readings?: number; flagged?: boolean; writing?: "message" | "listing" }) {
  return (
    <ol className="steps">
      {attempts.map((a, i) => (
        <li key={i}>
          <span className={a.problems.length ? "failed" : "passed"}>
            {stepName(a, i < readings, writing)}{" "}
            {a.problems.length ? `failed: ${a.problems.join("; ")}`
              : flagged && a.job === "reason" && a.model.startsWith("claude-haiku") ? "flagged it" : "passed"}
          </span>
          <span className="meta">{a.seconds.toFixed(1)}s · {cost(a.cost_pence)}</span>
        </li>
      ))}
    </ol>
  );
}

// ── icons: line icons on a 24 grid, 2px strokes, round ends ─────────────────

type IconProps = { size?: number; stroke?: number };

function icon(paths: ReactNode) {
  return function Icon({ size = 18, stroke = 2 }: IconProps) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke}
        strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {paths}
      </svg>
    );
  };
}

export const SparkleIcon = icon(<>
  <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
  <path d="M19 16l.7 1.8 1.8.7-1.8.7L19 21l-.7-1.8-1.8-.7 1.8-.7z" />
</>);
export const TagIcon = icon(<><path d="M3 12V4a1 1 0 0 1 1-1h8l9 9-9 9z" /><circle cx="7.5" cy="7.5" r="1.3" /></>);
export const PoundIcon = icon(<path d="M16.5 7.2A4 4 0 0 0 9.5 9v5.5c0 2-1 3.5-3 4.5h11M7 13h7" />);
export const GaugeIcon = icon(<><path d="M3.5 18a9 9 0 1 1 17 0" /><path d="m12 14 4-4" /></>);
export const PenIcon = icon(<path d="M4 20h4L19 9l-4-4L4 16zM13 7l4 4" />);
export const SunIcon = icon(<path d="M12 4V2M12 22v-2M4 12H2M22 12h-2M5.6 5.6 4.2 4.2M19.8 19.8l-1.4-1.4M5.6 18.4l-1.4 1.4M19.8 4.2l-1.4 1.4M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z" />);
export const MoonIcon = icon(<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />);
export const WarningIcon = icon(<><path d="M12 3 2 20h20z" /><path d="M12 10v4M12 17h.01" /></>);
export const CameraIcon = icon(<><path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" /></>);
export const CheckIcon = icon(<path d="m5 12 5 5L20 7" />);
export const CrossIcon = icon(<path d="M6 6l12 12M18 6 6 18" />);
export const TrashIcon = icon(<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />);
export const ChevronIcon = icon(<path d="m6 9 6 6 6-6" />);
export const PlusIcon = icon(<path d="M12 5v14M5 12h14" />);
