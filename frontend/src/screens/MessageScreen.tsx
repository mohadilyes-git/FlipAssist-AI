// AI message: the listing on the left; on the right your price (three cards
// and a line to slide it along), whether to say the flaw, and the message. Code
// sets the starting prices and checks every draft; your own sentences (or
// AlertFlip's) write it, with no AI, around the reason flip-wording-4b words.
// Only Rewrite has an AI write: Gemma 3 4B rewords it (14 Oct). Nothing is sent
// from here: you copy it into the marketplace, and approving it teaches your style.
import { useEffect, useMemo, useState } from "react";
import { api, type FlawsSaid, type Kind, type Listing, type MessageDraft, type ReasonCheck } from "../api";
import { cost, readBy, reasonLine, seconds, writerName } from "../format";
import { gapOf, lowerPrice, money, morePrice, sliderRange, toPence } from "../prices";
import { CheckIcon, ChevronIcon, Chip, Head, paidReason, PriceSlider, SparkleIcon, Steps, Warn, WarningIcon } from "../ui";

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
const MY_STYLE_KEY = "flipassist.myStyle"; // "off" when you turned My style off
const MARKETPLACE = "facebook";
/** what happened when you approved: copied or not, and whether it joined your style */
type Approval = { copied: boolean; edited: boolean; saved: boolean };
/** the draft on screen, and keptBy: the model that checked a reason Claude Haiku 5.5 flagged and kept it (4 Nov).
 * The screen's own, never sent: the API's reason.by stays the model that worded it, as it's credited */
type OnScreen = MessageDraft & { keptBy?: string };

/** Who kept a flagged reason, from the check's answer (4 Nov). Its reason says "flagged, kept" with the model that
 * worded it as by, whoever kept it, so the fix's own step tells: the fixer (Claude Sonnet 5.5) kept it when its step
 * answered and no fix of its was left out of the message (problems say why one wasn't put in). With no fix step (none
 * set up) or a failed one (it couldn't answer), nobody did, and the line stays "kept as written". The fix is the paid
 * step after the check's, whichever models .env names (15 Nov review: not by its name) */
function keeper(done: ReasonCheck): string | undefined {
  if (done.reason.checked !== "flagged, kept" || done.problems.length) return undefined;
  const fix = done.attempts.filter(paidReason)[1];
  return fix && !fix.problems.length ? fix.model : undefined;
}

/** onCheckPrice(title, description, read): the listing goes to AI UK price estimate, which opens and checks it (14
 * Nov), with the flaws its draft's reader found and who that was, when the draft is of this listing (9 Nov) */
/** hasStyle: My style has learned something (4 Nov: until then its On/Off is greyed out, with Set up my style beside it,
 * onSetUp opening the setup) */
