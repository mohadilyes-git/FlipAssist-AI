// Home, drawn like AlertFlip's home: a blue hero card with the cost meter, then
// whether everything's running and who did the work. From /health and /stats.
import { useCallback, useEffect, useState } from "react";
import { api, type Health, type Stats } from "../api";
import { cost, writerName } from "../format";
import { MainButton, MeterIcon, ScreenHead, SecondButton } from "../ui";

export function HomeScreen({ go }: { go: (tab: "message" | "listing") => void }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [h, s] = await Promise.all([api.health(), api.stats()]);
      setHealth(h);
      setStats(s);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => void load(), [load]);

  const percent = (n: number) => `${Math.round(n * 100)}%`;
  return (
    <div className="screen">
      <ScreenHead icon={<MeterIcon />} title="FlipAssist" sub="Code first · AI on this Mac · paid AI only when it must"
        right={<button type="button" className="link" onClick={() => void load()}>Refresh</button>} />

      {stats && (
        <section className="hero">
          <p className="hero-label">DONE ON THIS MAC</p>
          <p className="hero-big">{percent(stats.done_on_this_mac)}</p>
          <div className="hero-rule" />
          <div className="hero-stats">
            <div><strong>{cost(stats.cost_per_100_drafts_pence)}</strong><span>per 100 drafts</span></div>
            <div><strong>{stats.drafts}</strong><span>drafts</span></div>
            <div><strong>{stats.drafts ? percent(stats.ready / stats.drafts) : "–"}</strong><span>ready</span></div>
            <div><strong>{stats.approved ? percent(stats.edited_before_sending / stats.approved) : "–"}</strong><span>edited</span></div>
          </div>
        </section>
      )}

      {error && <p className="error" role="alert">{error}</p>}

      {health && (
        <section className="card">
          <p className="section-label">RUNNING</p>
          <div className="rows">
            <Status ok={health.local_running} name={writerName(health.local_model)}
              value={health.local_running ? "Running" : "Not running: start it with ollama serve"} />
            <Status ok={health.api_key_set} name={writerName(health.api_model)}
              value={health.api_key_set ? "Ready if Gemma's answer fails a check" : "No key: local only"} />
            <Status ok={health.flip_api_key_set} name="API key" value={health.flip_api_key_set ? "Set" : "Missing: every draft is refused"} />
          </div>
        </section>
      )}

      {stats && stats.models.length > 0 && (
        <section className="card">
          <p className="section-label">WHO DID THE WORK</p>
          <div className="rows">
            {stats.models.map((m) => (
              <div className="row" key={m.model}>
                <span className="row-name">{writerName(m.model)}</span>
                <span className="row-value">{m.passed} of {m.attempts} passed · {cost(m.cost_pence)}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="footer">
        <SecondButton label="List on eBay" onClick={() => go("listing")} />
        <MainButton label="Message a seller" onClick={() => go("message")} />
      </div>
    </div>
  );
}

function Status({ ok, name, value }: { ok: boolean; name: string; value: string }) {
  return (
    <div className="row">
      <span className="row-name"><span className={ok ? "dot ok" : "dot bad"} aria-hidden="true" />{name}</span>
      <span className="row-value">{value}</span>
    </div>
  );
}
