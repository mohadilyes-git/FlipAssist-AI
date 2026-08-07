"""What each AI call cost. The local model is free. API prices are US dollars
per million tokens, from Anthropic's price list on 1 Aug 2026 (Claude Haiku 5.5,
prompts up to 100K tokens). Pounds use a set rate: USD_TO_GBP in .env."""

import os
from decimal import Decimal

PRICES_USD = {"claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50"))}  # per million tokens: in, out
USD_TO_GBP = Decimal("0.80")  # the default rate; change it in .env when it moves


def cost_pence(model, tokens_in, tokens_out):
    """The cost in pence, kept to fractions of a penny (one draft costs far less than 1p)."""
    price_in, price_out = PRICES_USD.get(model, (Decimal(0), Decimal(0)))
    dollars = (price_in * tokens_in + price_out * tokens_out) / 1_000_000
    return dollars * Decimal(os.environ.get("USD_TO_GBP", USD_TO_GBP)) * 100
