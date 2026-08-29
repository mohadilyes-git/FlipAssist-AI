// List on eBay: photos and your notes on the left, the checked eBay draft on
// the right. Code fills what the catalogue knows (model, storage, specs, the
// title), the AI the colour from the photos, the condition and the
// description, and the checks hold it to your notes. Nothing is listed from
// here: you copy it into eBay.
import { Fragment, useEffect, useMemo, useState } from "react";
import { api, type ListingDraft } from "../api";
import { CONDITIONS, cost, seconds, writerName } from "../format";
import { CameraIcon, CheckIcon, ChevronIcon, CrossIcon, Head, Steps, TagIcon, Warn, WarningIcon } from "../ui";

const MAX_PHOTOS = 8;
const MAX_PHOTO_BYTES = 15 * 1024 * 1024; // the API's limit for one photo: refused here, before it's sent
const TITLE_LIMIT = 80; // eBay's limit
const LONG_TITLE = 74; // past this the counter turns orange
const PHOTO_TYPE = /^image\/(jpeg|png|heic|heif|webp)$/;
const PHOTO_NAME = /\.(jpe?g|png|heic|heif|webp)$/i; // a HEIC from the Mac can come with no type
const FACTS = ["brand", "model", "storage", "network", "colour"];

export function ListingScreen() {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [notes, setNotes] = useState("");
  const [photos, setPhotos] = useState<File[]>([]);
  const [draft, setDraft] = useState<ListingDraft | null>(null);
  const [ebayTitle, setEbayTitle] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState<boolean | null>(null);

  function add(files: FileList | null) {
    const given = Array.from(files ?? []);
    const photo = (f: File) => PHOTO_TYPE.test(f.type) || PHOTO_NAME.test(f.name);
    const fit = given.filter((f) => photo(f) && f.size <= MAX_PHOTO_BYTES);
    const left = [
      ...given.filter((f) => !photo(f)).map((f) => `${f.name} isn't a JPEG, PNG, HEIC or WebP photo`),
      ...given.filter((f) => photo(f) && f.size > MAX_PHOTO_BYTES).map((f) => `${f.name} is over 15 MB`),
    ];
    setError(left.length ? `Left out: ${left.join("; ")}.` : "");
    setPhotos((now) => [...now, ...fit].slice(0, MAX_PHOTOS));
  }

  async function submit() {
    setBusy(true);
    setError("");
    setCopied(null);
    const form = new FormData();
    form.append("title", title);
    form.append("description", description);
    form.append("notes", notes);
    photos.forEach((photo) => form.append("photos", photo));
    try {
      const found = await api.draftListing(form);
      setDraft(found);
      setEbayTitle(found.ebay_title ?? "");
      setText(found.description ?? "");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (!draft || !text.trim()) return;
    const condition = draft.condition_id ? CONDITIONS[draft.condition_id] ?? draft.condition_id : "";
    const all = [ebayTitle, condition && `Condition: ${condition}`, draft.condition_note, text].filter(Boolean).join("\n\n");
    let ok = true;
    try {
      await navigator.clipboard.writeText(all);
    } catch {
      ok = false; // the browser said no: it's all still on screen
    }
    try {
      await api.approve(draft.draft_id, text);
      setCopied(ok);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <>
      <Head icon={<TagIcon />} title="List on eBay" sub="Your notes and photos · a checked eBay draft" />
      <div className="split">
        <div className="stack">
          {error && <p className="error" role="alert">{error}</p>}
          <Photos photos={photos} onAdd={add} onRemove={(i) => setPhotos((now) => now.filter((_, n) => n !== i))} />
          <section className="card" aria-label="The item">
            <label className="field">
              <span>The seller's title</span>
              <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300}
                placeholder="iphone 13 128gb unlocked boxed" />
            </label>
            <label className="field">
              <span>The seller's description</span>
              <textarea className="input" rows={3} value={description} maxLength={5000}
                onChange={(e) => setDescription(e.target.value)} />
            </label>
            <label className="field">
              <span>Your notes from looking at it</span>
              <textarea className="input" rows={3} value={notes} maxLength={2000} onChange={(e) => setNotes(e.target.value)}
                placeholder="battery 87%, light scratch on the back, screen perfect, boxed, no charger" />
            </label>
          </section>
          {!draft && (
            <button type="button" className="main" aria-busy={busy} disabled={busy || !title.trim()}
              onClick={() => void submit()}>
              {busy ? "Drafting…" : "Draft listing"}
            </button>
          )}
        </div>

        <div className="stack">
          {draft ? (
            <>
              <Drafted draft={draft} ebayTitle={ebayTitle} setEbayTitle={setEbayTitle} text={text} setText={setText} />
              <div className="buttons">
                <button type="button" className="second" aria-busy={busy} disabled={busy} onClick={() => void submit()}>
                  {busy ? "Drafting…" : "Redraft"}
                </button>
                <button type="button" className="main" disabled={busy || !text.trim()} onClick={() => void approve()}>
                  Copy &amp; approve
                </button>
              </div>
              {copied !== null && (
                <p className={copied ? "done-line" : "done-line warn"} role="status">
                  {copied ? <CheckIcon size={14} stroke={2.6} /> : <WarningIcon size={14} stroke={2.2} />}
                  {copied ? "Copied and saved: title, condition and description."
                    : "Couldn't copy: select the text and copy it by hand."}
                </p>
              )}
            </>
          ) : (
            <div className="empty">
              <span className="tile"><TagIcon size={20} /></span>
              <strong>Your eBay draft shows here</strong>
              <p className="sub">Add photos and notes, then Draft listing. Code fills the specs, AI writes the rest.</p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

type DraftedProps = {
  draft: ListingDraft;
  ebayTitle: string;
  setEbayTitle: (title: string) => void;
  text: string;
  setText: (text: string) => void;
};

function Drafted({ draft, ebayTitle, setEbayTitle, text, setText }: DraftedProps) {
  const [code, setCode] = useState(false);
  const [why, setWhy] = useState(false);
  const ready = draft.status === "ready";
  const colour = !draft.colour ? "Unsure from the photos: check it"
    : draft.colour_from === "photos" ? `${draft.colour} (from the photos)` : draft.colour;
  return (
    <section className="card" aria-label="Your eBay draft" aria-live="polite">
      <p className="status-row">
        <span className={ready ? "badge ready" : "badge"}>{ready ? "Ready" : "Needs you"}</span>
        <span className="sub">{draft.photo_count} {draft.photo_count === 1 ? "photo" : "photos"} read</span>
      </p>
      {[...draft.reasons, ...draft.warnings].map((r) => <Warn key={r}>{r}</Warn>)}
      <label className="field">
        <span className="field-head">
          <span>eBay title</span>
          <span className={ebayTitle.length > LONG_TITLE ? "count long" : "count"}>{ebayTitle.length}/{TITLE_LIMIT}</span>
        </span>
        <input className="input" value={ebayTitle} maxLength={TITLE_LIMIT} onChange={(e) => setEbayTitle(e.target.value)} />
      </label>
      <div className="rows">
        <Row name="Condition" value={draft.condition_id ? CONDITIONS[draft.condition_id] ?? draft.condition_id : "Not drafted"} />
        {draft.condition_note && <Row name="Condition note" value={draft.condition_note} />}
        <Row name="Colour" value={colour} warn={!draft.colour} />
      </div>
      <label className="field">
        <span>Description</span>
        <textarea className="input" rows={5} value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      <div className="tips">
        <button type="button" className="code-toggle" aria-expanded={code} onClick={() => setCode(!code)}>
          <span className="caps">Filled by code, no AI</span>
          <ChevronIcon size={12} stroke={2.6} />
        </button>
        {code && (
          <dl className="facts">
            {facts(draft.filled_by_code).map(([name, value]) => (
              <Fragment key={name}><dt>{name}</dt><dd>{value}</dd></Fragment>
            ))}
          </dl>
        )}
        <p className="tip-row sub">
          <span>{writerName(draft.attempts.at(-1)?.model ?? null)} · {seconds(draft.attempts)} · {cost(draft.cost_pence)}</span>
          {draft.attempts.length > 0 && (
            <button type="button" className="link" aria-expanded={why} onClick={() => setWhy(!why)}>Why</button>
          )}
        </p>
        {why && <Steps attempts={draft.attempts} />}
      </div>
    </section>
  );
}

function Row({ name, value, warn }: { name: string; value: string; warn?: boolean }) {
  return (
    <div className="row">
      <span className="row-name">{name}</span>
      <span className={warn ? "row-value warn" : "row-value"}>{value}</span>
    </div>
  );
}

/** What the catalogue filled in, by name: brand, model, storage, network, colour, then options and specs. */
function facts(found: Record<string, unknown>): [string, string][] {
  const named = (key: string) => key[0].toUpperCase() + key.slice(1);
  const shown = (value: unknown) => (value === null || value === undefined || value === "" ? "–" : String(value));
  const group = (key: string) => Object.entries((found[key] ?? {}) as Record<string, unknown>);
  return [
    ...FACTS.filter((key) => key in found).map((key): [string, string] => [named(key), shown(found[key])]),
    ...group("options").map(([key, value]): [string, string] => [named(key), shown(value)]),
    ...group("specs").map(([key, value]): [string, string] => [key, shown(value)]),
  ];
}

function Photos({ photos, onAdd, onRemove }: { photos: File[]; onAdd: (files: FileList | null) => void; onRemove: (i: number) => void }) {
  const previews = useMemo(() => photos.map((p) => URL.createObjectURL(p)), [photos]);
  useEffect(() => () => previews.forEach((url) => URL.revokeObjectURL(url)), [previews]);
  return (
    <section className="photos" aria-label="Photos" onDragOver={(e) => e.preventDefault()} onDrop={(e) => {
      e.preventDefault();
      onAdd(e.dataTransfer.files);
    }}>
      {Array.from({ length: MAX_PHOTOS }, (_, i) => {
        const photo = photos[i];
        if (photo) {
          return (
            <div className="slot filled" key={`${photo.name}-${i}`}>
              <img src={previews[i]} alt={photo.name} />
              <button type="button" className="slot-remove" aria-label={`Remove ${photo.name}`} onClick={() => onRemove(i)}>
                <CrossIcon size={11} stroke={3} />
              </button>
              {i === 0 && <span className="slot-cover">Cover</span>}
            </div>
          );
        }
        if (i === photos.length) {
          return (
            <label className="slot add" key="add">
              <CameraIcon size={20} />
              <span>Add photo</span>
              <input className="sr-only" type="file" multiple
                accept="image/jpeg,image/png,image/heic,image/heif,image/webp,.heic,.heif" onChange={(e) => {
                  onAdd(e.target.files);
                  e.target.value = ""; // the same photo can be added again after removing it
                }} />
            </label>
          );
        }
        return <div className="slot" key={`empty-${i}`} aria-hidden="true" />;
      })}
    </section>
  );
}
