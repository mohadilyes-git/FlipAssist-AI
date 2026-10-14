// "Set up your style": reply to 6 listings the way you'd message their sellers. Your answers go to the API, which
// learns from them (a style card, a phrasebook, and the 3 closest past messages as examples for each new listing):
// nothing gets trained. On first launch, and from Your style (Do setup, or Redo setup: your new answers take the place
// of your last setup's).
import { useState } from "react";
import { api, type Kind, type Learned, type NewStyleMessage, type Style } from "../api";
import { lowerPrice, money, morePrice } from "../prices";
import { CheckIcon, Logo } from "../ui";
import { habitsOf, LearnedRow, lengthOf, remove, sentencesOf } from "./StyleScreen";

export type SetupStep = "welcome" | "cards" | "result";

type Props = {
  step: SetupStep;
  go: (step: SetupStep) => void;
  style: Style | null;
  onLearned: () => Promise<void>;
  /** leave the setup: back where you came from (Your style), or on to Home the first time */
  onLeave: () => void;
  /** opened from Your style (Do setup, Redo setup), not on first launch */
  again: boolean;
};

// each listing shows one way you might message a seller (3 Oct: no Vinted or posted-flaw card: the eBay AirPods
// card teaches posted deals, and how you give a flaw is the same posted or collected)
const LISTINGS: { title: string; price: number; market: string; description: string; kind: Kind; teaches: string }[] = [
  { title: "iPhone 13 128GB, cracked back", price: 220, market: "Facebook", kind: "lower", teaches: "whether you mention flaws",
    description: "Back glass cracked when I dropped it, screen perfect. Battery 86%. Collection from Leeds LS6." },
  { title: "PS5 Disc Edition + 2 pads", price: 300, market: "Facebook", kind: "lower", teaches: "your plain offer",
    description: "Works perfectly, boxed with both controllers. Collect from Bradford BD1." },
  { title: "AirPods Pro 2", price: 120, market: "eBay", kind: "lower", teaches: "how you write when you can't collect",
    description: "Used a few times, all tips included. Postage only." },
  { title: "iPhone 12 64GB, scratches", price: 140, market: "Gumtree", kind: "lower", teaches: "small flaws",
    description: "Light scratches on the screen, does not affect use. Unlocked. Collect Leeds LS2." },
  { title: "MacBook Air M1 8GB", price: 450, market: "Facebook", kind: "asking", teaches: "paying full price",
    description: "Great condition, charger included. Price is firm, no offers." },
  { title: "Dyson V11 Absolute", price: 180, market: "Facebook", kind: "more", teaches: "offering more to hold it",
    description: "All attachments, new filter fitted. Lots of interest, first to collect." },
];
const OFFER: Record<Kind, (asking: number) => number> = { lower: lowerPrice, asking: (asking) => asking, more: morePrice };
const OFFER_LABEL: Record<Kind, string> = { lower: "Offer lower", asking: "Pay asking", more: "Offer more" };
const WAYS = [
  ["Style card", "your greeting, length and habits"],
  ["Phrasebook", "sentences you use again and again"],
  ["Closest past messages", "the 3 most like a new listing become examples"],
];

