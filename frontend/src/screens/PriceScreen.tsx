// AI UK price estimate: what an iPhone, a Samsung phone or a MacBook sells for in the UK, cut for its flaws (4 Oct,
// its own tab). The seller's description is read for its flaws as a draft's is (flip-reader-5 on this device), then the
// AlertFlip app's prices API prices it: the middle price of clean ones of the same model and size (sales Claude Haiku
// 5.5 sorted), cut for the kinds of flaw found, or what for-parts ones sell for when it's locked or for parts.
import { useState } from "react";
import { api, type PriceEstimate } from "../api";
import { modelName, readBy } from "../format";
import { Head, PoundIcon, Warn } from "../ui";

const pounds = (n: number | null | undefined) => (n == null ? "–" : `£${Math.round(n).toLocaleString("en-GB")}`);
const size = (gb: number) => (gb >= 1024 && gb % 1024 === 0 ? `${gb / 1024}TB` : `${gb}GB`);
const sales = (n: number) => `${n} sale${n === 1 ? "" : "s"}`;
/** "a 128GB one", but "an 8GB RAM one" and "an 18GB one": the article goes by how the number is said */
const a = (said: string) => `${/^(?:8|1[18](?!\d))/.test(said) ? "an" : "a"} ${said}`;
/** ["damage", "fault"] → "damage and fault" */
const and = (words: string[]) =>
  words.length > 1 ? `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}` : words.join("");

/** Whether the title names this size itself: "128GB", "128" or "1TB" for storage, and a MacBook's RAM with its unit
 * ("16GB", "16 gig", "16/512"), so "MacBook Pro 16" isn't 16GB of RAM. A search by words is made from the title and
 * its sales aren't sorted by size: a size the title names is most likely in its words, one only the description
 * gives isn't. */
function titleNames(title: string, gb: number, ram = false) {
  const n = `(?<![\\w.])${gb}`;
  const terabytes = !ram && gb >= 1024 && gb % 1024 === 0 ? `|(?<![\\w.])${gb / 1024}\\s?t(?:b|era)` : "";
  const named = ram ? `${n}\\s?(?:gb?|gigs?|gigabytes?)(?![a-z])|${n}\\s?(?:gb)?\\s?/` : `${n}(?![\\d.])${terabytes}`;
  return new RegExp(named, "i").test(title);
}

/** The prices API names models in lower case: "iphone 13 pro max" → "iPhone 13 Pro Max", "galaxy s23 fe" →
 * "Galaxy S23 FE", "macbook air 13 m1" → "MacBook Air 13-inch M1", "macbook pro 2019" → "MacBook Pro 2019" */
export function itemName(model: string) {
  const inches = /^macbook (air|pro) (13|14|15|16)( .+)$/.exec(model);
  const words = inches ? `macbook ${inches[1]} ${inches[2]}-inch${inches[3]}` : model;
  return words.split(" ").map((w) => (w === "iphone" ? "iPhone" : w === "macbook" ? "MacBook"
    : /^[a-z]{1,2}$|^\dg$/.test(w) ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1))).join(" ");
}

export function PriceScreen() {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [found, setFound] = useState<{ listing: string; estimate: PriceEstimate } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const listing = JSON.stringify([title, description]);
  // an estimate belongs to the listing it was checked for: change the title or the description and it goes
  const shown = found && found.listing === listing ? found.estimate : null;

  async function check() {
    const asked = listing;
    setBusy(true);
    setError("");
    try {
      setFound({ listing: asked, estimate: await api.estimatePrice({ title, description }) });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Head icon={<PoundIcon />} title="AI UK price estimate" sub="iPhones, Samsung phones and MacBooks · cut for their flaws" />
      <div className="split">
        <div className="stack">
          {error && <p className="error" role="alert">{error}</p>}
          <section className="card" aria-label="The item">
            <label className="field">
              <span>Listing title</span>
              <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300}
                placeholder="iPhone 13 128GB Blue, or MacBook Air M1 8GB 256GB" />
            </label>
            <label className="field">
              <span>The seller's description</span>
              <textarea className="input" rows={5} value={description} maxLength={5000}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Cracked back, battery 81%, works perfectly…" />
            </label>
          </section>
          <button type="button" className="main" aria-busy={busy} disabled={busy || !title.trim()}
            onClick={() => void check()}>
            {busy ? "Reading the flaws and checking…" : "Check the UK price"}
          </button>
        </div>

        <div className="stack">
          {shown && <Estimated estimate={shown} title={title} />}
          <section className="card" aria-label="How it works">
            <p className="caps">How it works</p>
            <ol className="how-it-works">
              <li><strong>AlertFlip API</strong> keeps recent UK sales of iPhones, Samsung phones and MacBooks.</li>
              <li><strong>Claude Haiku 5.5</strong> organises that sales data: each sale's model, storage, a MacBook's RAM,
                condition and flaws.</li>
              <li>The middle price of clean ones, same model and size, is <strong>sent here</strong>. The cheapest
                quarter is left out, as those often hide flaws.</li>
              {/* no amounts here: the prices API's cut table is its own and can change */}
              <li><strong>flip-reader-5</strong>, FlipAssist's own model on this device, reads the title and description
                for flaws (if its reading fails code's checks, Claude Sonnet 5.5 reads it instead, a paid
                call). <strong>flip-kinds-1</strong>, FlipAssist's own flaw-sorting model on this device, sorts each flaw
                into a kind (code's rules do when it isn't installed),
                and the price is cut by amounts measured on phone listings: any flaw takes a small cut, faults cut
                the most, and different kinds' cuts multiply. Damage is cut by how bad it is (minor, moderate or
                severe) and how pricey the model is, as measured on 1,697 damaged iPhone, Samsung and MacBook listings. A locked or for-parts one is priced at what
                for-parts ones of the same model and size sell for, or at a rough guess when too few have sold, with its
                other flaws not cut on top.</li>
            </ol>
          </section>
        </div>
      </div>
    </>
  );
}

