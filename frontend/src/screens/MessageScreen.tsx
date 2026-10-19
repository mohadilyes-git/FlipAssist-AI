// AI message: the listing on the left; on the right your price (three cards
// and a line to slide it along), whether to say the flaw, and the message. Code
// sets the starting prices and checks every draft; your own sentences (or
// AlertFlip's) write it, with no AI, around the reason flip-wording-4b words.
// Only Rewrite has an AI write: Gemma 3 4B rewords it (14 Oct). Nothing is sent
// from here: you copy it into the marketplace, and approving it teaches your style.
import { useEffect, useMemo, useState } from "react";
import { api, type FlawsSaid, type Kind, type Length, type Listing, type MessageDraft } from "../api";
import { cost, readBy, reasonLine, seconds, writerName } from "../format";
import { gapOf, lowerPrice, money, morePrice, sliderRange, toPence } from "../prices";
import { CheckIcon, ChevronIcon, Chip, Head, PriceSlider, SparkleIcon, Steps, Warn, WarningIcon } from "../ui";

type Mention = "yes" | "no";
const KINDS: Kind[] = ["lower", "asking", "more"];
const LABEL: Record<Kind, string> = { lower: "Offer lower", asking: "Pay asking", more: "Offer more" };
// how many of the listing's flaws an offer gives, the worst first (14 Oct): a lower offer's reason, or at Pay asking
// and Offer more the flaws you say you don't mind ("I don't mind that the screen is burnt"); yours to pick
const COUNTS: { said: FlawsSaid; label: string }[] = [{ said: 1, label: "1 flaw only" }, { said: 2, label: "2 flaws only" },
  { said: 3, label: "3 flaws only" }, { said: "all", label: "All flaws" }];
// Rewrite's AI (14 Oct: every message is written with no AI; only Rewrite rewords it with an AI)
const REWRITE_HINT = "Gemma 3 4B rewords it on this device, keeping the price, the facts and the checked reason word "
  + "for word; Claude Sonnet 5.5 (paid) does it when Gemma 3 4B's tries fail code's checks";
// the listing's marketplace, now there's none to pick (14 Oct): written for a listing you collect and pay cash for,
// unless its description says it's posted ("Postage only"), which the API reads from the description itself
const MARKETPLACE = "facebook";
/** what happened when you approved: copied or not, and whether it joined your style */
type Approval = { copied: boolean; edited: boolean; saved: boolean };

