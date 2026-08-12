"""Deterministic local embeddings suitable for repeatable tests and offline demos."""

import hashlib
import math
import re


class LocalHashEmbedding:
    """Map tokens into a fixed vector without a model download or network call."""

    def __init__(self, dimensions: int = 256) -> None:
        if dimensions < 32:
            raise ValueError("Embedding dimensions must be at least 32")
        self.dimensions = dimensions

    def embed(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[a-z0-9]+", text.casefold())
        for token in tokens:
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4]) % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            return tuple(vector)
        return tuple(value / magnitude for value in vector)