const HARD_TO_PRICE = ["lock", "parts", "not genuine", "network lock"];

/** What to know before trusting the price: the size it priced, how few sales, a flaw that's hard to price. title: the
 * listing's, to tell a size the title names from one only the description gives (a search by words leaves that out) */
export function cautions(e: PriceEstimate, title?: string): string[] {
  const said: string[] = [];
  const mac = e.kind === "macbook";
  const sizeOf = (storage?: number | null, ram?: number | null) =>
    [mac && ram ? `${ram}GB RAM` : "", storage ? size(storage) : ""].filter(Boolean).join(" ");
  const priced = sizeOf(e.storage_gb, e.ram_gb);
  const unknown = [e.asked_storage_gb == null && e.storage_gb ? "storage" : "", mac && e.asked_ram_gb == null && e.ram_gb
    ? "RAM" : ""].filter(Boolean);
  // "couldn't find", not "none": the listing may give it in words code doesn't read ("128gig")
  const missing = `Couldn't find the ${unknown.join(" or ")} in the listing`;
  // a size the listing gives that it didn't price, even when the listing leaves out the other one (a MacBook's RAM)
  const differs = (e.asked_storage_gb != null && e.storage_gb != null && e.asked_storage_gb !== e.storage_gb)
    || (mac && e.asked_ram_gb != null && e.ram_gb != null && e.asked_ram_gb !== e.ram_gb);
  const n = e.sales ?? 0;
  // sales counts clean ones: a for-parts price isn't from them (the API doesn't say how many for-parts ones it had)
  const counted = e.mode !== "keyword" && !e.parts_price;
  let ownSize = false;
  if (e.mode === "keyword") {
    // the search is the title's words, of any size: a size only the description gives wasn't used
    const storage = title != null && e.asked_storage_gb && !titleNames(title, e.asked_storage_gb) ? e.asked_storage_gb
      : null;
    const ram = title != null && mac && e.asked_ram_gb && !titleNames(title, e.asked_ram_gb, true) ? e.asked_ram_gb : null;
    const which = mac && !(storage && ram) ? (storage ? "storage" : "RAM") : "size";
    said.push("Rough: priced from a search by words, not a model it knows"
      + (storage || ram ? `, and for any ${which}: the listing's ${sizeOf(storage, ram)} wasn't used` : ""));
  } else if (differs && priced) {
    said.push(`${unknown.length ? `${missing}, and too few` : "Too few"} sales of ${a(sizeOf(e.asked_storage_gb,
      e.asked_ram_gb))} one: this is ${a(priced)} one's price, not changed for size`);
  } else if (unknown.length && priced) said.push(`${missing}: priced as ${a(priced)} one, the size that sells most`);
  else if (!e.exact && counted) {
    said.push(`Rough: only ${sales(n)} of this size to go on`);
    ownSize = true;
  }
  // how few sales the price is from, whichever size it priced (a listing with no size gets this too)
  if (counted && !ownSize && n < 20) said.push(`Rough: only ${sales(n)} to go on`);
  if (e.parts_price) said.push("Priced at what for-parts ones sell for");
  else {
    const hard = (e.kinds ?? []).filter((k) => HARD_TO_PRICE.includes(k));
    if (hard.length) said.push(`Rough: ${hard.join(" and ")} ${hard.length > 1 ? "are" : "is"} hard to price`);
  }
  // only when a flaw cut the prices API measured on phones was used: the damage cut is measured on MacBooks too
  if (mac && (e.cuts ?? []).filter((c) => !(e.damage && c === "damage")).length && !e.parts_price) {
    said.push("Rough for a MacBook: the flaw cuts were measured on phones");
  }
  return said;
}

const TIERS: Record<string, string> = { bottom: "cheaper", middle: "mid-priced", top: "pricier" };
const NOUNS: Record<string, string> = { iphone: "iPhone", samsung: "Samsung", macbook: "MacBook" };

