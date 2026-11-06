// Your style: what FlipAssist learned from your messages (the style card and the phrasebook, worked out by code, its
// gaps filled by our style reader where code checks what it found: nothing is trained on your messages), each thing
// yours to remove for good, and the messages it learns from, each one yours to delete. Do setup (Redo setup once
// you've done it) teaches it from 6 listings.
import { useEffect, useState } from "react";
import { api, type Learned, type Style, type StyleMessage } from "../api";
import { money, toPence } from "../prices";
import { Head, PenIcon, TrashIcon } from "../ui";

type Props = { style: Style | null; reload: () => Promise<void>; setUp: () => void };

/** "220" -> "£220"; a price that isn't one is shown as it was written */
export const priceText = (price: string) => {
  const pence = toPence(price);
  return pence === null ? price : money(pence);
};

/** Your sentences go in the phrasebook, wherever they're for: every message, one kind of offer ("Closing under
 * asking") or one marketplace ("Offer sentence on eBay and Vinted"); everything else is a habit on the style card. */
const isSentence = (row: Learned) => row.key.startsWith("phrase:") || row.key.startsWith("ask:");
// a removed one is gone for good (14 Oct): it isn't shown, the AI is told never to write it, and the checks refuse it
export const habitsOf = (style: Style | null) => (style?.learned ?? []).filter((row) => row.used && !isSentence(row));
export const sentencesOf = (style: Style | null) => (style?.learned ?? []).filter((row) => row.used && isSentence(row));
// how long your messages are isn't a thing it puts in, so it's shown, not removed
export const lengthOf = (style: Style | null) => style?.traits.find((t) => t.k === "Length");

/** Remove one thing your style learned, for good, then show your style as it is now. */
export async function remove(row: Learned, reload: () => Promise<void>) {
  await api.changeLearned(row.key, false);
  await reload();
}

/** One thing your style learned, with the button that removes it. */
export function LearnedRow({ row, onRemove, kind }: { row: Learned; onRemove: (row: Learned) => void; kind: "trait" | "phrase" }) {
  const button = (
    <button type="button" className="remove" aria-label={`Remove “${row.value}” from My style`} onClick={() => onRemove(row)}>
      Remove
    </button>
  );
  if (kind === "phrase") {
    return (
      <p className="phrase">
        <span className="phrase-top"><span className="label">{row.what}</span>{button}</span>
        <span className="phrase-value">{row.value}</span>
      </p>
    );
  }
  return (
    <p className="trait learned-row">
      <span>{row.what}</span>
      <span className="trait-value">{row.value}</span>
      {button}
    </p>
  );
}

export function StyleScreen({ style, reload, setUp }: Props) {
  const [messages, setMessages] = useState<StyleMessage[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.styleMessages().then(setMessages, (e: Error) => setError(e.message));
  }, []);

  async function forget(id: string) {
    setError("");
    try {
      await api.forgetStyleMessage(id);
      setMessages((now) => now?.filter((m) => m.id !== id) ?? null);
      await reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function removeRow(row: Learned) {
    setError("");
    try {
      await remove(row, reload);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const count = style?.count ?? 0;
  // set up already: some of the messages it learns from are your setup's answers (or, while they load, any at all)
  const setUpAlready = messages ? messages.some((m) => m.source === "added") : count > 0;
  const length = lengthOf(style);
  const habits = habitsOf(style);
  const sentences = sentencesOf(style);
  return (
    <>
      <Head icon={<PenIcon />} title="My style" sub={`Learned from ${count} of your messages · nothing gets trained`}
        right={<button type="button" className="main small" onClick={setUp}>{setUpAlready ? "Redo setup" : "Do setup"}</button>} />
      {error && <p className="error" role="alert">{error}</p>}
      <div className="split">
        <div className="stack">
          <section className="hero style-card" aria-label="Style card">
            <p className="caps">Style card</p>
            <p className="sub">Habits it found in your messages · remove any you don't want</p>
            {length && <p className="trait"><span>{length.k}</span><span>{length.v}</span></p>}
            {habits.map((row) => <LearnedRow key={row.key} row={row} onRemove={(r) => void removeRow(r)} kind="trait" />)}
            {!length && !habits.length && <p className="trait"><span>Nothing yet: do the setup</span></p>}
          </section>
          <section className="card roomy" aria-label="Phrasebook">
            <span className="card-words">
              <span className="caps">Phrasebook</span>
              {/* reworded 4 Nov (the owner: "make it better writing") */}
              <span className="sub">Sentences you've used in at least two messages. Some go in every message, others in only
                one kind of offer.</span>
            </span>
            {sentences.length ? sentences.map((row) => (
              <LearnedRow key={row.key} row={row} onRemove={(r) => void removeRow(r)} kind="phrase" />
            )) : <p className="sub">None yet: a sentence joins once it's in 2 of your messages.</p>}
          </section>
        </div>
        <div className="stack">
          <section className="card roomy" aria-label="Messages it learns from">
            <p className="card-head">
              <span className="caps">Messages it learns from</span>
              <span>{messages?.length ?? count}</span>
            </p>
            {messages?.length === 0 && <p className="sub">None yet: do the setup, and every message you approve joins.</p>}
            <ul className="learned">
              {messages?.map((m) => (
                <li key={m.id}>
                  <span>
                    <span className="learned-title">{[m.title || "Listing", m.price && priceText(m.price)].filter(Boolean).join(" · ")}</span>
                    <span className="learned-text">{m.text}</span>
                  </span>
                  <button type="button" className="trash" aria-label="Delete this message" onClick={() => void forget(m.id)}>
                    <TrashIcon size={14} />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </>
  );
}
