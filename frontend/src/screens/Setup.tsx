// First launch: "Set up your style". Reply to 8 listings, or paste messages
// you've already sent. Either way they go to the API, which learns from them
// with plain code (a style card, a phrasebook, and the 3 closest past messages
// as examples for each new listing): nothing gets trained.
import { useState } from "react";
import { api, type Kind, type NewStyleMessage, type Style } from "../api";
import { lowerPrice, money, morePrice } from "../prices";
import { CheckIcon, CrossIcon, Logo, PlusIcon } from "../ui";

export type SetupStep = "welcome" | "cards" | "paste" | "result";

type Props = {
  step: SetupStep;
  go: (step: SetupStep) => void;
  style: Style | null;
  onLearned: () => Promise<void>;
  onStart: () => void;
};

// each listing shows one way you might message a seller
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
  { title: "Nintendo Switch OLED", price: 210, market: "Vinted", kind: "lower", teaches: "Vinted offers",
    description: "Barely used, boxed with the dock. Can post or collect from York." },
  { title: "Dyson V11 Absolute", price: 180, market: "Facebook", kind: "more", teaches: "offering more to hold it",
    description: "All attachments, new filter fitted. Lots of interest, first to collect." },
  { title: "Apple Watch Series 7 45mm", price: 150, market: "eBay", kind: "lower", teaches: "flaws when posting",
    description: "Battery 82%, small mark on the case. Postage only." },
];
const OFFER: Record<Kind, (asking: number) => number> = { lower: lowerPrice, asking: (asking) => asking, more: morePrice };
const OFFER_LABEL: Record<Kind, string> = { lower: "Offer lower", asking: "Pay asking", more: "Offer more" };
const WAYS = [
  ["Style card", "your greeting, length and habits"],
  ["Phrasebook", "sentences you use again and again"],
  ["Closest past messages", "the 3 most like a new listing become examples"],
];

type Pasted = { id: number; title: string; price: string; text: string };
let made = 0;
const blank = (): Pasted => ({ id: ++made, title: "", price: "", text: "" });

export function Setup({ step, go, style, onLearned, onStart }: Props) {
  const [at, setAt] = useState(0);
  const [answers, setAnswers] = useState(() => LISTINGS.map(() => ""));
  const [pasted, setPasted] = useState(() => [blank(), blank(), blank()]);
  const [learned, setLearned] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function learn(messages: NewStyleMessage[]) {
    setError("");
    if (messages.length) {
      setBusy(true);
      try {
        await api.addStyleMessages(messages);
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
            <textarea className="input answer" aria-label="Your message to this seller" value={answers[at]}
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

  if (step === "paste") {
    const filled = pasted.filter((p) => p.text.trim());
    const edit = (id: number, change: Partial<Pasted>) =>
      setPasted((now) => now.map((p) => (p.id === id ? { ...p, ...change } : p)));
    return (
      <>
        <div className="paste-head">
          <button type="button" className="link" onClick={() => go("welcome")}>Back</button>
          <h1 className="step-title">Paste my messages</h1>
          <p className="sub">One box per message, with its listing title and price. 10–20 real offers works best.</p>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="pasted">
          {pasted.map((p, i) => (
            <section className="card" key={p.id} aria-label={`Message ${i + 1}`}>
              <p className="pasted-top">
                <span className="caps">Message {i + 1}</span>
                <button type="button" className="round-x" aria-label={`Remove message ${i + 1}`}
                  onClick={() => setPasted((now) => now.filter((x) => x.id !== p.id))}>
                  <CrossIcon size={11} stroke={3} />
                </button>
              </p>
              <div className="pasted-pair">
                <input className="input" aria-label="Listing title" placeholder="Listing title" value={p.title}
                  onChange={(e) => edit(p.id, { title: e.target.value })} />
                <input className="input" aria-label="Price" placeholder="£220" inputMode="decimal" value={p.price}
                  onChange={(e) => edit(p.id, { price: e.target.value })} />
              </div>
              <textarea className="input" rows={4} aria-label="Your message" placeholder="Hi mate, would you take £185 cash?"
                value={p.text} onChange={(e) => edit(p.id, { text: e.target.value })} />
            </section>
          ))}
          <button type="button" className="add-tile" onClick={() => setPasted((now) => [...now, blank()])}>
            <PlusIcon size={20} stroke={2.4} />
            Add another
          </button>
        </div>
        <div className="paste-foot">
          <button type="button" className="link" onClick={toCards}>Reply to 8 listings instead</button>
          <button type="button" className="main" aria-busy={busy} disabled={busy || !filled.length}
            onClick={() => void learn(filled.map((p) => ({ title: p.title.trim(), price: p.price.trim(), text: p.text.trim() })))}>
            {busy ? "Learning…" : filled.length ? `Learn from ${filled.length} message${filled.length > 1 ? "s" : ""}` : "Learn my style"}
          </button>
        </div>
      </>
    );
  }

  if (step === "result") {
    return (
      <div className="centre">
        <div className="welcome result">
          <span className="check-circle"><CheckIcon size={28} stroke={2.6} /></span>
          <p className="caps">Learned from {learned} {learned === 1 ? "message" : "messages"}</p>
          <h1 className="big-title">Your style</h1>
          <div className="hero result-card">
            {style?.traits.length ? style.traits.map((t) => (
              <p className="trait" key={t.k}><span>{t.k}</span><span>{t.v}</span></p>
            )) : <p className="trait"><span>Nothing to learn from yet: add messages any time from Your style</span></p>}
          </div>
          <p className="sub">Every message you approve teaches it a bit more.</p>
          <button type="button" className="main full" onClick={onStart}>Start</button>
        </div>
      </div>
    );
  }

  return (
    <div className="centre">
      <div className="welcome">
        <Logo big />
        <p className="caps">First launch · about 3 minutes</p>
        <h1 className="big-title">Set up your style</h1>
        <p className="lead">Teach FlipAssist how you message sellers: 8 quick listings, or paste messages you've already sent.</p>
        <ol className="card ways">
          {WAYS.map(([name, what], i) => (
            <li key={name}>
              <span className="number">{i + 1}</span>
              <span><strong>{name}</strong><span className="sub">{what}</span></span>
            </li>
          ))}
        </ol>
        <div className="choose">
          <button type="button" className="second" onClick={() => go("paste")}>Paste my messages</button>
          <button type="button" className="main" onClick={toCards}>Reply to 8 listings</button>
        </div>
        <p className="footnote">Nothing gets trained. It learns from your own messages.</p>
      </div>
    </div>
  );
}
