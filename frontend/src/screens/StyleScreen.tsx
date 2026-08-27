// Your style: what FlipAssist learned from your messages (the style card and
// the phrasebook, worked out by plain code: nothing gets trained) and the
// messages it learns from, each one yours to delete.
import { useEffect, useState } from "react";
import { api, type Style, type StyleMessage } from "../api";
import { money, toPence } from "../prices";
import { Head, PenIcon, TrashIcon } from "../ui";

type Props = { style: Style | null; reload: () => Promise<void>; redo: () => void; addMore: () => void };

/** "220" -> "£220"; a price that isn't one is shown as it was written */
export const priceText = (price: string) => {
  const pence = toPence(price);
  return pence === null ? price : money(pence);
};

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

  const count = style?.count ?? 0;
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
            <p className="sub">Habits in 40% or more of your messages</p>
            {style?.traits.length ? style.traits.map((t) => (
              <p className="trait" key={t.k}><span>{t.k}</span><span>{t.v}</span></p>
            )) : <p className="trait"><span>Nothing yet: add a few of your messages</span></p>}
          </section>
          <section className="card roomy" aria-label="Phrasebook">
            <span className="card-words">
              <span className="caps">Phrasebook</span>
              <span className="sub">Sentences you've written in 2 or more messages</span>
            </span>
            {style?.phrases.length ? style.phrases.map((p) => (
              <p className="phrase" key={p.k}>
                <span className="label">{p.k}</span>
                <span className="phrase-value">{p.v}</span>
              </p>
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