/** The damage cut FlipAssist measured, in words: "Damage counted as moderate: −30% for a mid-priced iPhone, from 191
 * listings like it", and where a rough one came from. */
export function damageLine(e: PriceEstimate): string {
  const d = e.damage;
  if (!d) return "";
  const where = !d.rough ? "" : d.from?.includes("the US") ? " (rough: from US sales)"
    : d.from?.includes("the iPhone") ? " (rough: from iPhones)" : " (rough: few listings, pooled with a group next to it)";
  return `Damage counted as ${d.level}: −${Math.round(-d.cut * 100)}% for ${TIERS[d.tier] ? `a ${TIERS[d.tier]}` : "this"} `
    + `${NOUNS[e.kind ?? ""] ?? "item"}, from ${d.n} listings like it${where}`;
}

/** After "counted as": a locked or for-parts one is priced as that, so its other flaws aren't cut on top of it */
function notCutOnTop(e: PriceEstimate) {
  const others = (e.kinds ?? []).filter((k) => k !== "lock" && k !== "parts");
  if (!others.length) return "";
  if (e.parts_price) return " · priced at what for-parts ones sell for, with nothing cut on top";
  const cuts = e.cuts ?? [];
  const whole = cuts.includes("lock") ? "locked" : cuts.includes("parts") ? "for parts" : "";
  return whole ? ` · priced as ${whole}: ${and(others)} ${others.length > 1 ? "aren't" : "isn't"} cut on top` : "";
}

/** Who sorted the flaws into kinds, when an AI did: " (sorted by flip-kinds-1)"; nothing when code's rules did */
export function sortedBy(by?: string | null): string {
  if (!by || by === "code") return "";
  return ` (sorted by ${by.split(" and ").map((m) => (m === "code" ? "code" : modelName(m))).join(" and ")})`;
}

function Estimated({ estimate, title }: { estimate: PriceEstimate; title: string }) {
  if (estimate.skipped) return <Warn>{estimate.skipped}</Warn>;
  if (estimate.error || estimate.price == null) return <Warn>No UK price: {estimate.error ?? "no price came back"}</Warn>;
  const off = estimate.middle ? Math.round(100 * (1 - estimate.price / estimate.middle)) : 0;
  const flaws = estimate.flaws ?? [];
  const kinds = estimate.kinds ?? [];
  const sized = [estimate.kind === "macbook" && estimate.ram_gb ? `${estimate.ram_gb}GB RAM` : "",
    estimate.storage_gb ? size(estimate.storage_gb) : ""].filter(Boolean).join(" ");
  const named = estimate.model ? itemName(estimate.model) : estimate.item ?? "";
  const item = named ? `${named}${sized ? ` ${sized}` : ""}` : "this item";
  const from = `from ${estimate.sales ?? "?"} UK sale${estimate.sales === 1 ? "" : "s"}`;
  return (
    <>
      <section className="hero" aria-label="UK price">
        <p className="caps">UK price{off > 0 ? " with its flaws" : ""}</p>
        <p className="hero-big">{pounds(estimate.price)}</p>
        {/* a for-parts price is from for-parts sales: the count is of the clean ones its "no flaws" price is from */}
        <p className="sub">{item} · {estimate.parts_price ? `for-parts price · clean price ${from}` : from}</p>
        <div className="hero-rule" />
        <div className="hero-stats three">
          <div><strong>{pounds(estimate.middle)}</strong><span>with no flaws</span></div>
          <div><strong>{off > 0 ? `−${off}%` : "none"}</strong><span>cut for its flaws</span></div>
          <div><strong>{estimate.low != null && estimate.high != null
            ? `${pounds(estimate.low)}–${pounds(estimate.high)}` : "–"}</strong>
            <span>middle half of clean sales</span><span>(cheapest quarter left out)</span></div>
        </div>
      </section>
      {cautions(estimate, title).map((c) => <Warn key={c}>{c}</Warn>)}
      <section className="card" aria-label="Flaws it found">
        <p className="caps">Flaws it found</p>
        {flaws.length ? (
          <ul className="price-flaws">{flaws.map((f) => <li key={f}>{f}</li>)}</ul>
        ) : kinds.length ? (
          // nothing quoted, but the title's own flaws still count ("Faulty iPhone 12 for parts")
          <p className="sub">{`${estimate.read_by ? "None quoted from the description" : "None given"}. Counted from the `
            + `title: ${kinds.join(", ")}`}</p>
        ) : <p className="sub">None: priced as one with no flaws.</p>}
        <p className="sub">
          {estimate.read_by ? `R${readBy(estimate.read_by).slice(1)}` : "Flaws as given"}
          {!flaws.length ? "" : kinds.length ? ` · counted as ${kinds.join(", ")}` : " · none of these lowers the price"}
          {flaws.length ? sortedBy(estimate.sorted_by) : ""}
          {notCutOnTop(estimate)}
        </p>
        {estimate.damage && <p className="sub" aria-label="Damage cut">{damageLine(estimate)}</p>}
      </section>
    </>
  );
}
