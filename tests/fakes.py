"""Pretend models for tests: no AI runs, nothing is downloaded, nothing costs anything."""

import math
import re
import zlib

from flip.ai import Reply


class FakeModel:
    """A pretend model: hands back prepared answers in order and remembers what it was asked."""

    def __init__(self, name, *replies):
        self.name, self.replies, self.asked = name, list(replies), []

    def ask(self, system, user, photos, schema):
        self.asked.append({"system": system, "user": user, "photos": photos, "schema": schema})
        reply = self.replies.pop(0)
        return reply if isinstance(reply, Reply) else \
            Reply(self.name, answer=reply, tokens_in=1500, tokens_out=300, seconds=2.0)


def fake_embed(texts):
    """Words to numbers the cheap way: texts that share words land close together."""
    vectors = []
    for text in texts:
        vector = [0.0] * 64
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            vector[zlib.crc32(word.encode()) % 64] += 1.0
        length = math.sqrt(sum(x * x for x in vector)) or 1.0
        vectors.append([x / length for x in vector])
    return vectors