export function Setup({ step, go, style, onLearned, onLeave, again }: Props) {
  const [at, setAt] = useState(0);
  const [answers, setAnswers] = useState(() => LISTINGS.map(() => ""));
  const [learned, setLearned] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  /** Your answers, in place of your last setup's. Every one skipped: nothing is sent, and your style stays as it was. */
  async function learn(messages: NewStyleMessage[]) {
    setError("");
    if (messages.length) {
      setBusy(true);
      try {
        await api.setUpStyle(messages);
        await onLearned();
      } catch (e) {
        setError((e as Error).message);
        return;
      } finally {
        setBusy(false);
      }
    }
    setLearned(messages.length);
    go("result");
  }

  const toCards = () => {
    setAt(0);
    go("cards");
  };

  if (step === "cards") {
    const listing = LISTINGS[at];
    const last = at === LISTINGS.length - 1;
    const next = (kept: string[]) => {
      if (!last) return setAt(at + 1);
      void learn(LISTINGS.map((l, i) => ({ title: l.title, price: String(l.price), marketplace: l.market.toLowerCase(),
        text: kept[i].trim() })).filter((m) => m.text));
    };
    const skip = () => {
      const kept = answers.map((a, i) => (i === at ? "" : a));
      setAnswers(kept);
      next(kept);
    };
    return (
      <>
        <div className="progress">
          <button type="button" className="link" onClick={() => (at ? setAt(at - 1) : go("welcome"))}>Back</button>
          <span className="dots">
            <span aria-hidden="true">
              {LISTINGS.map((_, i) => <span key={i} className={i === at ? "now" : i < at ? "done" : undefined} />)}
            </span>
            {at + 1} of {LISTINGS.length}
          </span>
        </div>
        <h1 className="step-title">How would you message this seller?</h1>
        <div className="split">
          <section className="card roomy" aria-label="The listing">
            <p className="listing-top"><span className="market">{listing.market}</span>Teaches {listing.teaches}</p>
            <p className="listing-title">{listing.title}</p>
            <p className="listing-price">{money(listing.price * 100)}</p>
            <p className="listing-text">{listing.description}</p>
            <p className="offer-row">
              <span className="label">Your offer</span>
              <span className="offer-chip">{OFFER_LABEL[listing.kind]} · {money(OFFER[listing.kind](listing.price * 100))}</span>
            </p>
          </section>
          <div className="stack">
            <textarea className="input answer" aria-label="Your message to this seller" value={answers[at]} maxLength={2000}
              placeholder="Write it the way you normally would." onChange={(e) => {
                const text = e.target.value;
                setAnswers((now) => now.map((a, i) => (i === at ? text : a)));
              }} />
            <p className="sub">Your words, typos and all. Skip any that don't fit how you buy.</p>
            {error && <p className="error" role="alert">{error}</p>}
            <div className="buttons">
              <button type="button" className="second" disabled={busy} onClick={skip}>Skip</button>
              <button type="button" className="main" aria-busy={busy} disabled={busy} onClick={() => next(answers)}>
                {!last ? "Next" : busy ? "Learning…" : "See my style"}
              </button>
            </div>
          </div>
        </div>
      </>
    );
  }

  if (step === "result") {
    // everything it learned, each yours to remove before you start: a removed one is gone, and never written
    const length = lengthOf(style);
    const rows = [...habitsOf(style), ...sentencesOf(style)];
    const removeRow = async (row: Learned) => {
      setError("");
      try {
        await remove(row, onLearned);
      } catch (e) {
        setError((e as Error).message);
      }
    };
    return (
      <div className="centre">
        <div className="welcome result">
          <span className="check-circle"><CheckIcon size={28} stroke={2.6} /></span>
          <p className="caps">{learned ? `Learned from ${learned} ${learned === 1 ? "message" : "messages"}` : "Nothing written"}</p>
          <h1 className="big-title">Your style</h1>
          {!learned && (
            <p className="sub">{again ? `You skipped all ${LISTINGS.length}, so your style stays as it was.`
              : `You skipped all ${LISTINGS.length}: do the setup any time from Your style.`}</p>
          )}
          {learned > 0 && rows.length > 0 && <p className="sub">This is what it'll put in your messages. Remove anything you don't want.</p>}
          {error && <p className="error" role="alert">{error}</p>}
          {(learned > 0 || again) && (
            <div className="hero result-card" aria-label="What it learned">
              {length && <p className="trait"><span>{length.k}</span><span>{length.v}</span></p>}
              {rows.map((row) => <LearnedRow key={row.key} row={row} onRemove={(r) => void removeRow(r)} kind="trait" />)}
              {!length && !rows.length && <p className="trait"><span>Nothing to learn from yet</span></p>}
            </div>
          )}
          <p className="sub">Every message you approve teaches it a bit more.</p>
          <button type="button" className="main full" onClick={onLeave}>{again ? "Done" : "Start"}</button>
        </div>
      </div>
    );
  }

  return (
    <div className="centre">
      <div className="welcome">
        <Logo big />
        <p className="caps">{again ? "Your style · about 3 minutes" : "First launch · about 3 minutes"}</p>
        <h1 className="big-title">Set up your style</h1>
        <p className="lead">
          Teach FlipAssist how you message sellers: reply to {LISTINGS.length} quick listings.
          {again && " Your answers take the place of your last setup's."}
        </p>
        <ol className="card ways">
          {WAYS.map(([name, what], i) => (
            <li key={name}>
              <span className="number">{i + 1}</span>
              <span><strong>{name}</strong><span className="sub">{what}</span></span>
            </li>
          ))}
        </ol>
        <div className="choose">
          <button type="button" className="second" onClick={onLeave}>{again ? "Go back" : "Skip for now"}</button>
          <button type="button" className="main" onClick={toCards}>Do the setup</button>
        </div>
        <p className="footnote">Nothing gets trained. It learns from your own messages.</p>
      </div>
    </div>
  );
}
