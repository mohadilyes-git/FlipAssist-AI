// AI message: the listing on the left; on the right your price (three cards
// and a line to slide it along), how it's written, and the message. Code sets
// the starting prices and checks every draft; your own sentences (or the AI)
// write it. Nothing is sent from here: you copy it into the marketplace, and
// approving it teaches your style.
import { useMemo, useState } from "react";
import { api, type Kind, type MessageDraft, type Writer } from "../api";
import { cost, MARKETPLACES, readBy, seconds, writerName } from "../format";
import { gapOf, lowerPrice, money, morePrice, sliderRange, toPence } from "../prices";
import { CheckIcon, ChevronIcon, Chip, Head, PriceSlider, SparkleIcon, Steps, Warn, WarningIcon } from "../ui";

type Mention = "auto" | "yes" | "no";
const MENTION: Record<Mention, boolean | null> = { auto: null, yes: true, no: false };
const KINDS: Kind[] = ["lower", "asking", "more"];
const LABEL: Record<Kind, string> = { lower: "Offer lower", asking: "Pay asking", more: "Offer more" };
/** what happened when you approved: copied or not, and whether it joined your style */
type Approval = { copied: boolean; edited: boolean; saved: boolean };

export function MessageScreen({ onApproved }: { onApproved?: () => void }) {
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
  const [approval, setApproval] = useState<Approval | null>(null);

  const askingPence = toPence(asking);
  // each card's price: where you slid it, or the price code starts from (under £1 isn't a price to offer on)
  const prices = useMemo(() => {
    if (askingPence === null || askingPence < 100) return null;
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
    setApproval(null);
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
      setText(found.message ?? "");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // the new price goes into the message, every other word stays (your edits too)
  function slide(to: number) {
    if (!prices || kind === "asking") return;
    const from = prices[kind];
    setMoved((now) => ({ ...now, [kind]: to }));
    if (draft && draft.kind === kind) setText((now) => now.split(money(from)).join(money(to)));
  }

  async function approve() {
    if (!draft || !text.trim()) return;
    let copied = true;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      copied = false; // the browser said no: the message is still on screen to copy by hand
    }
    try {
      const done = await api.approve(draft.draft_id, text);
      setApproval({ copied, edited: done.edited, saved: done.saved_to_style });
      if (done.saved_to_style) onApproved?.();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const shown = draft && draft.kind === kind ? draft : null;
  return (
    <>
      <Head icon={<SparkleIcon />} title="AI message" sub="Pick your price · we write the message" />
      <div className="split">
        <div className="stack">
          {error && <p className="error" role="alert">{error}</p>}
          <section className="card" aria-label="The listing">
            <label className="field">
              <span>Listing title</span>
              <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300}
                placeholder="iPhone 13 128GB Blue" />
            </label>
            <div className="pair">
              <label className="field">
                <span>Asking price</span>
                <input className="input" value={asking} inputMode="decimal" placeholder="£220" onChange={(e) => {
                  setAsking(e.target.value);
                  setMoved({});
                }} />
              </label>
              <label className="field">
                <span>Marketplace</span>
                <span className="select">
                  <select className="input" value={marketplace} onChange={(e) => setMarketplace(e.target.value)}>
                    {MARKETPLACES.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                  </select>
                  <ChevronIcon size={14} stroke={2.4} />
                </span>
              </label>
            </div>
            <label className="field">
              <span>The seller's description</span>
              <textarea className="input" rows={4} value={description} maxLength={5000}
                onChange={(e) => setDescription(e.target.value)} placeholder="Flaws, where to collect, &quot;no offers&quot;…" />
            </label>
          </section>
        </div>

        <div className="stack">
          <div className="prices" role="radiogroup" aria-label="Your price">
            {KINDS.map((k) => {
              const price = prices?.[k];
              const gap = price != null && prices ? gapOf(price, prices.asking) : null;
              return (
                <button type="button" key={k} className="price" role="radio" aria-checked={kind === k}
                  onClick={() => setKind(k)}>
                  <span className="price-label">{LABEL[k]}</span>
                  <span className="price-value">{price != null ? money(price) : "–"}</span>
                  <span className={`price-gap ${gap?.tone ?? ""}`}>{gap?.text ?? "enter a price"}</span>
                </button>
              );
            })}
          </div>

          {prices && range && range.max > range.min && (
            <PriceSlider value={prices[kind]} min={range.min} max={range.max} step={range.step}
              label={`${LABEL[kind]} price`} onChange={slide} />
          )}

          {kind === "lower" && draft?.reading.no_offers && <Warn>The seller says no offers</Warn>}

          <div className="chips" role="group" aria-label="How it's written">
            <span className="label">Say the flaw</span>
            {(["auto", "yes", "no"] as Mention[]).map((m) => (
              <Chip key={m} on={mention === m} label={m === "auto" ? "My style" : m === "yes" ? "Yes" : "No"}
                onClick={() => setMention(m)} />
            ))}
            <span className="chips-divider" aria-hidden="true" />
            <span className="label">Writer</span>
            {(["auto", "template", "ai"] as Writer[]).map((w) => (
              <Chip key={w} on={writer === w} label={w === "auto" ? "Auto" : w === "template" ? "No AI" : "AI"}
                onClick={() => setWriter(w)} />
            ))}
          </div>

          {shown ? (
            <Drafted draft={shown} text={text} setText={setText} busy={busy} approval={approval}
              onLonger={() => void write("longer", { previous: text })}
              onAnswer={(yes) => {
                setMention(yes ? "yes" : "no");
                void write("usual", { mention: yes });
              }}
              onRewrite={() => void write("usual")} onApprove={() => void approve()} />
          ) : (
            <>
              <p className="note">Code sets the price and checks every draft before you see it.</p>
              <button type="button" className="main" aria-busy={busy} disabled={busy || !prices || !title.trim()}
                onClick={() => void write("usual")}>
                {busy ? "Writing…" : "Write my message"}
              </button>
            </>
          )}
        </div>
      </div>
    </>
  );
}

type DraftedProps = {
  draft: MessageDraft;
  text: string;
  setText: (text: string) => void;
  busy: boolean;
  approval: Approval | null;
  onLonger: () => void;
  onAnswer: (yes: boolean) => void;
  onRewrite: () => void;
  onApprove: () => void;
};

function Drafted({ draft, text, setText, busy, approval, onLonger, onAnswer, onRewrite, onApprove }: DraftedProps) {
  const [why, setWhy] = useState(false);
  const reading = draft.reading;
  const steps = [...reading.attempts, ...draft.attempts];
  return (
    <>
      <div className="message">
        <textarea className="input" aria-label="Your message" value={text} maxLength={5000} onChange={(e) => setText(e.target.value)}
          placeholder="No draft passed the checks: write your own here." />
        {draft.note && <p className="orange">{draft.note}</p>}
        {draft.reasons.map((r) => <p className="orange" key={r}>{r}</p>)}
        <p className="end">
          <button type="button" className="link" onClick={onLonger} disabled={busy || !text.trim()}>Make it longer</button>
        </p>
      </div>

      {draft.ask && (
        <div className="card">
          <p className="ask">{draft.ask}</p>
          <div className="ask-buttons">
            <button type="button" disabled={busy} onClick={() => onAnswer(true)}>Yes, mention it</button>
            <button type="button" disabled={busy} onClick={() => onAnswer(false)}>No</button>
          </div>
        </div>
      )}

      <div className="tips">
        <p className="caps">Read from the listing</p>
        <p className="tags">
          {reading.flaws.map((f) => <span className="tag" key={f}>{f}</span>)}
          {reading.pickup && <span className="tag good">Collect: {reading.pickup}</span>}
          {reading.no_offers && <span className="tag warn">No offers</span>}
          {!reading.flaws.length && !reading.pickup && !reading.no_offers && <span className="sub">Nothing to note</span>}
        </p>
        <p className="sub">
          {draft.written_by ? writerName(draft.written_by) : "No draft passed"} · {seconds(steps)} · {cost(draft.cost_pence)} · {readBy(reading.read_by)}
        </p>
        {steps.length > 0 && (
          <button type="button" className="link" aria-expanded={why} onClick={() => setWhy(!why)}>
            Why · {steps.length} {steps.length === 1 ? "step" : "steps"}
            <ChevronIcon size={12} stroke={2.6} />
          </button>
        )}
        {why && <Steps attempts={steps} />}
      </div>

      <div className="buttons">
        <button type="button" className="second" aria-busy={busy} disabled={busy} onClick={onRewrite}>
          <SparkleIcon size={16} />
          {busy ? "Writing…" : "Rewrite"}
        </button>
        <button type="button" className="main" disabled={busy || !text.trim()} onClick={onApprove}>Copy &amp; approve</button>
      </div>

      {approval && (
        <>
          <p className={approval.copied ? "done-line" : "done-line warn"} role="status">
            {approval.copied ? <CheckIcon size={14} stroke={2.6} /> : <WarningIcon size={14} stroke={2.2} />}
            {!approval.copied ? "Couldn't copy: select the message and copy it by hand."
              : approval.edited ? "Copied and saved: you changed it first." : "Copied and saved: sent as drafted."}
          </p>
          {approval.saved && <p className="saved-style">Saved to your style</p>}
        </>
      )}
    </>
  );
}
