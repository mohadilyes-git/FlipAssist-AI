// Message the seller, drawn like AlertFlip's AI message sheet: pick your price
// on the cards and the slider, and the message is written for you. Code sets
// the starting prices and checks every draft; your own sentences (or the AI)
// write it; nothing is sent from here: you copy it into the marketplace.
import { useMemo, useState } from "react";
import { api, type Attempt, type Kind, type MessageDraft, type Writer } from "../api";
import { cost, MARKETPLACES, seconds, writerName } from "../format";
import { gapOf, lowerPrice, money, morePrice, sliderRange, toPence } from "../prices";
import { Chip, MainButton, Note, PriceSlider, ScreenHead, SecondButton, SparkleIcon, Warn } from "../ui";

type Mention = "auto" | "yes" | "no";
const MENTION: Record<Mention, boolean | null> = { auto: null, yes: true, no: false };
const KINDS: Kind[] = ["lower", "asking", "more"];
const LABEL: Record<Kind, string> = { lower: "Offer lower", asking: "Pay asking", more: "Offer more" };

export function MessageScreen() {
  const [title, setTitle] = useState("");
  const [asking, setAsking] = useState("");
  const [marketplace, setMarketplace] = useState("facebook");
  const [description, setDescription] = useState("");
  const [kind, setKind] = useState<Kind>("lower");
  const [moved, setMoved] = useState<Partial<Record<Kind, number>>>({});
  const [mention, setMention] = useState<Mention>("auto");
  const [writer, setWriter] = useState<Writer>("auto");
  const [draft, setDraft] = useState<MessageDraft | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  const askingPence = toPence(asking);
  // each card's price: where you slid it, or the price code starts from
  const prices = useMemo(() => {
    if (askingPence === null || askingPence <= 0) return null;
    return {
      lower: moved.lower ?? lowerPrice(askingPence),
      asking: askingPence,
      more: moved.more ?? morePrice(askingPence),
    };
  }, [askingPence, moved]);
  const range = prices && kind !== "asking" ? sliderRange(prices.asking, kind) : null;

  async function write(length: "usual" | "longer", overrides: { mention?: boolean | null; previous?: string } = {}) {
    if (!prices) return;
    setBusy(true);
    setError("");
    setSaved("");
    try {
      const found = await api.draftMessage({
        listing: { title, description, asking_price: (prices.asking / 100).toFixed(2), marketplace },
        kind,
        offer: (prices[kind] / 100).toFixed(2),
        mention: overrides.mention !== undefined ? overrides.mention : MENTION[mention],
        length,
        previous: overrides.previous ?? null,
        writer,
      });
      setDraft(found);
      // the message says the price you picked, even before the API takes a picked price
      const drafted = found.message ?? "";
      setText(found.offer_pence !== prices[kind] ? drafted.split(found.offer).join(money(prices[kind])) : drafted);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // AlertFlip's slider: the new price goes into the message, every other word stays
  function slide(to: number) {
    if (!prices || kind === "asking") return;
    const from = prices[kind];
    setMoved((now) => ({ ...now, [kind]: to }));
    if (draft && draft.kind === kind) setText((now) => now.split(money(from)).join(money(to)));
  }

  async function approve() {
    if (!draft || !text.trim()) return;
    try {
      await navigator.clipboard?.writeText(text);
    } catch {
      // the browser can block copying: the message is still on screen
    }
    try {
      const done = await api.approve(draft.draft_id, text);
      setSaved(done.edited ? "Copied and saved: you changed it first." : "Copied and saved: sent as drafted.");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const shown = draft && draft.kind === kind ? draft : null;
  return (
    <form className="screen" onSubmit={(e) => {
      e.preventDefault();
      void write("usual");
    }}>
      <ScreenHead icon={<SparkleIcon />} title="AI message" sub="Pick your price · we write the message" />

      <section className="card fields">
        <label>
          <span>Listing title</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={300} placeholder="iPhone 13 128GB Blue" />
        </label>
        <div className="pair">
          <label>
            <span>Asking price</span>
            <input value={asking} onChange={(e) => {
              setAsking(e.target.value);
              setMoved({});
            }} required inputMode="decimal" placeholder="£220" />
          </label>
          <label>
            <span>Marketplace</span>
            <select value={marketplace} onChange={(e) => setMarketplace(e.target.value)}>
              {MARKETPLACES.map((m) => <option key={m} value={m}>{m[0].toUpperCase() + m.slice(1)}</option>)}
            </select>
          </label>
        </div>
        <label>
          <span>The seller's description</span>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={4} maxLength={5000}
            placeholder="Flaws, where to collect, &quot;no offers&quot;…" />
        </label>
      </section>

      <div className="approaches" role="radiogroup" aria-label="Your price">
        {KINDS.map((k) => {
          const price = prices?.[k];
          const gap = price != null && prices ? gapOf(price, prices.asking) : null;
          return (
            <button type="button" key={k} role="radio" aria-checked={kind === k} className={kind === k ? "approach on" : "approach"}
              onClick={() => setKind(k)}>
              <span className="approach-label">{LABEL[k]}</span>
              <span className="approach-price">{price != null ? money(price) : "–"}</span>
              <span className={`approach-gap ${gap?.tone ?? ""}`}>{gap?.text ?? "enter a price"}</span>
            </button>
          );
        })}
      </div>

      {prices && range && range.max > range.min && (
        <PriceSlider value={prices[kind]} min={range.min} max={range.max} step={range.step}
          label={`${LABEL[kind]} price`} onChange={slide} />
      )}

      {shown?.note && kind === "lower" && <Warn>The seller says no offers</Warn>}

      <div className="chips" aria-label="Options">
        <span className="chips-label">Say the flaw</span>
        {(["auto", "yes", "no"] as Mention[]).map((m) => (
          <Chip key={m} on={mention === m} label={m === "auto" ? "My style" : m === "yes" ? "Yes" : "No"} onClick={() => setMention(m)} />
        ))}
        <span className="chips-label">Writer</span>
        {(["auto", "template", "ai"] as Writer[]).map((w) => (
          <Chip key={w} on={writer === w} label={w === "auto" ? "Auto" : w === "template" ? "No AI" : "AI"} onClick={() => setWriter(w)} />
        ))}
      </div>

      {shown ? (
        <MessageResult draft={shown} text={text} setText={setText} busy={busy}
          onLonger={() => void write("longer", { previous: text })}
          onAnswer={(yes) => {
            setMention(yes ? "yes" : "no");
            void write("usual", { mention: yes });
          }} />
      ) : (
        <Note>Code sets the price and checks every draft before you see it.</Note>
      )}

      {error && <p className="error" role="alert">{error}</p>}
      {saved && <p className="saved" role="status">{saved}</p>}

      <div className="footer">
        {shown ? (
          <>
            <SecondButton label="Rewrite" icon={<SparkleIcon />} disabled={busy} onClick={() => void write("usual")} />
            <MainButton label="Copy & approve" disabled={busy || !text.trim()} onClick={() => void approve()} />
          </>
        ) : (
          <MainButton type="submit" label={busy ? "Writing…" : "Write my message"} disabled={busy || !prices} />
        )}
      </div>
    </form>
  );
}

type ResultProps = {
  draft: MessageDraft;
  text: string;
  setText: (text: string) => void;
  busy: boolean;
  onLonger: () => void;
  onAnswer: (yes: boolean) => void;
};

function MessageResult({ draft, text, setText, busy, onLonger, onAnswer }: ResultProps) {
  const reading = draft.reading;
  return (
    <>
      <label className="message">
        <span className="sr-only">Message</span>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={5}
          placeholder={draft.status === "ready" ? "" : "No draft passed the checks: write your own here."} />
      </label>
      {draft.note && <Note tone="warn">{draft.note}</Note>}
      {draft.reasons.length > 0 && <Note tone="warn">{draft.reasons.join(" · ")}</Note>}
      {draft.ask && (
        <div className="card ask">
          <p>{draft.ask}</p>
          <div className="ask-buttons">
            <SecondButton label="Yes, mention it" disabled={busy} onClick={() => onAnswer(true)} />
            <SecondButton label="No" disabled={busy} onClick={() => onAnswer(false)} />
          </div>
        </div>
      )}
      <button type="button" className="link" onClick={onLonger} disabled={busy || !text.trim()}>Make it longer</button>

      <div className="tips">
        <p className="tips-label">READ FROM THE LISTING</p>
        <p>
          {reading.flaws.length ? reading.flaws.map((f) => <span className="tag" key={f}>{f}</span>) : <span className="tip">No flaws</span>}
          {reading.pickup && <span className="tag good">Collect: {reading.pickup}</span>}
          {reading.no_offers && <span className="tag warn">No offers</span>}
        </p>
        <p className="tip">
          {writerName(draft.written_by)} · {seconds([...reading.attempts, ...draft.attempts])} · {cost(draft.cost_pence)}
          <span className="faint"> · read by {writerName(reading.read_by)}</span>
        </p>
        <Attempts attempts={[...reading.attempts, ...draft.attempts]} />
      </div>
    </>
  );
}

export function Attempts({ attempts }: { attempts: Attempt[] }) {
  const caught = attempts.filter((a) => a.problems.length);
  if (!attempts.length) return null;
  return (
    <details className="attempts">
      <summary>Why · {attempts.length} {attempts.length === 1 ? "step" : "steps"}{caught.length ? `, ${caught.length} caught by the checks` : ""}</summary>
      <ol>
        {attempts.map((a, i) => (
          <li key={i}>
            <strong>{writerName(a.model)}</strong> {a.problems.length ? `failed: ${a.problems.join(" | ")}` : "passed"}
            <span className="faint"> ({a.seconds.toFixed(1)}s, {cost(a.cost_pence)})</span>
          </li>
        ))}
      </ol>
    </details>
  );
}