/** checker: the model /health names for the reason's check (FLIP_WORDING_CHECK), named on the reason's line */
export function MessageScreen({ onApproved, onCheckPrice, hasStyle = true, onSetUp, checker }: {
  onApproved?: () => void;
  onCheckPrice?: (title: string, description: string, read?: { flaws: string[]; readBy: string }) => void;
  hasStyle?: boolean;
  onSetUp?: () => void;
  checker?: string;
}) {
  const [title, setTitle] = useState("");
  const [asking, setAsking] = useState("");
  const [description, setDescription] = useState("");
  const [kind, setKind] = useState<Kind>("lower");
  const [moved, setMoved] = useState<Partial<Record<Kind, number>>>({});
  // each card's own choice (14 Oct): at Offer lower you pick Yes or No yourself, and the counts come once you click
  // Yes; at Pay asking and Offer more saying you don't mind the flaw starts at Yes (4 Nov, the owner: "it become on
  // the yes always at the start unless they change it"), and how many flaws to say is still yours to pick
  // Yes to start with for every kind of offer (9 Nov, the owner: "make say flaws on like pay asking price and offer
  // more"): an offer lower gives its flaws as the reason unless you pick No; how many is still yours to pick
  const [mentions, setMentions] = useState<Record<Kind, Mention | null>>({ lower: "yes", asking: "yes", more: "yes" });
  const [counts, setCounts] = useState<Record<Kind, FlawsSaid | null>>({ lower: null, asking: null, more: null });
  const mention = mentions[kind];
  const flaws = counts[kind]; // how many: none picked until you pick (14 Oct)
  const setMention = (m: Mention) => setMentions((now) => ({ ...now, [kind]: m }));
  const setFlaws = (said: FlawsSaid) => setCounts((now) => ({ ...now, [kind]: said }));
  const [pickFlaws, setPickFlaws] = useState(false); // you wrote without picking how many: the row turns red
  const [pickMention, setPickMention] = useState(false); // you wrote without picking Yes or No: that row turns red
  const [draft, setDraft] = useState<OnScreen | null>(null);
  const [draftedFor, setDraftedFor] = useState(""); // the title and description the draft on screen was made from
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // My style On or Off (14 Oct, the owner): Off writes the default way, and a message approved then isn't learned from.
  // Remembered on this device
  const [myStyle, setMyStyle] = useState(() => {
    try {
      return localStorage.getItem(MY_STYLE_KEY) !== "off";
    } catch {
      return true;
    }
  });
  const pickStyle = (on: boolean) => {
    setMyStyle(on);
    try {
      localStorage.setItem(MY_STYLE_KEY, on ? "on" : "off");
    } catch {
      // private storage blocked: it stays as picked until the app restarts
    }
  };
  const [approval, setApproval] = useState<Approval | null>(null);
  // a draft belongs to the listing it was written from: change the title or the description and it goes, so you
  // write one for the listing as it is now (3 Oct; a draft that arrives for the old one goes too)
  useEffect(() => {
    if (draft && draftedFor !== JSON.stringify([title, description])) {
      setDraft(null);
      setText("");
      setApproval(null);
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

  // the message is always the usual length: Make it longer is gone (14 Oct, the owner: "remove that one")
  async function write(overrides: { rewrite_of?: string } = {}) {
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
        length: "usual",
        previous: null,
        // no AI writing, except Rewrite: Gemma 3 4B rewords the message on screen (14 Oct)
        writer: overrides.rewrite_of ? "ai" : "template",
        rewrite_of: overrides.rewrite_of ?? null,
        check_later: true,
        style: myStyle && hasStyle,
        // the same listing again, any kind of offer (9 Nov, the owner: "get the flaws that the reader found straight
        // from the previous request do not read it again"): its reading goes back as it is, and so does its reason
        // (it may be Sonnet's fix) for Rewrite, or once its check is done; a listing you've changed since is read and
        // worded again (3 Oct: a new listing was given the last one's "there's a scratch on the screen")
        reading: draft && draftedFor === thisListing ? { flaws: draft.reading.flaws, quotes: draft.reading.quotes,
          pickup: draft.reading.pickup, no_offers: draft.reading.no_offers, read_by: draft.reading.read_by } : null,
        reason: draft?.reason && draftedFor === thisListing
          && (overrides.rewrite_of || ["ok", "fixed", "flagged, kept"].includes(draft.reason.checked))
          ? { ...draft.reason, quotes: worded(draft) } : null,
      });
      if (!found.message && overrides.rewrite_of) {
        // no new version passed the checks, or none could be tried (15 Nov review): Gemma 3 4B not installed, Ollama
        // off or too slow, and a model on this device that can't answer is never sent to Claude in its place
        // (flip.attempts: "…, and nothing was sent to Claude Sonnet 5.5 (paid) instead"). The one on screen stays
        const couldnt = found.reasons.find((r) => r.includes("nothing was sent to"));
        setError(couldnt ? `Rewrite couldn't run: ${couldnt}. Your message is unchanged`
          : "No new wording passed the checks, so your message is unchanged");
        return;
      }
      // Rewrite gives back the reason on screen word for word, so who kept it is still said (4 Nov); a reason worded
      // again comes back "pending", and its own check says
      const same = overrides.rewrite_of && found.reason?.checked === "flagged, kept"
        && found.reason.clause === draft?.reason?.clause;
      setDraft({ ...found, keptBy: same ? draft?.keptBy : undefined });
      setDraftedFor(thisListing);
      setText(found.message ?? "");
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
    const update = (change: (d: OnScreen) => OnScreen) =>
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
      update((d) => ({ ...d, message: done.message, reason: done.reason, keptBy: keeper(done),
        attempts: [...d.attempts, ...done.attempts],
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
      const done = await api.approve(draft.draft_id, text, myStyle);
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
                placeholder="iPhone 13 128GB Blue" aria-describedby="supported-items" />
            </label>
            {/* 9 Nov, the owner: only listings FlipAssist supports (the API refuses others, flip.prices.supported) */}
            <p className="sub" id="supported-items">iPhones, Samsung phones and MacBooks</p>
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
            {/* 4 Nov, the owner: "when there's no my style just please grey it out and put set up my style when
                clicked it takes to the setting up" */}
            <div className={hasStyle ? "chips say-flaw" : "chips say-flaw greyed"} role="group" aria-label="My style">
              <span className="label">My style</span>
              <Chip on={myStyle && hasStyle} label="On" onClick={() => pickStyle(true)} disabled={!hasStyle} />
              <Chip on={!myStyle || !hasStyle} label="Off" onClick={() => pickStyle(false)} disabled={!hasStyle} />
              {!hasStyle && onSetUp && (
                <button type="button" className="second set-up" onClick={onSetUp}>Set up my style</button>
              )}
            </div>
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
            <>
              <Drafted draft={shown} text={text} setText={setText} busy={busy} approval={approval} checker={checker}
                onRewrite={() => void write({ rewrite_of: text })} onApprove={() => void approve()} />
              {/* 4 Nov, the owner: "add a button after it drafts a msg send the listing to ai uk price estimate": the
                  title and description go to that tab, which opens and checks them */}
              {onCheckPrice && (
                <button type="button" className="second" disabled={!title.trim()}
                  onClick={() => onCheckPrice(title, description, shown && draftedFor === JSON.stringify([title, description])
                    ? { flaws: shown.reading.quotes ?? shown.reading.flaws, readBy: shown.reading.read_by } : undefined)}>
                  Check the UK price
                </button>
              )}
            </>
          ) : (
            <>
              <p className="note">Code sets the price and checks every draft before you see it.</p>
              <button type="button" className="main" aria-busy={busy} disabled={busy || !prices || !title.trim()}
                onClick={() => void write()}>
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
 * sentences (its quotes), else its flaws. Haiku's check reads these, and Rewrite sends them back. */
const worded = (draft: MessageDraft) => draft.reason_from ?? draft.reading.quotes ?? draft.reading.flaws;

type DraftedProps = {
  draft: OnScreen;
  text: string;
  setText: (text: string) => void;
  busy: boolean;
  approval: Approval | null;
  checker?: string;
  onRewrite: () => void;
  onApprove: () => void;
};

function Drafted({ draft, text, setText, busy, approval, checker, onRewrite, onApprove }: DraftedProps) {
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
        {draft.reason && <p className="sub">{reasonLine(draft.reason, draft.keptBy, checker)}</p>}
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
          {approval.saved && <p className="saved-style">Saved to My style</p>}
        </>
      )}
    </>
  );
}
