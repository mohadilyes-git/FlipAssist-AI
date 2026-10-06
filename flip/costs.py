"""What each AI call cost. The local model is free. API prices are US dollars
per million tokens, from Anthropic's price list on 1 Aug 2026 (Claude Haiku 5.5,
prompts up to 100K tokens). Pounds use a set rate: USD_TO_GBP in .env."""

import os
from decimal import Decimal

PRICES_USD = {"claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),  # per million tokens: in, out
              "claude-sonnet-5-5": (Decimal("2.00"), Decimal("10.00"))}  # the reason's fixer (flip.wording), 3 Oct
CACHE_READ, CACHE_WRITE = Decimal("0.1"), Decimal("1.25")  # of the input price: read from, or put in, the 5-minute cache
USD_TO_GBP = Decimal("0.80")  # the default rate; change it in .env when it moves


def cost_pence(model, tokens_in, tokens_out, tokens_cached=0, tokens_cache_write=0):
    """The cost in pence, kept to fractions of a penny (one draft costs far less than 1p).
    A paid model with no price here (a Claude model added later) is never
    counted free: it's priced as the dearest here until its own price is added."""
    dearest = (max(p[0] for p in PRICES_USD.values()), max(p[1] for p in PRICES_USD.values()))
    price_in, price_out = PRICES_USD.get(model) or (dearest if str(model).startswith("claude") else (Decimal(0), Decimal(0)))
    dollars = (price_in * (tokens_in + CACHE_READ * tokens_cached + CACHE_WRITE * tokens_cache_write)
               + price_out * tokens_out) / 1_000_000
    return dollars * Decimal(os.environ.get("USD_TO_GBP", USD_TO_GBP)) * 100
