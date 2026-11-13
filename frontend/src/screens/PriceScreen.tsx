// AI UK price estimate: what an iPhone, a Samsung phone or a MacBook sells for in the UK, cut for its flaws (4 Oct,
// its own tab). The seller's description is read for its flaws as a draft's is (flip-reader-5 on this device), then the
// AlertFlip app's prices API prices it: the middle price of clean ones of the same model and size (sales Claude Haiku
// 5.5 sorted), cut for the kinds of flaw found, or what for-parts ones sell for when it's locked or for parts.
import { useEffect, useState } from "react";
import { api, type CutRow, type OwnCut, type PriceEstimate } from "../api";
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

/** A listing sent here from AI message's Check the UK price (4 Nov): a new one each time it's sent */
export type SentListing = { title: string; description: string };

export function PriceScreen({ sent = null }: { sent?: SentListing | null }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [found, setFound] = useState<{ listing: string; estimate: PriceEstimate } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const listing = JSON.stringify([title, description]);
  // an estimate belongs to the listing it was checked for: change the title or the description and it goes
  const shown = found && found.listing === listing ? found.estimate : null;

  async function check(forTitle = title, forDescription = description) {
    const asked = JSON.stringify([forTitle, forDescription]);
    setBusy(true);
    setError("");
    try {
      setFound({ listing: asked, estimate: await api.estimatePrice({ title: forTitle, description: forDescription }) });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // a listing sent from AI message (4 Nov, the owner: "it sends the title and description and it opens the window with
  // check uk price there please and start checking"): filled in here and checked straight away
  useEffect(() => {
    if (!sent) return;
    setTitle(sent.title);
    setDescription(sent.description);
    void check(sent.title, sent.description);
  }, [sent]);  // eslint-disable-line react-hooks/exhaustive-deps

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
            {/* 4 Nov, the owner: the sales sorting is a small line under the API; the reader, the sorter and how the
                price is cut are a step each; no counts or amounts (the cut tables are measured and can change) */}
            <ol className="how-it-works">
              <li><strong>AlertFlip API</strong> keeps recent UK sales of iPhones, Samsung phones and MacBooks.
                <span className="how-sub">Claude Haiku 5.5 sorts each sale: its model, storage, a MacBook's RAM, its
                  condition and its flaws.</span></li>
              <li>The middle price of clean ones of the same model and size is <strong>sent here</strong>. The cheapest
                quarter is left out, as those often hide flaws.</li>
              <li><strong>flip-reader-5</strong>, FlipAssist's own model on this device, reads the title and description
                for flaws. If its reading fails code's checks, Claude Sonnet 5.5 reads it instead (a paid call).</li>
              <li><strong>flip-kinds-1</strong>, FlipAssist's own model on this device, sorts each flaw into a kind:
                damage, a fault, a worn battery, wear and so on. Code's rules sort them when it isn't installed.</li>
              <li><strong>The price is cut</strong> for each kind, by amounts measured on UK listings of the same item:
                iPhones on iPhones, Samsungs on Samsungs, MacBooks on MacBooks.
                <ul className="how-cuts">
                  <li>Any flaw takes a small cut, counted once. Each other flaw adds its own cut on top, and faults cut
                    the most.</li>
                  <li>Damage is cut by how bad it is (minor, moderate or severe) and how pricey the model is.</li>
                  <li>A worn battery is cut by how low its health is, as it has to be replaced.</li>
                  <li>A locked or for-parts one is priced at what for-parts ones of the same model and size sell for, or
                    at a rough guess when too few have sold. Its other flaws aren't cut on top.</li>
                </ul>
              </li>
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
  // only when a flaw cut the prices API measured on phones was used: a MacBook's own cuts (4 Nov) and its damage cut
  // are measured on MacBooks (the battery cut is the owner's rule, 14 Oct, not one measured on phones)
  const own = e.own_cuts ?? {};
  if (mac && (e.cuts ?? []).filter((c) => !(e.damage && c === "damage") && !(e.battery && c === "battery")
    && !(c in own)).length && !e.parts_price && !e.own_whole) {
    said.push("Rough for a MacBook: the flaw cuts were measured on phones");
  }
  // a kind too few of a Samsung's or a MacBook's own listings had: the iPhone's cut, measured the same way
  const borrowed = Object.entries(own).filter(([, c]) => c.from === "the iPhone").map(([k]) => k);
  const noun = NOUNS[e.kind ?? ""] ?? "item";
  if (borrowed.length) {
    said.push(`Rough for a ${noun}: the ${borrowed.join(" and ")} cut${borrowed.length > 1 ? "s are" : " is"} the `
      + `iPhone's, as too few ${noun}s had ${borrowed.length > 1 ? "them" : "it"}`);
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
  // a cut borrowed from US listings says only that it's rough (9 Nov, the owner: "do not mention us sales")
  const where = !d.rough ? "" : d.from?.includes("the US") ? " (rough)"
    : d.from?.includes("the iPhone") ? " (rough: from iPhones)" : " (rough: few listings, pooled with a group next to it)";
  const judged = !d.by ? "" : d.by.startsWith("Claude Sonnet") ? ` · ${d.by} decided how bad`
    : ` · how bad: ${d.by}`;  // the hybrid (14 Oct): code and Claude Haiku 5.5, Claude Sonnet 5.5 when they disagree
  return `Damage counted as ${d.level}: −${Math.round(-d.cut * 100)}% for ${TIERS[d.tier] ? `a ${TIERS[d.tier]}` : "this"} `
    + `${NOUNS[e.kind ?? ""] ?? "item"}, from ${d.n} listings like it${where}${judged}`;
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

// ── each flaw with its own cut (14 Oct, the owner: "give real description like here we had 2 flaws") ──────────────
// The card gave only the damage's cut ("Damage counted as moderate: −30%") by a price cut 42%: now each flaw has its
// own row, in the seller's words, with what it takes off in pounds, and the rows add up to the price.

/** Each kind of flaw in plain words: its name on the card, and "one with ..." for what UK sellers ask */
const KIND_WORDS: Record<string, { name: string; one: string }> = {
  damage: { name: "Damage", one: "a damaged one" },
  fault: { name: "Fault", one: "one with a fault" },
  battery: { name: "Worn battery (under 80% or needs a service)", one: "one with a worn battery" },
  wear: { name: "Wear", one: "one with wear" },
  "network lock": { name: "Network locked", one: "a network-locked one" },
  "not genuine": { name: "Parts that aren't genuine", one: "one with parts that aren't genuine" },
  lock: { name: "Locked", one: "a locked one" },
  parts: { name: "For parts", one: "one for parts" },
};
const kindName = (k: string) => KIND_WORDS[k]?.name ?? k.charAt(0).toUpperCase() + k.slice(1);
const percent = (cut: number) => `−${Math.round(-cut * 100)}%`;

/** What a row's cut is, in words: "Damage, counted as moderate: −30%. UK sellers ask about 30% less for a mid-priced
 * iPhone with moderate damage (191 listings) · how bad: code and Claude Haiku 5.5", "Fault: −17%. UK sellers ask about
 * 17% less for one with a fault (the AlertFlip API's cut)". */
export function cutWords(row: CutRow, e: PriceEstimate): string {
  const names = and(row.kinds.map(kindName));
  const d = e.damage;
  if (row.by === "damage" && d && row.cut != null) {
    const rough = !d.rough ? "" : d.from?.includes("the US") ? ", rough"
      : d.from?.includes("the iPhone") ? ", rough: from iPhones" : ", rough: few listings, pooled with a group next to it";
    const judged = !d.by ? "" : d.by.startsWith("Claude Sonnet") ? ` · ${d.by} decided how bad` : ` · how bad: ${d.by}`;
    const what = TIERS[d.tier] ? `a ${TIERS[d.tier]} ${NOUNS[e.kind ?? ""] ?? "one"}` : `a ${NOUNS[e.kind ?? ""] ?? "one"}`;
    // a cut borrowed from US listings (every Samsung's, most MacBooks') is what sellers ask, never "UK sellers" (14 Oct
    // review), and never "US" either (9 Nov, the owner: "do not mention us sales")
    const who = d.from?.includes("the US") ? "Sellers" : "UK sellers";
    return `Damage, counted as ${d.level}: ${percent(row.cut)}. ${who} ask about ${Math.round(-row.cut * 100)}% less `
      + `for ${what} with ${d.level} damage (${d.n} listings${rough})${judged}`;
  }
  if (row.by === "battery" && row.cut != null) {
    // the owner's rule (14 Oct): a battery under 80% has to be replaced, so it's cut by how low it is
    const figure = e.battery?.figure;
    return `${figure != null ? `Battery at ${figure}%` : "Worn battery, no figure given"}: ${percent(row.cut)}. `
      + "FlipAssist's battery cut: 10% off at 75–79%, 15% at 70–74% or with no figure, 20% under 70%";
  }
  if (row.by === "api none") return `${names}: no more off, as it's counted in the cut above (the AlertFlip API's way)`;
  // a Samsung's or a MacBook's own cuts (4 Nov), measured on its own UK listings against flawless ones
  if (row.by === "own none") return `${names}: no more off, as the cut any flaw takes is counted once, in the cut above`;
  const own = row.kinds.length === 1 ? e.own_cuts?.[row.kinds[0]] : undefined;
  if (row.by === "own" && row.cut != null && own) return ownWords(row, own, e);
  if (row.by === "own lock" && row.cut != null && e.own_whole) {
    return `${ownWords(row, e.own_whole, e)}; too few for-parts sales of this model to go on`;
  }
  if (row.cut == null) {
    if (row.by !== "not on top") return `${names}: not cut for`;
    // with no for-parts sales to go on, the price is the API's rough cut for a locked or for-parts one (14 Oct review)
    const first = e.breakdown?.[0]?.kinds[0];
    const price = e.parts_price ? "the for-parts price" : first === "lock" ? "the rough cut for a locked one"
      : "the rough cut for a for-parts one";
    return `${names}: not cut on top of ${price}`;
  }
  if (row.by === "parts price") return `${names}: ${percent(row.cut)}, priced at what for-parts ones of this model sell for`;
  if (row.by === "lock") {
    return `${names}: ${percent(row.cut)}, a rough cut (too few for-parts sales of this model to go on)`;
  }
  const less = `UK sellers ask about ${Math.round(-row.cut * 100)}% less for`;
  const phones = e.kind === "macbook" ? ", measured on phones" : "";  // its cuts were measured on phone listings
  if (row.by === "api together") {
    return `${names}: ${percent(row.cut)} together. ${less} one with all of these (the AlertFlip API's cuts${phones})`;
  }
  return `${names}: ${percent(row.cut)}. ${less} ${KIND_WORDS[row.kinds[0]]?.one ?? "one like it"} (the AlertFlip `
    + `API's cut${phones})`;
}

/** "a Samsung with a fault", "a network-locked MacBook", "an iPhone with parts that aren't genuine" */
function ownOne(kind: string, noun: string): string {
  const a = /^[aeiou]/i.test(noun) ? "an" : "a";
  return ({ wear: `${a} ${noun} with wear`, fault: `${a} ${noun} with a fault`, "network lock": `a network-locked ${noun}`,
    "not genuine": `${a} ${noun} with parts that aren't genuine`, lock: `a locked ${noun}`,
    parts: `${a} ${noun} for parts` } as Record<string, string>)[kind] ?? `${a} ${noun} like it`;
}

/** A Samsung's or a MacBook's own cut in words (4 Nov): "Fault: −33%. UK sellers ask about 33% less for a Samsung with
 * a fault than a flawless one (168 Samsung listings)"; a kind beside a worse one is only its part on top ("Network
 * locked: −4% more ..."), and a kind too few of them had is the iPhone's, rough. */
function ownWords(row: CutRow, own: OwnCut, e: PriceEstimate): string {
  const kind = row.kinds[0];
  const noun = NOUNS[e.kind ?? ""] ?? "item";
  const iphones = own.from === "the iPhone";
  const onTop = row.cut != null && Math.abs(row.cut - own.cut) > 0.0005;  // its part on top of the any-flaw cut
  const from = iphones ? `${own.n} iPhone listings: too few ${noun}s had it, so it's rough`
    : `${own.n} ${noun} listings${own.rough ? ", rough: few listings" : ""}`;
  return `${and(row.kinds.map(kindName))}: ${percent(row.cut ?? 0)}${onTop ? " more" : ""}. UK sellers ask about `
    + `${Math.round(-own.cut * 100)}% less for ${ownOne(kind, iphones ? "iPhone" : noun)} than a flawless one (${from})`
    + (onTop ? "; the part any flaw takes is counted once, above" : "");
}

/** What each row takes off in pounds, taken in turn from the clean middle price to the price: [72, 29] for −30% then
 * −17% off £240 (£139); null for a row not cut. Each step is rounded as the screen shows prices, and the last step
 * lands on the price itself, so the pounds always add up to the price. */
export function poundsOff(rows: CutRow[], middle: number, price: number): (number | null)[] {
  const last = rows.map((r) => r.cut != null).lastIndexOf(true);
  let before = middle;
  return rows.map((row, n) => {
    if (row.cut == null) return null;
    const after = n === last ? price : before * (1 + row.cut);
    const off = Math.round(before) - Math.round(after);
    before = after;
    return off;
  });
}

/** The flaws card when the estimate says what each flaw cut: a row for each, then how they add up */
function FlawCuts({ estimate }: { estimate: PriceEstimate }) {
  const rows = estimate.breakdown ?? [];
  const notCut = estimate.not_cut ?? [];
  const middle = estimate.middle ?? estimate.price ?? 0;
  const offs = poundsOff(rows, middle, estimate.price ?? 0);
  const taken = offs.filter((o): o is number => !!o);  // a cut that rounds to £0 isn't summed
  const sorter = estimate.sorted_by && estimate.sorted_by !== "code"
    ? ` · sorted by ${estimate.sorted_by.split(" and ").map((m) => (m === "code" ? "code" : modelName(m))).join(" and ")}`
    : "";
  return (
    <>
      {!(estimate.flaws ?? []).length && <p className="sub">{estimate.read_by ? "None quoted from the description."
        : "None given."}</p>}
      <ol className="flaw-cuts">
        {rows.map((row, n) => (
          <li key={`${row.kinds.join("+")}-${n}`}>
            <div className="flaw-cut-top">
              <span className="flaw-words">{row.title ? `In the title: ${row.words.join(" · ")}` : row.words.join(" · ")}</span>
              <strong className="flaw-off">{offs[n] ? `−£${offs[n]!.toLocaleString("en-GB")}` : "–"}</strong>
            </div>
            <p className="sub">{cutWords(row, estimate)}</p>
          </li>
        ))}
      </ol>
      {taken.length > 0 && (
        <p className="flaw-sum" aria-label="How the cuts add up">
          {`${pounds(middle)} with no flaws${taken.map((o) => ` − £${o.toLocaleString("en-GB")}`).join("")} = `}
          <strong>{pounds(estimate.price)}</strong>
        </p>
      )}
      {notCut.length > 0 && <p className="sub">Not cut for: {notCut.join(" · ")}</p>}
      <p className="sub">{estimate.read_by ? `R${readBy(estimate.read_by).slice(1)}` : "Flaws as given"}{sorter}</p>
    </>
  );
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
        {/* 9 Nov: a title that didn't say which model was asked with the description's year, chip or size */}
        {estimate.asked_title && (
          <p className="sub">Priced as “{estimate.asked_title}”, with the model details from the description</p>
        )}
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
        {(estimate.breakdown ?? []).length ? <FlawCuts estimate={estimate} /> : <>
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
        </>}
      </section>
    </>
  );
}
