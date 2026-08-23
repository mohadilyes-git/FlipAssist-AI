// List on eBay, drawn like AlertFlip's eBay screens: photos in slots, your notes,
// and a draft to check. Code fills what the catalogue knows (model, storage,
// specs, the title), the AI the colour from the photos, the condition and the
// description, and the checks hold it to your notes. Nothing is listed from here.
import { useEffect, useMemo, useState } from "react";
import { api, type ListingDraft } from "../api";
import { CONDITIONS, cost, seconds, writerName } from "../format";
import { CameraIcon, MainButton, Note, ScreenHead, SecondButton, TagIcon } from "../ui";
import { Attempts } from "./MessageScreen";

const MAX_PHOTOS = 8;
const TITLE_LIMIT = 80; // eBay's limit

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
  const [saved, setSaved] = useState("");

  function add(files: FileList | null) {
    if (!files) return;
    setPhotos((now) => [...now, ...Array.from(files)].slice(0, MAX_PHOTOS));
  }

  async function submit() {
    setBusy(true);
    setError("");
    setSaved("");
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
    try {
      await navigator.clipboard?.writeText(all);
    } catch {
      // the browser can block copying: everything is still on screen
    }
    try {
      const done = await api.approve(draft.draft_id, text);
      setSaved(done.edited ? "Copied and saved: you changed the description first." : "Copied and saved: listed as drafted.");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <form className="screen" onSubmit={(e) => {
      e.preventDefault();
      void submit();
    }}>
      <ScreenHead icon={<TagIcon />} title="List on eBay" sub="Your notes and photos · a checked eBay draft" />

      <Photos photos={photos} onAdd={add} onRemove={(i) => setPhotos((now) => now.filter((_, n) => n !== i))} />

      <section className="card fields">
        <label>
          <span>The seller's title</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={300} placeholder="iphone 13 128gb unlocked boxed" />
        </label>
        <label>
          <span>The seller's description</span>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} maxLength={5000} />
        </label>
        <label>
          <span>Your notes from looking at it</span>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} maxLength={2000}
            placeholder="battery 87%, light scratch on the back, screen perfect, boxed, no charger" />
        </label>
      </section>

      {draft && (
        <section className="card review" aria-live="polite">
          <p className="review-status">
            <span className={`badge ${draft.status === "ready" ? "ready" : "needs"}`}>{draft.status === "ready" ? "Ready" : "Needs you"}</span>
            <span className="faint">{draft.photo_count} {draft.photo_count === 1 ? "photo" : "photos"} read</span>
          </p>
          {[...draft.reasons, ...draft.warnings].map((r) => <Note tone="warn" key={r}>{r}</Note>)}
          <label>
            <span>eBay title <span className="faint">{ebayTitle.length}/{TITLE_LIMIT}</span></span>
            <input value={ebayTitle} onChange={(e) => setEbayTitle(e.target.value)} maxLength={TITLE_LIMIT} />
          </label>
          <div className="rows">
            <Row name="Condition" value={draft.condition_id ? CONDITIONS[draft.condition_id] ?? draft.condition_id : "not drafted"} />
            {draft.condition_note && <Row name="Condition note" value={draft.condition_note} />}
            <Row name="Colour" value={draft.colour === "unsure" ? "Unsure from the photos: check it" : draft.colour ?? "Not known"} />
          </div>
          <label>
            <span>Description</span>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={6} />
          </label>
          <FilledByCode facts={draft.filled_by_code} />
          <div className="tips">
            <p className="tip">
              {writerName(draft.attempts.at(-1)?.model ?? null)} · {seconds(draft.attempts)} · {cost(draft.cost_pence)}
            </p>
            <Attempts attempts={draft.attempts} />
          </div>
        </section>
      )}

      {error && <p className="error" role="alert">{error}</p>}
      {saved && <p className="saved" role="status">{saved}</p>}

      <div className="footer">
        {draft ? (
          <>
            <SecondButton label="Redraft" disabled={busy} onClick={() => void submit()} />
            <MainButton label="Copy & approve" disabled={busy || !text.trim()} onClick={() => void approve()} />
          </>
        ) : (
          <MainButton type="submit" label={busy ? "Drafting…" : "Draft listing"} disabled={busy} />
        )}
      </div>
    </form>
  );
}

function Row({ name, value }: { name: string; value: string }) {
  return (
    <div className="row">
      <span className="row-name">{name}</span>
      <span className="row-value">{value}</span>
    </div>
  );
}

function Photos({ photos, onAdd, onRemove }: { photos: File[]; onAdd: (files: FileList | null) => void; onRemove: (i: number) => void }) {
  const previews = useMemo(() => photos.map((p) => URL.createObjectURL(p)), [photos]);
  useEffect(() => () => previews.forEach((url) => URL.revokeObjectURL(url)), [previews]);
  const empty = Math.max(0, MAX_PHOTOS - photos.length);
  return (
    <section className="photos" aria-label="Photos"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        onAdd(e.dataTransfer.files);
      }}>
      {photos.map((p, i) => (
        <div className="slot filled" key={`${p.name}-${i}`}>
          <img src={previews[i]} alt={p.name} />
          <button type="button" className="slot-remove" aria-label={`Remove ${p.name}`} onClick={() => onRemove(i)}>×</button>
          {i === 0 && <span className="slot-cover">Cover</span>}
        </div>
      ))}
      {empty > 0 && (
        <label className="slot add">
          <CameraIcon />
          <span>Add photo</span>
          <input type="file" accept="image/*,.heic,.heif" multiple onChange={(e) => onAdd(e.target.files)} />
        </label>
      )}
      {Array.from({ length: Math.max(0, empty - 1) }, (_, i) => <div className="slot ghost" key={`ghost-${i}`} aria-hidden="true" />)}
    </section>
  );
}

function FilledByCode({ facts }: { facts: Record<string, unknown> }) {
  const shown = Object.entries(facts).filter(([key, value]) => value && !["specs", "options", "model_id"].includes(key));
  const specs = (facts.specs ?? {}) as Record<string, unknown>;
  return (
    <details className="filled">
      <summary>Filled by code, no AI</summary>
      <div className="rows">
        {[...shown, ...Object.entries(specs)].map(([key, value]) => <Row key={key} name={key} value={String(value)} />)}
      </div>
    </details>
  );
}
