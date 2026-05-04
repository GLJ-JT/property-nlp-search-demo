#!/usr/bin/env python3
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "near",
    "of",
    "on",
    "or",
    "the",
    "to",
    "under",
    "with",
    "within",
}


class SimpleTfidfVectorIndex:
    """Small local vector layer for soft semantic matching without paid APIs."""

    def __init__(self, properties: list[dict[str, Any]]):
        self.property_ids = [str(prop.get("id", "")) for prop in properties]
        documents = [self._property_document(prop) for prop in properties]
        tokenized = [self._tokenize(document) for document in documents]
        self.idf = self._build_idf(tokenized)
        self.vectors = [self._vectorize(tokens) for tokens in tokenized]

    def score(self, query: str) -> dict[str, float]:
        query_vector = self._vectorize(self._tokenize(query))
        if not query_vector:
            return {prop_id: 0.0 for prop_id in self.property_ids}
        return {
            prop_id: self._cosine(query_vector, vector)
            for prop_id, vector in zip(self.property_ids, self.vectors, strict=False)
        }

    def _property_document(self, prop: dict[str, Any]) -> str:
        parts = [
            str(prop.get("name", "")),
            str(prop.get("location", "")),
            str(prop.get("area", "")),
            str(prop.get("postcode", "")),
            str(prop.get("station", "")),
            str(prop.get("station_line", "")),
            str(prop.get("building_type", "")),
            str(prop.get("room_type", "")),
            str(prop.get("floor_label", "")),
            str(prop.get("furnished", "")),
            str(prop.get("description", "")),
            " ".join(str(item) for item in prop.get("keywords", [])),
            " ".join(str(item) for item in prop.get("accessibility", [])),
            "bills included" if prop.get("bills_included") else "bills not included",
            "pet friendly pets allowed" if prop.get("pets_allowed") else "no pets",
            "new build modern development" if prop.get("new_build") else "older period established",
        ]
        for station in prop.get("nearby_stations", []):
            parts.append(str(station.get("name", "")))
            parts.append(str(station.get("line", "")))
        for landmark in prop.get("nearby_landmarks", []):
            parts.append(str(landmark.get("name", "")))
            parts.append(str(landmark.get("category", "")))
        return " ".join(parts)

    def _tokenize(self, text: str) -> list[str]:
        raw_tokens = re.findall(r"[a-z][a-z0-9]+", text.lower())
        tokens = []
        for token in raw_tokens:
            if token in STOPWORDS:
                continue
            tokens.append(self._stem(token))
        return tokens

    def _stem(self, token: str) -> str:
        for suffix in ("friendly", "included", "including", "bedrooms", "bedroom", "minutes"):
            if token.endswith(suffix) and len(token) > len(suffix) + 3:
                return token[: -len(suffix)]
        for suffix in ("ies", "ing", "ed", "es", "s"):
            if token.endswith(suffix) and len(token) > len(suffix) + 3:
                if suffix == "ies":
                    return token[:-3] + "y"
                return token[: -len(suffix)]
        return token

    def _build_idf(self, tokenized: list[list[str]]) -> dict[str, float]:
        document_count = max(1, len(tokenized))
        df = Counter()
        for tokens in tokenized:
            df.update(set(tokens))
        return {
            token: math.log((1 + document_count) / (1 + frequency)) + 1
            for token, frequency in df.items()
        }

    def _vectorize(self, tokens: list[str]) -> dict[str, float]:
        counts = Counter(token for token in tokens if token in self.idf)
        if not counts:
            return {}
        max_count = max(counts.values())
        vector = {
            token: (count / max_count) * self.idf[token]
            for token, count in counts.items()
        }
        norm = math.sqrt(sum(value * value for value in vector.values()))
        if norm == 0:
            return {}
        return {token: value / norm for token, value in vector.items()}

    def _cosine(self, left: dict[str, float], right: dict[str, float]) -> float:
        if not left or not right:
            return 0.0
        if len(left) > len(right):
            left, right = right, left
        return sum(value * right.get(token, 0.0) for token, value in left.items())
