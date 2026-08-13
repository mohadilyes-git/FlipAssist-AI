"""Money in plain code: profit and the offer prices. Every amount is whole pence
(£12.50 is 1250), because computers store 0.1 + 0.2 as 0.30000000000000004 and
whole numbers never have that problem."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

TOO_BIG = Decimal("1000000")  # a million pounds or more is a typo, not a price


def to_pence(pounds):
    """'12.50', '£1,200' or 12.5 -> 1250, 120000, 1250. Anything that isn't a
    sensible amount ("abc", a 40-digit number) is a ValueError, not a crash."""
    text = str(pounds).replace("£", "").replace(",", "").strip()
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"not an amount of money: {pounds!r}") from None
    if not amount.is_finite() or abs(amount) >= TOO_BIG:
        raise ValueError(f"not a sensible amount of money: {pounds!r}")
    return int((amount * 100).quantize(Decimal("1"), ROUND_HALF_UP))


def pounds(pence):
    """1250 -> '£12.50'"""
    sign = "-" if pence < 0 else ""
    pence = abs(pence)
    return f"{sign}£{pence // 100:,}.{pence % 100:02d}"


def percent_of(pence, percent):
    """percent of an amount, rounded to the nearest penny"""
    return int((Decimal(pence) * Decimal(str(percent)) / 100).quantize(Decimal("1"), ROUND_HALF_UP))


def profit(sale, paid, postage=0, fee_percent=0, fee_fixed=0, other_costs=0):
    """What's left after a sale. All amounts in pence.

    sale: everything the buyer pays (item + any postage they pay)
    postage: what you pay to send it
    fee_percent, fee_fixed: your eBay selling fees. They depend on your account
    and eBay changes them, so they're settings, not baked in. On 1 Aug 2026
    eBay UK charged private sellers no final value fee (the buyer pays a
    protection fee); business sellers pay a percentage plus a per-order fee
    """
    fees = percent_of(sale, fee_percent) + fee_fixed if sale else 0
    left = sale - paid - postage - fees - other_costs
    margin = (Decimal(left * 100) / sale).quantize(Decimal("0.1"), ROUND_HALF_UP) if sale else Decimal("0.0")
    return {"fees": fees, "profit": left, "margin_percent": float(margin)}


def offer_price(asking, discount_percent=15):
    """Your opening offer: the asking price minus your discount, rounded down
    to a tidy number (whole pounds under £20, £5 steps from £20)."""
    offer = asking - percent_of(asking, discount_percent)
    step = 500 if offer >= 2000 else 100
    rounded = offer - offer % step
    return rounded if rounded > 0 else offer


OFFER_KINDS = ("lower", "asking", "more")


def price_step(price):
    """Prices land on numbers people say: whole pounds under £60, £5 steps
    under £1,000, £10 steps from £1,000."""
    return 100 if price < 6000 else 500 if price < 100000 else 1000


def more_price(asking, percent=5):
    """Offering more than asking, to beat other buyers: the asking price plus
    percent, rounded UP to a tidy number, and always at least one step over
    the asking price. The same rule as AlertFlip's "pay more"."""
    step = price_step(asking)
    up = lambda pence: -(-pence // step) * step  # round up to the step
    return max(up(asking + percent_of(asking, percent)), up(asking) + step)


def offer_for(kind, asking, discount_percent=15, more_percent=5):
    """The price for each kind of offer: "lower" than asking, the "asking"
    price itself, or "more" than asking."""
    if kind == "lower":
        return offer_price(asking, discount_percent)
    if kind == "more":
        return more_price(asking, more_percent)
    if kind == "asking":
        return asking
    raise ValueError(f"not a kind of offer: {kind!r} (lower, asking or more)")
