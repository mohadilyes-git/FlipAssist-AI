// Home: the cost meter in the blue hero card, whether everything's running,
// and who did the work. From /stats and /health.
import { type MouseEvent, useCallback, useEffect, useState } from "react";
import { api, type Stats } from "../api";
import type { Running, Tab } from "../App";
import { cost, writerName } from "../format";
import { GaugeIcon, Head, PenIcon, TagIcon } from "../ui";

type Props = { go: (tab: Tab) => void; count: number; running: Running; reload: () => Promise<void> };

const percent = (part: number, whole = 1) => (whole ? `${Math.round((part / whole) * 100)}%` : "–");

export function HomeScreen({ go, count, running, reload }: Props) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const [found] = await Promise.all([api.stats(), reload()]);
      setStats(found);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [reload]);
  useEffect(() => void load(), [load]);

  const link = (tab: Tab) => (e: MouseEvent) => {
    e.preventDefault();
    go(tab);
  };
  return (
    <>
      <Head icon={<GaugeIcon />} title="FlipAssist" sub="Code first · AI on this Mac · paid AI only when it must"
        right={<button type="button" className="link" disabled={busy} onClick={() => void load()}>{busy ? "Refreshing…" : "Refresh"}</button>} />
      {error && <p className="error" role="alert">{error}</p>}
      <div className="split tight">
        <section className="hero" aria-label="Done on this Mac">
          <p className="caps">Done on this Mac</p>
          <p className="hero-big">{stats ? percent(stats.done_on_this_mac) : "–"}</p>
          <p className="sub">of drafts never needed the paid backup</p>
          <a className="hero-pill" href="#style" onClick={link("style")}>
            <PenIcon size={12} stroke={2.4} />
            Learning from {count} of your messages
          </a>
          <div className="hero-rule" />
          <div className="hero-stats">
            <div><strong>{stats ? cost(stats.cost_per_100_drafts_pence) : "–"}</strong><span>per 100 drafts</span></div>
            <div><strong>{stats?.drafts ?? "–"}</strong><span>drafts</span></div>
            <div><strong>{stats ? percent(stats.ready, stats.drafts) : "–"}</strong><span>ready</span></div>
            <div><strong>{stats ? percent(stats.edited_before_sending, stats.approved) : "–"}</strong><span>edited</span></div>
          </div>
        </section>

        <section className="card">
          <p className="caps">Running</p>
          {runningRows(running).map((row) => (
            <div className="running" key={row.name}>
              <span className={row.ok ? "dot" : "dot bad"} aria-hidden="true" />
              <span>
                <strong>{row.name}</strong>
                <span className="sub">{row.state}</span>
              </span>
            </div>
          ))}
        </section>

        <section className="card">
          <p className="caps">Who did the work</p>
          {stats?.models.length ? stats.models.map((m) => (
            <div className="model" key={m.model}>
              <p className="model-head">
                <span>{writerName(m.model)}</span>
                <span className={m.cost_pence ? undefined : "free"}>{cost(m.cost_pence)}</span>
              </p>
              <span className="bar"><span style={{ width: percent(m.passed, m.attempts) }} /></span>
              <span className="sub">{m.passed} of {m.attempts} passed</span>
            </div>
          )) : <p className="sub">Nothing drafted yet.</p>}
        </section>

        <div className="buttons wide">
          <a className="second" href="#listing" onClick={link("listing")}><TagIcon size={16} />List on eBay</a>
          <a className="main" href="#message" onClick={link("message")}>Message a seller</a>
        </div>
      </div>
    </>
  );
}

function runningRows(running: Running): { name: string; state: string; ok: boolean }[] {
  if (running === null) return [{ name: "FlipAssist's API", state: "Checking…", ok: true }];
  if (running === "down") {
    return [{ name: "FlipAssist's API", state: "Not running: start it with .venv/bin/uvicorn flip.api:app", ok: false }];
  }
  return [
    { name: writerName(running.local_model), ok: running.local_running,
      state: running.local_running ? "Running" : "Not running: start it with ollama serve" },
    { name: writerName(running.api_model), ok: running.api_key_set,
      state: running.api_key_set ? "Ready if Gemma's answer fails a check" : "No key: local only" },
    { name: "API key", ok: running.flip_api_key_set, state: running.flip_api_key_set ? "Set" : "Missing: every draft is refused" },
  ];
}
