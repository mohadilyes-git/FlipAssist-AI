// Home: how much of drafting ran on this device and what it cost (the blue card, from /stats), what's running and
// what each part does (from /health), and who did the work. It loads afresh each time you open it, and again when
// you come back to the window (14 Oct: no Refresh button).
import { type MouseEvent, useCallback, useEffect, useState } from "react";
import { api, type Health, type Stats } from "../api";
import type { Running, Tab } from "../App";
import { cost, jobName, modelName } from "../format";
import { GaugeIcon, Head, PenIcon } from "../ui";

type Props = { go: (tab: Tab) => void; count: number; running: Running; reload: () => Promise<void> };
/** One line of the Running card. ok: true (green), false (red: something's wrong) or "off" (grey: switched off, as
 * set up). model: one of Ollama's models, on its own line under Ollama's. */
export type Row = { name: string; state: string; ok: boolean | "off"; model?: boolean };

const percent = (part: number, whole = 1) => (whole ? `${Math.round((part / whole) * 100)}%` : "–");

// what each of Ollama's models does, by the job /health names it for
const JOBS: Record<string, string> = {
  "reads listings": "reads the listing",
  "words the reason": "words the offer's reason",
  "sorts price flaws": "sorts the flaws for the UK price",
  "reads your style": "reads My style",
  "writes messages": "rewords a message when you click Rewrite, and writes eBay listings",
};
// ...and what does that job when the model isn't installed
const INSTEAD: Record<string, string> = {
  "reads listings": "Gemma 3 4B reads the listing instead",
  "words the reason": "code words the reason instead",
  "sorts price flaws": "code's rules sort the flaws instead",
  "reads your style": "code reads My style alone",
  "writes messages": "Rewrite and List on eBay can't run on this device",
};

export function HomeScreen({ go, count, running, reload }: Props) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [found] = await Promise.all([api.stats(), reload()]);
      setStats(found);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }, [reload]);
  useEffect(() => {
    void load();  // each time you open Home
    const again = () => void load();  // ...and when you come back to the window
    window.addEventListener("focus", again);
    return () => window.removeEventListener("focus", again);
  }, [load]);

  const link = (tab: Tab) => (e: MouseEvent) => {
    e.preventDefault();
    go(tab);
  };
  const checks = typeof running === "object" && running !== null && !!running.check_model;
  return (
    <>
      <Head icon={<GaugeIcon />} title="FlipAssist"
        sub={`Code first · FlipAssist's models and Gemma 3 4B on this device${checks
          ? ` · ${modelName((running as Health).check_model ?? "")} checks each reason` : ""}`} />
      {error && <p className="error" role="alert">{error}</p>}
      {/* the blue card with who did the work under it and what's running beside them, so a tall Running card leaves
          no gap (14 Oct); one column when it's narrow: the blue card, Running, then who did the work */}
      <div className="home">
        <div className="home-grid">
        <section className="hero home-hero" aria-label="Done by the models">
          <p className="caps">Done by the models</p>
          {/* every successful output (an answer that passed its checks), by every model, paid ones too: the "passed"
              numbers in Who did the work add up to it (14 Oct) */}
          <p className="hero-big">{stats ? stats.outputs.toLocaleString("en-GB") : "–"}</p>
          <p className="sub">successful outputs across all the models</p>
          <a className="hero-pill" href="#style" onClick={link("style")}>
            <PenIcon size={12} stroke={2.4} />
            Learning from {count} of your messages
          </a>
          <div className="hero-rule" />
          <div className="hero-stats">
            <div><strong>{stats ? cost(stats.cost_per_100_drafts_pence) : "–"}</strong><span>per 100 drafts</span></div>
            <div><strong>{stats?.drafts ?? "–"}</strong><span>drafts</span></div>
            <div><strong>{stats ? percent(stats.ready, stats.drafts) : "–"}</strong><span>ready</span></div>
            <div>
              <strong>{stats?.approved ? percent(stats.edited_before_sending, stats.approved) : "–"}</strong>
              <span>{stats?.approved ? `edited, of ${stats.approved} sent` : "edited · none sent yet"}</span>
            </div>
          </div>
        </section>

        <section className="card home-running" aria-label="Running">
          <p className="caps">Running</p>
          {runningRows(running).map((row) => (
            <div className={row.model ? "running model-line" : "running"} key={`${row.name} ${row.state}`}>
              <span className={row.ok === true ? "dot" : row.ok === "off" ? "dot off" : "dot bad"} aria-hidden="true" />
              <span>
                <strong>{row.name}</strong>
                <span className="sub">{row.state}</span>
              </span>
            </div>
          ))}
        </section>

        <section className="card home-work" aria-label="Who did the work">
          <p className="card-head">
            <span className="caps">Who did the work</span>
            {stats ? <span>{stats.outputs.toLocaleString("en-GB")} passed in all</span> : null}
          </p>
          {stats?.models.length ? stats.models.map((m) => (
            <div className="model" key={`${m.model} ${m.job}`}>
              <p className="model-head">
                <span>{modelName(m.model)} · {jobName(m.model, m.job)}</span>
                <span className={m.cost_pence ? undefined : "free"}>{cost(m.cost_pence)}</span>
              </p>
              <span className="bar"><span style={{ width: percent(m.passed, m.attempts) }} /></span>
              <span className="sub">{m.passed} of {m.attempts} passed</span>
            </div>
          )) : <p className="sub">Nothing drafted yet.</p>}
        </section>
        </div>
      </div>
    </>
  );
}

