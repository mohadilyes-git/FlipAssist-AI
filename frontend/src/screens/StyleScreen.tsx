// Your style: what FlipAssist learned from your messages (the style card and
// the phrasebook, worked out by plain code: nothing gets trained), each thing
// yours to remove, and the messages it learns from, each one yours to delete.
import { useEffect, useState } from "react";
import { api, type Learned, type Style, type StyleMessage } from "../api";
import { money, toPence } from "../prices";
import { Head, PenIcon, TrashIcon } from "../ui";

type Props = { style: Style | null; reload: () => Promise<void>; redo: () => void; addMore: () => void };

/** "220" -> "£220"; a price that isn't one is shown as it was written */
export const priceText = (price: string) => {
  const pence = toPence(price);
  return pence === null ? price : money(pence);
};

// your sentences go in the phrasebook; everything else is a habit on the style card
const SENTENCES = new Set(["Usual opener", "Offer sentence", "Offer under asking", "Offer at asking",
  "Offer over asking", "Closing", "Asks every time"]);
export const habitsOf = (style: Style | null) => (style?.learned ?? []).filter((row) => !SENTENCES.has(row.what));
export const sentencesOf = (style: Style | null) => (style?.learned ?? []).filter((row) => SENTENCES.has(row.what));
// how long your messages are isn't a thing it puts in, so it's shown, not removed
export const lengthOf = (style: Style | null) => style?.traits.find((t) => t.k === "Length");

/** Remove one thing your style learned, or put it back, then show your style as it is now. */
export async function keepOrRemove(row: Learned, reload: () => Promise<void>) {
  await api.changeLearned(row.key, !row.used);
  await reload();
}

/** One thing your style learned, with the button that removes it or puts it back. A
 * removed one is never written: the AI is told not to, and the checks refuse it. */
export function LearnedRow({ row, onUse, kind }: { row: Learned; onUse: (row: Learned) => void; kind: "trait" | "phrase" }) {
  const button = (
    <button type="button" className="remove" aria-label={row.used ? `Remove “${row.value}” from your style`
      : `Use “${row.value}” again`} onClick={() => onUse(row)}>
      {row.used ? "Remove" : "Use again"}
    </button>
  );
  if (kind === "phrase") {
    return (
      <p className={`phrase${row.used ? "" : " removed"}`}>
        <span className="phrase-top"><span className="label">{row.what}</span>{button}</span>
        <span className="phrase-value">{row.value}</span>
      </p>
    );
  }
  return (
    <p className={`trait learned-row${row.used ? "" : " removed"}`}>
      <span>{row.what}</span>
      <span className="trait-value">{row.value}</span>
      {button}
    </p>
  );
}

export function StyleScreen({ style, reload, redo, addMore }: Props) {
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

  async function toggle(row: Learned) {
    setError("");
    try {
      await keepOrRemove(row, reload);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const count = style?.count ?? 0;
  const length = lengthOf(style);
  const habits = habitsOf(style);
  const sentences = sentencesOf(style);
  return (
    <>
      <Head icon={<PenIcon />} title="Your style" sub={`Learned from ${count} of your messages · nothing gets trained`}
        right={(
          <span className="head-buttons">
            <button type="button" className="second small" onClick={redo}>Redo setup</button>
            <button type="button" className="main small" onClick={addMore}>Add more</button>
          </span>
        )} />
      {error && <p className="error" role="alert">{error}</p>}
      <div className="split">
        <div className="stack">
          <section className="hero style-card" aria-label="Style card">
            <p className="caps">Style card</p>
            <p className="sub">Habits in 40% or more of your messages · remove any you don't want</p>
            {length && <p className="trait"><span>{length.k}</span><span>{length.v}</span></p>}
            {habits.map((row) => <LearnedRow key={row.key} row={row} onUse={(r) => void toggle(r)} kind="trait" />)}
            {!length && !habits.length && <p className="trait"><span>Nothing yet: add a few of your messages</span></p>}
          </section>
          <section className="card roomy" aria-label="Phrasebook">
            <span className="card-words">
              <span className="caps">Phrasebook</span>
              <span className="sub">Sentences you've written in 2 or more messages</span>
            </span>
            {sentences.length ? sentences.map((row) => (
              <LearnedRow key={row.key} row={row} onUse={(r) => void toggle(r)} kind="phrase" />
            )) : <p className="sub">None yet: a sentence joins once it's in 2 of your messages.</p>}
          </section>
        </div>
        <div className="stack">
          <section className="card roomy" aria-label="Messages it learns from">
            <p className="card-head">
              <span className="caps">Messages it learns from</span>
              <span>{messages?.length ?? count}</span>
            </p>
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