export function MessageScreen({ onApproved }: { onApproved?: () => void }) {
  const [title, setTitle] = useState("");
  const [asking, setAsking] = useState("");
  const [description, setDescription] = useState("");
  const [kind, setKind] = useState<Kind>("lower");
  const [moved, setMoved] = useState<Partial<Record<Kind, number>>>({});
  // each card's own choice (14 Oct): at Offer lower you pick Yes or No yourself, and the counts come once you click
  // Yes; at Pay asking and Offer more saying you don't mind it is optional, so it starts at No
  const [mentions, setMentions] = useState<Record<Kind, Mention | null>>({ lower: null, asking: "no", more: "no" });
  const [counts, setCounts] = useState<Record<Kind, FlawsSaid | null>>({ lower: null, asking: null, more: null });
  const mention = mentions[kind];
  const flaws = counts[kind]; // how many: none picked until you pick (14 Oct)
  const setMention = (m: Mention) => setMentions((now) => ({ ...now, [kind]: m }));
  const setFlaws = (said: FlawsSaid) => setCounts((now) => ({ ...now, [kind]: said }));
  const [pickFlaws, setPickFlaws] = useState(false); // you wrote without picking how many: the row turns red
  const [pickMention, setPickMention] = useState(false); // you wrote without picking Yes or No: that row turns red
  const [draft, setDraft] = useState<MessageDraft | null>(null);
  const [draftedFor, setDraftedFor] = useState(""); // the title and description the draft on screen was made from
  const [text, setText] = useState("");
  const [length, setLength] = useState<Length>("usual"); // the length on screen: Rewrite keeps it
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [approval, setApproval] = useState<Approval | null>(null);
  // a draft belongs to the listing it was written from: change the title or the description and it goes, so you
  // write one for the listing as it is now (3 Oct; a draft that arrives for the old one goes too)
  useEffect(() => {
    if (draft && draftedFor !== JSON.stringify([title, description])) {
      setDraft(null);
      setText("");
      setApproval(null);
      setLength("usual");
      setError("");
    }
  }, [title, description, draft, draftedFor]);

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
  // only an offer lower gives a flaw as its reason (14 Oct): paying asking or more never names one
  const saysFlaws = mention === "yes";

  async function write(asked: Length, overrides: { previous?: string; rewrite_of?: string } = {}) {
    if (!prices) return;
    if (mention === null) {
      setPickMention(true); // nothing is written until you pick Yes or No
      return;
    }
    if (saysFlaws && flaws === null) {
      setPickFlaws(true); // nothing is written until you pick how many flaws to say
      return;
    }
    setBusy(true);
    setError("");
    setApproval(null);
    try {
      const listing = { title, description, asking_price: (prices.asking / 100).toFixed(2), marketplace: MARKETPLACE };
      const thisListing = JSON.stringify([title, description]);
      const found = await api.draftMessage({
        listing,
        kind,
        offer: (prices[kind] / 100).toFixed(2),
        // lower: Yes or No; asking: never the flaw; more: your style decides whether to say it's in good condition
        // Yes: the flaws (at or over asking, as ones you don't mind); No: none, and at Offer more your style decides
        // whether to say it's in good condition
        mention: mention === "yes" ? true : kind === "more" ? null : false,
        flaws_said: saysFlaws ? flaws : null,
        length: asked,
        previous: overrides.previous ?? null,
        // no AI writing, except Rewrite: Gemma 3 4B rewords the message on screen (14 Oct)
        writer: overrides.rewrite_of ? "ai" : "template",
        rewrite_of: overrides.rewrite_of ?? null,
        check_later: true,
        // Make it longer and Rewrite keep the reason the message on screen gives (it may be Sonnet's fix), but only for
        // the same listing: a listing you've changed since gets its reason worded again (3 Oct: a new listing was
        // given the last one's "there's a scratch on the screen")
        reason: (overrides.previous ?? overrides.rewrite_of) && draft?.reason && draftedFor === thisListing
          ? { ...draft.reason, quotes: worded(draft) } : null,
      });
      const changing = overrides.previous ?? overrides.rewrite_of;
      if (!found.message && changing) {
        // no new version passed the checks: the one on screen stays, as it was
        setError(`${overrides.previous ? "No longer message" : "No new wording"} passed the checks, so your message is unchanged`);
        return;
      }
      setDraft(found);
      setDraftedFor(thisListing);
      setText(found.message ?? "");
      setLength(asked);
      if (found.reason?.checked === "pending" && found.message) void checkReason(found, listing);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // the draft is on screen already: Haiku checks its reason now, and a fix (Sonnet's) replaces the message only
  // while it's still the one drafted, never over your own edits
  async function checkReason(found: MessageDraft, listing: Listing) {
    const update = (change: (d: MessageDraft) => MessageDraft) =>
      setDraft((now) => (now && now.draft_id === found.draft_id ? change(now) : now));
    try {
      const done = await api.checkReason({
        draft_id: found.draft_id,
        // Haiku checks the reason against the sentences flip-wording worded it from (the picked ones, when you
        // picked how many flaws); code's checks use the flaws
        listing, flaws: found.reading.flaws, quotes: found.reason_from ?? found.reading.quotes ?? [],
        clause: found.reason!.clause, message: found.message!,
        kind: found.kind, offer_pence: found.offer_pence, by: found.reason!.by, // credited to the model that worded it
      });
      update((d) => ({ ...d, message: done.message, reason: done.reason, attempts: [...d.attempts, ...done.attempts],
        cost_pence: d.cost_pence + done.cost_pence,
        warnings: [...d.warnings, ...done.problems.filter((p) => !d.warnings.includes(p))] })); // why a fix didn't go in
      if (done.changed) setText((now) => (now === found.message ? done.message : now));
    } catch {
      update((d) => ({ ...d, reason: { ...d.reason!, checked: "not checked" } }));
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
            <label className="field">
              <span>Asking price</span>
              <input className="input asking" value={asking} inputMode="decimal" placeholder="£220" onChange={(e) => {
                setAsking(e.target.value);
                setMoved({});
              }} />
            </label>
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

          <div className="how-written">
            <div className={pickMention && mention === null ? "chips say-flaw flaw-counts missing" : "chips say-flaw"}
              role="group" aria-label="Say the flaw">
              <span className="label">{kind === "lower" ? "Say the flaw" : "Say you don't mind the flaw"}</span>
              {(["yes", "no"] as Mention[]).map((m) => (
                <Chip key={m} on={mention === m} label={m === "yes" ? "Yes" : "No"} onClick={() => {
                  setMention(m);
                  setPickMention(false);
                  if (m === "no") setPickFlaws(false);
                }} />
              ))}
              {pickMention && mention === null && <span className="flaw-pick" role="alert">Pick Yes or No</span>}
            </div>
            {saysFlaws && (
              <div className={pickFlaws ? "chips flaw-counts missing" : "chips flaw-counts"} role="group"
                aria-label="How many flaws to say">
                {COUNTS.map(({ said, label }) => (
                  <Chip key={label} on={flaws === said} label={label} onClick={() => {
                    setFlaws(said);
                    setPickFlaws(false);
                  }} />
                ))}
                {pickFlaws && <span className="flaw-pick" role="alert">Pick how many flaws to say</span>}
              </div>
            )}
          </div>

          {shown ? (
            <Drafted draft={shown} text={text} setText={setText} busy={busy} approval={approval}
              longer={length === "longer"}
              onLength={() => void (length === "longer" ? write("usual") : write("longer", { previous: text }))}
              onRewrite={() => void write(length, { rewrite_of: text })} onApprove={() => void approve()} />
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

/** The lines a draft's reason was worded from: the picked ones when you picked how many flaws, else the reader's whole
 * sentences (its quotes), else its flaws. Haiku's check reads these, and Make it longer and Rewrite send them back. */
const worded = (draft: MessageDraft) => draft.reason_from ?? draft.reading.quotes ?? draft.reading.flaws;

type DraftedProps = {
  draft: MessageDraft;
  text: string;
  setText: (text: string) => void;
  busy: boolean;
  approval: Approval | null;
  longer: boolean;
  onLength: () => void;
  onRewrite: () => void;
  onApprove: () => void;
};

function Drafted({ draft, text, setText, busy, approval, longer, onLength, onRewrite, onApprove }: DraftedProps) {
  const [why, setWhy] = useState(false);
  const reading = draft.reading;
  const steps = [...reading.attempts, ...draft.attempts];
  return (
    <>
      <div className="message">
        <textarea className="input" aria-label="Your message" value={text} maxLength={5000} onChange={(e) => setText(e.target.value)}
          placeholder="No draft passed the checks: write your own here." />
        {draft.warnings.map((w) => <Warn key={w}>{w}</Warn>)}
        {draft.note && <p className="orange">{draft.note}</p>}
        {draft.reasons.map((r) => <p className="orange" key={r}>{r}</p>)}
        <p className="end">
          <button type="button" className="link" onClick={onLength} disabled={busy || !text.trim()}>
            {longer ? "Make it shorter" : "Make it longer"}
          </button>
        </p>
      </div>

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
        {draft.reason && <p className="sub">{reasonLine(draft.reason)}</p>}
        {steps.length > 0 && (
          <button type="button" className="link" aria-expanded={why} onClick={() => setWhy(!why)}>
            Why · {steps.length} {steps.length === 1 ? "step" : "steps"}
            <ChevronIcon size={12} stroke={2.6} />
          </button>
        )}
        {why && <Steps attempts={steps} readings={reading.attempts.length}
          flagged={draft.reason?.checked === "fixed" || draft.reason?.checked === "flagged, kept"} />}
      </div>

      <div className="buttons">
        <button type="button" className="second" aria-busy={busy} disabled={busy} onClick={onRewrite} title={REWRITE_HINT}>
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