/** Ollama, then each model it's asked for on its own line, with its job; one that isn't installed is said, with what
 * does its job instead (6 Oct review: Home said every model was running whenever Ollama was). */
/** Whether Claude writes List on eBay's drafts (14 Oct), not this device's model. */
const claudeLists = (running: Health) => (running.listing_model ?? "").startsWith("claude");
// with Claude writing eBay listings, this device's writer only rewords messages
const job = (name: string, running: Health) =>
  name === "writes messages" && claudeLists(running) ? "rewords a message when you click Rewrite" : JOBS[name] ?? name;
const instead = (name: string, running: Health) =>
  name === "writes messages" && claudeLists(running) ? "Rewrite can't run on this device"
    : INSTEAD[name] ?? "code does its job instead";

export function ollamaRows(running: Health): Row[] {
  if (!running.local_running) {
    return [{ name: "Ollama", ok: false, state: "Not running: start it with ollama serve" }];
  }
  const models = running.models ?? [];
  const missing = models.filter((m) => !m.installed).length;
  return [
    { name: "Ollama", ok: true,
      state: missing ? `Running on this device, ${missing} of its models not installed` : "Running on this device" },
    ...models.map((m) => ({ name: modelName(m.name), model: true, ok: m.installed,
      state: m.installed ? job(m.job, running) : `Not installed: ${instead(m.job, running)}` })),
  ];
}

/** The paid models, each on its own line with what it does: Claude Haiku 5.5 only checks each reason; Claude Sonnet
 * 5.5 writes when this device's models can't (and fixes a reason the check flags). */
export function paidRows(running: Health): Row[] {
  const paid = (model: string) => `${modelName(model)} (paid)`;
  if (!running.api_key_set) {
    return [
      { name: paid("claude-haiku-5-5"), ok: "off", state: "Off: no Anthropic key, so reasons aren't checked" },
      { name: paid("claude-sonnet-5-5"), ok: "off", state: "Off: no Anthropic key, so everything runs on this device" },
    ];
  }
  const lister = claudeLists(running) ? running.listing_model! : "";
  const rows: Row[] = [running.check_model
    ? { name: paid(running.check_model), ok: true, state: lister === running.check_model
      ? "Checks each message's reason is sendable, and writes eBay listings"
      : "Only checks each message's reason is sendable" }
    : { name: paid("claude-haiku-5-5"), ok: "off", state: "Off in .env: reasons aren't checked" }];
  if (lister && lister !== running.check_model) rows.push({ name: paid(lister), ok: true, state: "Writes eBay listings" });
  // the checker by name: it flags the reasons the fixer rewrites (Claude Haiku 5.5 unless .env names another)
  const checker = modelName(running.check_model || "claude-haiku-5-5");
  const writes = lister
    ? `writes a message, reads a listing, or looks at the photos for the colour; and writes an eBay listing when ${modelName(lister)}'s fails the checks`
    : "writes a message or eBay listing, reads a listing, or looks at the photos for the colour";
  if (running.fix_model && running.fix_model === running.api_model) {
    rows.push({ name: paid(running.api_model), ok: true,
      state: `Fixes a reason ${checker} flags; when this device's models can't, ${writes}` });
  } else {
    rows.push({ name: paid(running.api_model), ok: true, state: `When this device's models can't: ${writes}` });
    if (running.fix_model) rows.push({ name: paid(running.fix_model), ok: true, state: `Fixes a reason ${checker} flags` });
  }
  return rows;
}

export function runningRows(running: Running): Row[] {
  if (running === null) return [{ name: "FlipAssist's API", state: "Checking…", ok: true }];
  if (running === "down") {
    return [{ name: "FlipAssist's API", state: "Not running: start it with .venv/bin/uvicorn flip.api:app", ok: false }];
  }
  return [
    ...ollamaRows(running),
    ...paidRows(running),
    { name: "AlertFlip API", ok: !!running.prices_api_set,
      state: running.prices_api_set ? "Fresh local sales data for the UK price estimate"
        : "Not set: add PRICES_URL and PRICES_KEY to .env" },
    { name: "FlipAssist API key", ok: running.flip_api_key_set,
      state: running.flip_api_key_set ? "Set" : "Missing: every draft is refused" },
  ];
}
