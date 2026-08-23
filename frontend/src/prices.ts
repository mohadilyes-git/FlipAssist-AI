// Offer prices, in pence: the same rules as FlipAssist's flip/money.py, so the
// cards show what the API will draft, and AlertFlip's slider range and steps.

const percentOf = (pence: number, percent: number) => Math.round((pence * percent) / 100);

/** Prices land on numbers people say: whole pounds under £60, £5 under £1,000, £10 above. */
export function priceStep(pence: number): number {
  return pence < 6000 ? 100 : pence < 100000 ? 500 : 1000;
}

/** 15% under asking, rounded down: whole pounds under £20, £5 steps from £20 (flip.money.offer_price). */
export function lowerPrice(asking: number, percent = 15): number {
  const offer = asking - percentOf(asking, percent);
  const step = offer >= 2000 ? 500 : 100;
  const rounded = offer - (offer % step);
  return rounded > 0 ? rounded : offer;
}

/** 5% over asking, rounded up to the step, and at least one step over (flip.money.more_price). */
export function morePrice(asking: number, percent = 5): number {
  const step = priceStep(asking);
  const up = (pence: number) => Math.ceil(pence / step) * step;
  return Math.max(up(asking + percentOf(asking, percent)), up(asking) + step);
}

/** Where the slider goes (AlertFlip's sliderRange): lower from £200 or a quarter under up to just
 * below asking, more from just over asking up to £200 or 15% over, a step at a time. */
export function sliderRange(asking: number, kind: "lower" | "more") {
  const step = priceStep(asking);
  const down = (pence: number) => Math.floor(pence / step) * step;
  const up = (pence: number) => Math.ceil(pence / step) * step;
  if (kind === "lower") {
    const reach = Math.max(20000, asking * 0.25);
    const min = Math.max(step, up(asking - reach));
    return { min, max: Math.max(min, down(asking * 0.99)), step };
  }
  const reach = Math.max(20000, asking * 0.15);
  const max = down(asking + reach);
  return { min: Math.min(up(asking * 1.01), max), max, step };
}

/** £185, or £185.50 */
export function money(pence: number): string {
  return pence % 100 ? `£${(pence / 100).toFixed(2)}` : `£${(pence / 100).toLocaleString("en-GB")}`;
}

/** "£35 under", "£10 over", or "asking" */
export function gapOf(price: number, asking: number): { text: string; tone: "under" | "over" | "even" } {
  const diff = price - asking;
  if (diff === 0) return { text: "asking", tone: "even" };
  return { text: `${money(Math.abs(diff))} ${diff < 0 ? "under" : "over"}`, tone: diff < 0 ? "under" : "over" };
}

/** "220", "£219.99" -> pence; null if it isn't a price */
export function toPence(written: string): number | null {
  const found = written.replace(/[£,\s]/g, "").match(/^(\d{1,6})(?:\.(\d{1,2}))?$/);
  if (!found) return null;
  return Number(found[1]) * 100 + Number((found[2] ?? "").padEnd(2, "0"));
}
