#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

try:
    from vector_search import SimpleTfidfVectorIndex
except ImportError:
    from .vector_search import SimpleTfidfVectorIndex


BEDROOM_WORDS = {
    "studio": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
}

BUILDING_SYNONYMS = {
    "apartment": {"apartment", "flat", "apts", "condo"},
    "flat": {"flat", "apartment", "apts"},
    "house": {"house", "detached", "semi", "semi-detached", "terrace", "terraced", "townhouse"},
    "studio": {"studio"},
    "maisonette": {"maisonette"},
    "penthouse": {"penthouse"},
    "duplex": {"duplex"},
    "loft": {"loft", "warehouse"},
}

ROOM_SYNONYMS = {
    "studio": {"studio"},
    "1 bed": {"1 bed", "one bed", "one-bedroom", "1-bedroom", "single"},
    "2 bed": {"2 bed", "two bed", "two-bedroom", "2-bedroom"},
    "3 bed": {"3 bed", "three bed", "three-bedroom", "3-bedroom"},
    "room in house share": {"house share", "room", "room in house share", "flatshare", "flat share"},
}

NEW_BUILD_WORDS = {"new build", "brand new", "newly built", "new development", "modern development"}
OLD_BUILD_WORDS = {"old build", "period", "conversion", "character", "victorian", "edwardian", "georgian"}

BASE_DIR = Path(__file__).resolve().parent
JSON_DIR = BASE_DIR / "json"
SYNONYMS_PATH = JSON_DIR / "synonyms.json"
LANDMARKS_PATH = JSON_DIR / "landmarks.json"
STATIONS_PATH = JSON_DIR / "stations.json"


def _load_optional_json(path: Path, fallback: Any) -> Any:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return fallback


SYNONYMS = _load_optional_json(SYNONYMS_PATH, {})
LANDMARKS = _load_optional_json(LANDMARKS_PATH, [])
STATIONS = _load_optional_json(STATIONS_PATH, [])
LANDMARK_ALIASES = {
    item["name"]: set([item["name"].lower(), *[alias.lower() for alias in item.get("aliases", [])]])
    for item in LANDMARKS
}

QUERY_ALIASES = {
    "russel sqaure": "russell square",
    "russel square": "russell square",
    "russell sqaure": "russell square",
    "walthemstow": "walthamstow",
    "famy": "family",
    "newish": "new build",
    "walk up": "stairs only",
    "pw": "per week",
    "p/w": "per week",
}

AMBIGUOUS_LANDMARKS = {
    "UCL": [
        {"label": "UCL Bloomsbury", "phrase": "UCL Bloomsbury", "replace": "UCL"},
        {"label": "UCL East", "phrase": "UCL East", "replace": "UCL"},
    ],
}

AMBIGUOUS_NEAR_OPTIONS = [
    {"label": "10 min walk", "phrase": "10 min walk"},
    {"label": "20 min commute", "phrase": "20 min commute"},
    {"label": "Within 1 mile", "phrase": "within 1 mile"},
]

COMMUTE_DESTINATIONS = {
    "Canary Wharf": ["canary wharf"],
    "Liverpool Street": ["liverpool street"],
    "Bank": ["bank"],
    "Oxford Circus": ["oxford circus"],
    "King's Cross": ["king's cross", "kings cross"],
}


@dataclass
class ParsedQuery:
    raw: str
    rent_max: int | None = None
    rent_min: int | None = None
    rent_target: int | None = None
    rooms: str | None = None
    bedrooms: int | None = None
    building_type: str | None = None
    location: str | None = None
    landmark: str | None = None
    landmark_scope: str | None = None
    landmark_walk_max: int | None = None
    station: str | None = None
    station_walk_max: int | None = None
    station_distance_max: float | None = None
    council_tax_band: str | None = None
    size_min_sqft: int | None = None
    size_max_sqft: int | None = None
    floor_min: int | None = None
    floor_max: int | None = None
    new_build: bool | None = None
    keywords: list[str] | None = None
    exclude_keywords: list[str] | None = None
    hard_filters: list[str] | None = None
    soft_preferences: list[str] | None = None


class PropertySearchEngine:
    def __init__(self, properties: list[dict[str, Any]]):
        self.properties = properties
        self.vector_index = SimpleTfidfVectorIndex(properties)
        self.known_locations = self._build_location_values()
        self.known_stations = self._build_station_values()
        self.known_landmarks = self._build_landmark_values()
        self.synonym_lookup = self._build_synonym_lookup()

    def _build_known_values(self, field: str) -> list[str]:
        values = sorted({str(p.get(field, "")).strip() for p in self.properties if p.get(field)})
        return values

    def _build_location_values(self) -> list[str]:
        values = set()
        for prop in self.properties:
            location = str(prop.get("location", "")).strip()
            postcode = str(prop.get("postcode", "")).strip()
            if location:
                values.add(location)
                values.add(location.split(",", 1)[0].strip())
            if postcode:
                values.add(postcode)
                values.add(postcode.split()[0].strip())
        return sorted(value for value in values if value)

    def _build_landmark_values(self) -> list[str]:
        values = set(LANDMARK_ALIASES.keys())
        for aliases in LANDMARK_ALIASES.values():
            values.update(alias.title() for alias in aliases)
        for prop in self.properties:
            for item in prop.get("nearby_landmarks", []):
                name = str(item.get("name", "")).strip()
                if name:
                    values.add(name)
        return sorted(values)

    def _build_station_values(self) -> list[str]:
        values = set(self._build_known_values("station"))
        for station in STATIONS:
            name = str(station.get("name", "")).strip()
            if name:
                values.add(name)
        return sorted(values)

    def _build_synonym_lookup(self) -> dict[str, str]:
        lookup = {}
        for category in SYNONYMS.values():
            if not isinstance(category, dict):
                continue
            for canonical, aliases in category.items():
                lookup[canonical.lower()] = canonical.lower()
                for alias in aliases:
                    lookup[str(alias).lower()] = canonical.lower()
        return lookup

    def parse_query(self, query: str) -> ParsedQuery:
        text = self._normalize(query)
        location = self._find_best_phrase(text, self.known_locations)
        landmark = self._parse_landmark(text)
        landmark_scope = self._parse_landmark_scope(text, landmark)
        station = self._parse_station_name(text) or self._parse_explicit_station(text)
        feature_text = self._mask_known_entity_spans(text)
        tokens = self._tokenize(feature_text)

        rent_max, rent_min, rent_target = self._parse_rent(text)
        bedrooms, rooms = self._parse_rooms(feature_text)
        building_type = self._parse_category(feature_text, BUILDING_SYNONYMS)
        council_tax_band = self._parse_council_band(text)
        size_min, size_max = self._parse_size(text)
        floor_min, floor_max = self._parse_floor(text)
        new_build = self._parse_build_age(feature_text)
        station_walk_max = self._parse_station_walk(text)
        station_distance_max = self._parse_station_distance(text)
        landmark_walk_max = self._parse_landmark_walk(text, landmark) if landmark else None

        keywords = self._extract_keywords(tokens)
        exclude_keywords = self._extract_excludes(text)
        keywords = [
            keyword
            for keyword in keywords
            if keyword not in exclude_keywords and not any(keyword in excluded for excluded in exclude_keywords)
        ]
        hard_filters = self._build_hard_filters(
            rent_max=rent_max,
            rent_min=rent_min,
            rooms=rooms,
            bedrooms=bedrooms,
            location=location,
            landmark=landmark,
            station=station,
            station_walk_max=station_walk_max,
            landmark_walk_max=landmark_walk_max,
            new_build=new_build,
        )
        soft_preferences = self._build_soft_preferences(
            building_type=building_type,
            keywords=keywords,
            floor_min=floor_min,
            floor_max=floor_max,
            new_build=new_build,
        )

        return ParsedQuery(
            raw=query,
            rent_max=rent_max,
            rent_min=rent_min,
            rent_target=rent_target,
            rooms=rooms,
            bedrooms=bedrooms,
            building_type=building_type,
            location=location,
            landmark=landmark,
            landmark_scope=landmark_scope,
            landmark_walk_max=landmark_walk_max,
            station=station,
            station_walk_max=station_walk_max,
            station_distance_max=station_distance_max,
            council_tax_band=council_tax_band,
            size_min_sqft=size_min,
            size_max_sqft=size_max,
            floor_min=floor_min,
            floor_max=floor_max,
            new_build=new_build,
            keywords=keywords or None,
            exclude_keywords=exclude_keywords or None,
            hard_filters=hard_filters or None,
            soft_preferences=soft_preferences or None,
        )

    def search(self, query: str, top_n: int = 5, min_score: float | None = None) -> dict[str, Any]:
        parsed = self.parse_query(query)
        query_repair = self._query_repair(query)
        clarifications = self._build_clarifications(query, parsed)
        vector_scores = self.vector_index.score(query)
        ranked = []
        for prop in self.properties:
            vector_similarity = vector_scores.get(str(prop.get("id", "")), 0.0)
            score, reasons, explanation = self._score_property(prop, parsed, vector_similarity)
            ranked.append(
                {
                    "property": prop,
                    "score": round(score, 2),
                    "reasons": reasons,
                    "explanation": explanation,
                    "hard_filter_pass": explanation["hard_filter_pass"],
                    "excluded_by_query": explanation.get("excluded_by_query", False),
                }
            )
        ranked.sort(key=lambda item: item["score"], reverse=True)
        ranked_before_exclusions = ranked
        ranked = [
            item
            for item in ranked
            if not item.get("excluded_by_query") and item.get("hard_filter_pass", True)
        ]
        filtered = ranked
        if min_score is not None:
            filtered = [item for item in ranked if item["score"] >= min_score]
        return {
            "parsed_query": asdict(parsed),
            "query_repair": query_repair,
            "clarifications": clarifications,
            "results": filtered[:top_n],
            "total_matches": len(filtered),
            "filtered_out": len(ranked_before_exclusions) - len(filtered),
            "excluded_out": len(ranked_before_exclusions) - len(ranked),
        }

    def _query_repair(self, query: str) -> dict[str, Any]:
        normalized = self._normalize(query)
        raw_normalized = query.lower().replace("£", " gbp ")
        raw_normalized = raw_normalized.replace("-", " ")
        raw_normalized = re.sub(r"[^\w\s\.]", " ", raw_normalized)
        raw_normalized = re.sub(r"\s+", " ", raw_normalized).strip()
        repairs = []
        for wrong, right in QUERY_ALIASES.items():
            if re.search(rf"\b{re.escape(wrong)}\b", raw_normalized):
                repairs.append({"from": wrong, "to": right})
        return {
            "original": query,
            "normalized": normalized,
            "repairs": repairs,
            "changed": bool(repairs) or normalized != raw_normalized,
        }

    def _build_clarifications(self, query: str, parsed: ParsedQuery) -> list[dict[str, Any]]:
        text = self._normalize(query)
        prompts = []
        if parsed.landmark in AMBIGUOUS_LANDMARKS and not parsed.landmark_scope:
            prompts.append(
                {
                    "id": "landmark_scope",
                    "type": "choice",
                    "message": f"Which {parsed.landmark} do you mean?",
                    "options": AMBIGUOUS_LANDMARKS[parsed.landmark],
                }
            )
        if (
            (parsed.location or parsed.landmark)
            and parsed.station_walk_max is None
            and parsed.station_distance_max is None
            and parsed.landmark_walk_max is None
            and re.search(r"\bnear\b", text)
        ):
            label = parsed.location or parsed.landmark
            if parsed.landmark == "UCL" and parsed.landmark_scope:
                label = f"UCL {parsed.landmark_scope}"
            prompts.append(
                {
                    "id": "near_meaning",
                    "type": "choice",
                    "message": f"What should near {label} mean?",
                    "options": AMBIGUOUS_NEAR_OPTIONS,
                }
            )
        if parsed.location and parsed.station and parsed.location.lower() != parsed.station.lower():
            prompts.append(
                {
                    "id": "place_station_conflict",
                    "type": "choice",
                    "message": f"Should results prioritise {parsed.location} or {parsed.station} station?",
                    "options": [
                        {"label": parsed.location, "phrase": f"near {parsed.location}"},
                        {"label": f"{parsed.station} station", "phrase": f"near {parsed.station} station"},
                    ],
                }
            )
        commute_match = re.search(r"\b(\d{1,2})\s*(?:min|mins|minutes)\s*(?:to|commute to)\s+([a-z'\s]+)", text)
        if commute_match:
            destination_text = commute_match.group(2).strip()
            destination = self._known_commute_destination(destination_text)
            prompts.append(
                {
                    "id": "commute_mode",
                    "type": "choice",
                    "message": f"How should we treat the commute to {destination or destination_text.title()}?",
                    "options": [
                        {"label": "Public transport", "phrase": f"{commute_match.group(1)} min public transport to {destination or destination_text}"},
                        {"label": "Walking", "phrase": f"{commute_match.group(1)} min walk to {destination or destination_text}"},
                        {"label": "Cycling", "phrase": f"{commute_match.group(1)} min cycle to {destination or destination_text}"},
                    ],
                }
            )
        return prompts

    def _known_commute_destination(self, text: str) -> str | None:
        for canonical, aliases in COMMUTE_DESTINATIONS.items():
            if any(alias in text for alias in aliases):
                return canonical
        return None

    def _mask_known_entity_spans(self, text: str) -> str:
        masked = text
        entity_values = set(self.known_locations) | set(self.known_stations) | set(self.known_landmarks)
        for aliases in LANDMARK_ALIASES.values():
            entity_values.update(aliases)
        entity_values.update(COMMUTE_DESTINATIONS.keys())
        for aliases in COMMUTE_DESTINATIONS.values():
            entity_values.update(aliases)

        normalized_entities = sorted(
            {self._normalize_label(value) for value in entity_values if self._normalize_label(value)},
            key=len,
            reverse=True,
        )
        for entity in normalized_entities:
            if " " not in entity and len(entity) < 5:
                continue
            mask = " ".join(["entity"] * len(entity.split()))
            masked = re.sub(rf"\b{re.escape(entity)}\b", mask, masked)
        return masked

    def _score_property(
        self,
        prop: dict[str, Any],
        parsed: ParsedQuery,
        vector_similarity: float = 0.0,
    ) -> tuple[float, list[str], dict[str, Any]]:
        score = 0.0
        reasons: list[str] = []
        hard_checks: list[dict[str, Any]] = []
        soft_scores: list[dict[str, Any]] = []
        excluded_by_query = False

        def add_score(points: float, reason: str, category: str = "soft", passed: bool | None = None) -> None:
            nonlocal score
            score += points
            reasons.append(reason)
            entry = {"label": reason, "points": round(points, 2)}
            if category == "hard":
                entry["passed"] = bool(passed)
                hard_checks.append(entry)
            else:
                soft_scores.append(entry)

        if parsed.location:
            loc_score = self._phrase_score(parsed.location, str(prop.get("location", "")) + " " + str(prop.get("area", "")))
            loc_score = max(loc_score, self._phrase_score(parsed.location, str(prop.get("station", ""))))
            if loc_score >= 0.7:
                add_score(32 * loc_score, f"location match {loc_score:.2f}", "hard", True)
            else:
                add_score(-35, "location mismatch", "hard", False)

        if parsed.station:
            station_score = self._phrase_score(parsed.station, str(prop.get("station", "")))
            for station in prop.get("nearby_stations", []):
                station_score = max(station_score, self._phrase_score(parsed.station, str(station.get("name", ""))))
            if station_score > 0.45:
                add_score(18 * station_score, f"station match {station_score:.2f}", "hard", True)
            else:
                add_score(-20, f"station mismatch for {parsed.station}", "hard", False)

        if parsed.landmark:
            landmark_score, landmark_walk = self._score_landmark(prop, parsed.landmark)
            if landmark_score > 0:
                if landmark_walk is not None:
                    add_score(landmark_score, f"near {parsed.landmark} in {landmark_walk:g} min walk", "hard", True)
                else:
                    add_score(landmark_score, f"near {parsed.landmark}", "hard", True)
            else:
                add_score(-35, f"not near {parsed.landmark}", "hard", False)

            if parsed.landmark_walk_max is not None and landmark_walk is not None:
                if landmark_walk <= parsed.landmark_walk_max:
                    add_score(10, f"within {parsed.landmark_walk_max} min of {parsed.landmark}", "hard", True)
                else:
                    add_score(-min(24, (landmark_walk - parsed.landmark_walk_max) * 3), f"over {parsed.landmark_walk_max} min from {parsed.landmark}", "hard", False)

        if parsed.station_walk_max is not None:
            walk, station_name = self._nearest_station_walk(prop)
            if walk is not None:
                if walk <= parsed.station_walk_max:
                    suffix = f" to {station_name}" if station_name else " of station"
                    add_score(16 + max(0, (parsed.station_walk_max - walk)), f"within {walk:g} min walk{suffix}", "hard", True)
                else:
                    add_score(-min(18, walk - parsed.station_walk_max), f"over {parsed.station_walk_max} min walk to station", "hard", False)

        if parsed.station_distance_max is not None:
            dist = self._num_or_none(prop.get("station_distance_miles"))
            if dist is not None:
                if dist <= parsed.station_distance_max:
                    add_score(10 + max(0, (parsed.station_distance_max - dist) * 6), f"station distance {dist:.2f} mi", "hard", True)
                else:
                    add_score(-min(12, (dist - parsed.station_distance_max) * 8), f"station distance over {parsed.station_distance_max:.2f} mi", "hard", False)

        if parsed.rent_max is not None:
            rent = self._num_or_none(prop.get("monthly_rent_gbp"))
            if rent is not None:
                if rent <= parsed.rent_max:
                    add_score(24 + max(0, (parsed.rent_max - rent) / max(parsed.rent_max, 1) * 10), f"rent within budget at {rent}", "hard", True)
                else:
                    add_score(-min(35, (rent - parsed.rent_max) / max(parsed.rent_max, 1) * 60), f"rent above budget at {rent}", "hard", False)
        if parsed.rent_min is not None:
            rent = self._num_or_none(prop.get("monthly_rent_gbp"))
            if rent is not None:
                if rent >= parsed.rent_min:
                    add_score(18 + min(8, (rent - parsed.rent_min) / max(parsed.rent_min, 1) * 8), f"rent above minimum at {rent}", "hard", True)
                else:
                    add_score(-min(35, (parsed.rent_min - rent) / max(parsed.rent_min, 1) * 70), f"rent below minimum at {rent}", "hard", False)
        if parsed.rent_max is None and parsed.rent_min is None and parsed.rent_target is not None:
            rent = self._num_or_none(prop.get("monthly_rent_gbp"))
            if rent is not None:
                delta = abs(rent - parsed.rent_target)
                add_score(max(0, 18 - delta / max(parsed.rent_target, 1) * 18), f"rent near target at {rent}")

        if parsed.rooms:
            room_score = self._category_score(parsed.rooms, str(prop.get("room_type", "")))
            if room_score > 0:
                add_score(18 * room_score, f"room type {room_score:.2f}", "hard", room_score >= 0.9)
            else:
                add_score(-24, f"room type mismatch for {parsed.rooms}", "hard", False)

        if parsed.bedrooms is not None:
            bedrooms = self._num_or_none(prop.get("bedrooms"))
            if bedrooms is not None:
                diff = abs(bedrooms - parsed.bedrooms)
                points = max(-12, 16 - diff * 8)
                add_score(points, f"{bedrooms:g} bed", "hard", diff == 0)

        if parsed.building_type:
            bscore = self._category_score(parsed.building_type, str(prop.get("building_type", "")))
            if parsed.building_type == "house" and "share" in str(prop.get("room_type", "")).lower():
                bscore = 0.0
            if bscore > 0:
                add_score(18 * bscore, f"building type {bscore:.2f}", "hard", bscore >= 0.9)
            else:
                add_score(-24, f"building type mismatch for {parsed.building_type}", "hard", False)

        if parsed.council_tax_band:
            band = str(prop.get("council_tax_band", "")).upper()
            if band:
                if band == parsed.council_tax_band:
                    add_score(10, f"council tax band {band}", "hard", True)
                else:
                    add_score(-2 * abs(ord(band) - ord(parsed.council_tax_band)), f"council tax band {band}", "hard", False)

        if parsed.size_min_sqft is not None or parsed.size_max_sqft is not None:
            size = self._num_or_none(prop.get("size_sqft"))
            if size is not None:
                if parsed.size_min_sqft is not None and size >= parsed.size_min_sqft:
                    add_score(10, f"size above {parsed.size_min_sqft} sqft", "hard", True)
                if parsed.size_max_sqft is not None and size <= parsed.size_max_sqft:
                    add_score(10, f"size below {parsed.size_max_sqft} sqft", "hard", True)
                if parsed.size_min_sqft is not None and size < parsed.size_min_sqft:
                    add_score(-min(16, (parsed.size_min_sqft - size) / 40), f"below requested size {parsed.size_min_sqft} sqft", "hard", False)
                if parsed.size_max_sqft is not None and size > parsed.size_max_sqft:
                    add_score(-min(16, (size - parsed.size_max_sqft) / 40), f"above requested size {parsed.size_max_sqft} sqft", "hard", False)

        if parsed.floor_min is not None or parsed.floor_max is not None:
            floor = self._num_or_none(prop.get("floor_level"))
            if floor is not None:
                if parsed.floor_min is not None and floor >= parsed.floor_min:
                    add_score(9, f"floor {floor:g} meets minimum {parsed.floor_min}")
                if parsed.floor_max is not None and floor <= parsed.floor_max:
                    add_score(9, f"floor {floor:g} within maximum {parsed.floor_max}")
                if parsed.floor_min is not None and floor < parsed.floor_min:
                    add_score(-min(20, 3 * (parsed.floor_min - floor)), f"below requested floor {parsed.floor_min}")
                if parsed.floor_max is not None and floor > parsed.floor_max:
                    add_score(-min(20, 3 * (floor - parsed.floor_max)), f"above requested floor {parsed.floor_max}")

        if parsed.new_build is not None:
            prop_new = bool(prop.get("new_build"))
            if prop_new == parsed.new_build:
                add_score(12, "build age match", "hard", True)
            else:
                add_score(-24, "build age mismatch", "hard", False)

        if parsed.keywords:
            text_blob = self._property_text(prop)
            missing_keywords = []
            for keyword in parsed.keywords:
                feature_score = self._feature_similarity(keyword, text_blob)
                if feature_score >= 0.42:
                    add_score(9 * feature_score, f"feature match {keyword} {feature_score:.2f}")
                else:
                    missing_keywords.append(keyword)
            if missing_keywords:
                add_score(-len(missing_keywords) * 5, f"missing {', '.join(missing_keywords)}")

        if parsed.exclude_keywords:
            text_blob = self._property_text(prop)
            for keyword in parsed.exclude_keywords:
                if self._property_has_excluded_concept(prop, keyword, text_blob):
                    excluded_by_query = True
                    add_score(-30, f"excluded term {keyword}", "hard", False)
                else:
                    add_score(7, f"negative preference satisfied: no {keyword}")

        self._apply_default_quality_penalties(prop, parsed, add_score)

        name_blob = f"{prop.get('name', '')} {prop.get('location', '')} {prop.get('description', '')} {' '.join(prop.get('keywords', []))}"
        if parsed.raw.strip():
            loose = self._text_similarity(parsed.raw, name_blob)
            add_score(loose * 12, f"semantic text fit {loose:.2f}")
            if vector_similarity > 0:
                add_score(vector_similarity * 15, f"vector soft fit {vector_similarity:.2f}")

        hard_filter_pass = all(item.get("passed", True) for item in hard_checks)
        if not hard_filter_pass:
            score -= 15
        explanation = {
            "hard_filter_pass": hard_filter_pass,
            "hard_checks": hard_checks,
            "soft_scores": soft_scores,
            "excluded_by_query": excluded_by_query,
        }

        return score, reasons, explanation

    def _normalize(self, text: str) -> str:
        text = text.lower()
        text = text.replace("£", " gbp ")
        text = text.replace("-", " ")
        text = re.sub(r"[^\w\s\.]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        for wrong, right in QUERY_ALIASES.items():
            text = re.sub(rf"\b{re.escape(wrong)}\b", right, text)
        return text

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", text.lower())

    def _build_hard_filters(self, **kwargs: Any) -> list[str]:
        labels = []
        if kwargs.get("rent_max") is not None:
            labels.append("max rent")
        if kwargs.get("rent_min") is not None:
            labels.append("min rent")
        if kwargs.get("rooms") or kwargs.get("bedrooms") is not None:
            labels.append("room type")
        if kwargs.get("location"):
            labels.append("location")
        if kwargs.get("landmark"):
            labels.append("landmark proximity")
        if kwargs.get("station"):
            labels.append("station")
        if kwargs.get("station_walk_max") is not None:
            labels.append("station walk time")
        if kwargs.get("landmark_walk_max") is not None:
            labels.append("landmark walk time")
        if kwargs.get("new_build") is not None:
            labels.append("build age")
        return labels

    def _build_soft_preferences(self, **kwargs: Any) -> list[str]:
        labels = []
        if kwargs.get("building_type"):
            labels.append("building type")
        if kwargs.get("keywords"):
            labels.extend(kwargs["keywords"])
        if kwargs.get("floor_min") is not None or kwargs.get("floor_max") is not None:
            labels.append("floor level")
        if kwargs.get("new_build") is not None:
            labels.append("build age")
        return labels

    def _property_text(self, prop: dict[str, Any]) -> str:
        parts = [
            str(prop.get("name", "")),
            str(prop.get("location", "")),
            str(prop.get("station", "")),
            str(prop.get("building_type", "")),
            str(prop.get("room_type", "")),
            str(prop.get("description", "")),
            " ".join(prop.get("keywords", [])),
        ]
        for landmark in prop.get("nearby_landmarks", []):
            parts.append(str(landmark.get("name", "")))
        return " ".join(parts).lower()

    def _property_has_excluded_concept(self, prop: dict[str, Any], keyword: str, text_blob: str) -> bool:
        key = keyword.lower()
        floor = self._num_or_none(prop.get("floor_level"))
        accessibility = " ".join(prop.get("accessibility", [])).lower()
        room_type = str(prop.get("room_type", "")).lower()
        keywords = " ".join(prop.get("keywords", [])).lower()

        if key == "basement":
            return (floor is not None and floor < 0) or "basement" in text_blob
        if key in {"lift", "no lift"}:
            return (
                ("lift" in accessibility or "lift" in keywords or "lift" in text_blob)
                and "no lift" not in accessibility
                and "no lift" not in keywords
                and "no lift" not in text_blob
            )
        if key == "gym":
            return "gym" in text_blob and "no gym" not in text_blob
        if key in {"stairs", "stairs only", "walk up"}:
            return "stairs only" in accessibility or "walk up" in keywords or "no lift" in keywords
        if key in {"house", "share", "house share"}:
            return "share" in room_type or "house share" in text_blob or "flatmates" in text_blob
        if key in {"bathroom", "shared bathroom", "shared"}:
            return "shared bathroom" in text_blob
        if key in {"pets", "pet", "pet friendly"}:
            return bool(prop.get("pets_allowed")) or "pet friendly" in text_blob or "pets allowed" in text_blob
        if key in {"bills", "bills included"}:
            if self._text_has_negated_feature("bills included", text_blob):
                return False
            return bool(prop.get("bills_included")) or "bills included" in text_blob
        if key in {"parking"}:
            return "parking" in text_blob and "no parking" not in text_blob
        if key in {"garden"}:
            return "garden" in text_blob and "no garden" not in text_blob
        if key in {"students", "student"}:
            return "student" in text_blob and "no students" not in text_blob
        if key in {"noisy", "nightlife"}:
            return "noisy" in text_blob or "nightlife" in text_blob
        if key in {"road", "main", "busy", "main road", "busy road"}:
            if self._text_has_negated_feature("main road", text_blob):
                return False
            return "main road" in text_blob or "busy road" in text_blob
        return key in text_blob

    def _text_has_negated_feature(self, feature: str, text_blob: str) -> bool:
        if feature in {"bills", "bills included"}:
            return any(
                phrase in text_blob
                for phrase in (
                    "no bills included",
                    "bills not included",
                    "bills are not included",
                    "without bills included",
                )
            )
        if feature in {"pets", "pet", "pet friendly"}:
            return "no pets" in text_blob or "not pet friendly" in text_blob
        if feature == "parking":
            return "no parking" in text_blob or "without parking" in text_blob
        if feature == "garden":
            return "no garden" in text_blob or "without garden" in text_blob
        if feature == "gym":
            return "no gym" in text_blob or "without gym" in text_blob
        if feature in {"lift", "step free"}:
            return "no lift" in text_blob or "stairs only" in text_blob or "walk up" in text_blob
        if feature in {"main road", "busy road"}:
            return any(
                phrase in text_blob
                for phrase in (
                    "not main road",
                    "not on main road",
                    "not on the main road",
                    "away from main road",
                    "away from the main road",
                    "off main road",
                    "off the main road",
                    "set away from main road",
                    "set away from the main road",
                )
            )
        return False

    def _apply_default_quality_penalties(self, prop: dict[str, Any], parsed: ParsedQuery, add_score: Any) -> None:
        text_blob = self._property_text(prop)
        wanted_terms = set(parsed.keywords or []) | set(parsed.exclude_keywords or [])
        floor = self._num_or_none(prop.get("floor_level"))
        wants_basement = "basement" in parsed.raw.lower() and "not basement" not in parsed.raw.lower() and "no basement" not in parsed.raw.lower()
        wants_walk_up = any(term in wanted_terms for term in {"stairs", "stairs only", "walk up", "no lift"})

        if not wants_basement and ((floor is not None and floor < 0) or "basement" in text_blob):
            add_score(-34, "default quality penalty: basement")
        if not wants_walk_up and ("stairs only" in text_blob or "walk up" in text_blob):
            add_score(-12, "default quality penalty: stairs only")

    def _expanded_terms(self, term: str) -> set[str]:
        norm = term.lower()
        terms = {norm}
        canonical = self.synonym_lookup.get(norm)
        if canonical:
            terms.add(canonical)
            for category in SYNONYMS.values():
                if not isinstance(category, dict):
                    continue
                for key, aliases in category.items():
                    if key.lower() == canonical:
                        terms.update(str(alias).lower() for alias in aliases)
        return terms

    def _feature_similarity(self, feature: str, text_blob: str) -> float:
        if self._text_has_negated_feature(feature.lower(), text_blob):
            return 0.0
        terms = self._expanded_terms(feature)
        if any(term in text_blob for term in terms):
            return 1.0
        text_tokens = set(self._tokenize(text_blob))
        best = 0.0
        for term in terms:
            term_tokens = set(self._tokenize(term))
            if not term_tokens:
                continue
            overlap = len(term_tokens & text_tokens) / len(term_tokens)
            fuzzy = max((SequenceMatcher(None, token, term).ratio() for token in text_tokens), default=0.0)
            best = max(best, overlap, fuzzy)
        return best

    def _haversine_miles(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        radius_miles = 3958.8
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lng2 - lng1)
        a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return radius_miles * c

    def _walk_minutes_from_miles(self, distance_miles: float) -> int:
        return max(1, int(round(distance_miles / 3.0 * 60)))

    def _parse_rent(self, text: str) -> tuple[int | None, int | None, int | None]:
        compact = text.lower().replace(",", "")
        per_week = "per week" in compact or re.search(r"\bweek(?:ly)?\b", compact)
        rent_context = re.search(
            r"\b(?:rent|pcm|per month|monthly|per week|weekly|budget|gbp|under|max(?:imum)?|up to|less than|below|around|about|approx(?:\.|imately)?|circa|over|above|at least|more than|min(?:imum)?|plus|or more)\b",
            compact,
        )
        money_context = re.search(r"\b(?:gbp|pounds?)\s*\d|\d+(?:\.\d+)?k\b", compact)
        if not rent_context and not money_context:
            return None, None, None

        max_match = re.search(r"(?:under|max(?:imum)?|up to|less than|below)\s+(?:gbp?\s*)?(\d+(?:\.\d+)?)(k?)", compact)
        min_match = re.search(
            r"(?:over|above|at least|more than|min(?:imum)?)\s+(?:gbp?\s*)?(\d+(?:\.\d+)?)(k?)|(?:gbp?\s*)?(\d+(?:\.\d+)?)(k?)\s*(?:pcm|per month|monthly|rent)?\s*(?:and\s*)?(?:over|above|plus|or more)\b",
            compact,
        )
        if max_match and min_match:
            min_value = min_match.group(1) or min_match.group(3)
            min_suffix = min_match.group(2) or min_match.group(4) or ""
            return (
                self._money_to_int(max_match.group(1), max_match.group(2), per_week=per_week),
                self._money_to_int(min_value, min_suffix, per_week=per_week),
                None,
            )

        between = re.search(r"(?:between|from)\s+gbp?\s*(\d+(?:\.\d+)?)(k?)\s*(?:and|to|-)\s*gbp?\s*(\d+(?:\.\d+)?)(k?)", compact)
        if between:
            low = self._money_to_int(between.group(1), between.group(2), per_week=per_week)
            high = self._money_to_int(between.group(3), between.group(4), per_week=per_week)
            return high, low, (low + high) // 2

        under = re.search(r"(?:under|max(?:imum)?|up to|less than|below)\s+(?:gbp?\s*)?(\d+(?:\.\d+)?)(k?)", compact)
        if under:
            return self._money_to_int(under.group(1), under.group(2), per_week=per_week), None, None

        over = re.search(
            r"(?:over|above|at least|more than|min(?:imum)?)\s+(?:gbp?\s*)?(\d+(?:\.\d+)?)(k?)|(?:gbp?\s*)?(\d+(?:\.\d+)?)(k?)\s*(?:pcm|per month|monthly|rent)?\s*(?:and\s*)?(?:over|above|plus|or more)\b",
            compact,
        )
        if over:
            value = over.group(1) or over.group(3)
            suffix = over.group(2) or over.group(4) or ""
            return None, self._money_to_int(value, suffix, per_week=per_week), None

        around = re.search(r"(?:around|approx(?:\.|imately)?|about|circa)\s+(?:gbp?\s*)?(\d+(?:\.\d+)?)(k?)", compact)
        if around:
            value = self._money_to_int(around.group(1), around.group(2), per_week=per_week)
            return None, None, value

        bare = re.search(r"(?:gbp?\s*)?(\d+(?:\.\d+)?)(k?)\s*(?:pcm|per month|monthly|rent|budget)?", compact)
        if bare:
            after = compact[bare.end(): bare.end() + 12]
            if re.match(r"\s*(?:min|mins|minutes|mile|miles|km|sqft|sq\s*ft)\b", after):
                return None, None, None
            value = self._money_to_int(bare.group(1), bare.group(2), per_week=per_week)
            if re.search(r"\b(?:under|max(?:imum)?|up to|less than|below)\b", compact):
                return value, None, None
            if re.search(r"\b(?:over|above|at least|more than|min(?:imum)?|plus|or more)\b", compact):
                return None, value, None
            return None, None, value

        return None, None, None

    def _money_to_int(self, value: str, suffix: str, *, per_week: bool = False) -> int:
        amount = float(value)
        if suffix.lower() == "k":
            amount *= 1000
        if per_week:
            amount = amount * 52 / 12
        return int(round(amount))

    def _parse_rooms(self, text: str) -> tuple[int | None, str | None]:
        if "studio" in text:
            return 0, "studio"
        for word, count in BEDROOM_WORDS.items():
            if re.search(rf"\b{word}\b\s*(?:bed|beds|bedroom|bedrooms)?", text):
                if word == "studio":
                    return 0, "studio"
                if count > 0:
                    return count, f"{count} bed" if count > 0 else "studio"
        digit = re.search(r"\b(\d+)\s*(?:bed|beds|bedroom|bedrooms)\b", text)
        if digit:
            count = int(digit.group(1))
            return count, f"{count} bed"
        if "house share" in text or "flatshare" in text:
            return None, "room in house share"
        return None, None

    def _parse_category(self, text: str, synonym_map: dict[str, set[str]]) -> str | None:
        for canonical, options in synonym_map.items():
            for option in options:
                if re.search(rf"\b(?:no|not|without)\s+{re.escape(option)}\b", text):
                    continue
                if re.search(rf"\b{re.escape(option)}\b", text):
                    return canonical
        return None

    def _parse_council_band(self, text: str) -> str | None:
        match = re.search(r"(?:council tax\s*)?band\s*([a-h])\b", text)
        return match.group(1).upper() if match else None

    def _parse_size(self, text: str) -> tuple[int | None, int | None]:
        min_match = re.search(r"(?:at least|over|more than|minimum|min)\s*(\d+(?:\.\d+)?)\s*(?:sq\s*ft|sqft|square feet)", text)
        max_match = re.search(r"(?:under|less than|max(?:imum)?|up to)\s*(\d+(?:\.\d+)?)\s*(?:sq\s*ft|sqft|square feet)", text)
        exact = re.search(r"(\d+(?:\.\d+)?)\s*(?:sq\s*ft|sqft|square feet)", text)
        if min_match or max_match:
            return (
                int(float(min_match.group(1))) if min_match else None,
                int(float(max_match.group(1))) if max_match else None,
            )
        if exact:
            value = int(float(exact.group(1)))
            return value, value
        return None, None

    def _parse_floor(self, text: str) -> tuple[int | None, int | None]:
        if any(phrase in text for phrase in ("not basement", "no basement", "without basement", "avoid basement")):
            return 0, None
        if "ground floor" in text or text.strip().startswith("ground"):
            return 0, 0
        if "basement" in text:
            return -2, 0
        if "top floor" in text or "penthouse" in text:
            return 15, None
        if "low floor" in text:
            return 0, 3
        if "high floor" in text:
            return 8, None
        match = re.search(r"\b(\d+)(?:st|nd|rd|th)?\s*floor\b", text)
        if match:
            value = int(match.group(1))
            return value, value
        return None, None

    def _parse_build_age(self, text: str) -> bool | None:
        if any(word in text for word in NEW_BUILD_WORDS):
            return True
        if any(word in text for word in OLD_BUILD_WORDS):
            return False
        return None

    def _parse_station_walk(self, text: str) -> int | None:
        if any(
            word in text
            for word in (
                "close to station",
                "near station",
                "nearby station",
                "near by station",
                "station nearby",
                "walking distance to station",
            )
        ):
            return 10
        if re.search(r"\b(?:near|close to|by|beside|next to)\s+[a-z\s]+?\s+station\b", text):
            return 10
        match = re.search(r"(?:within|under|less than|no more than|about|around|roughly)?\s*(\d{1,2})\s*(?:min|mins|minutes)\s*(?:walk|from station|to station)", text)
        if match:
            return int(match.group(1))
        match = re.search(r"(\d{1,2})\s*(?:min|mins|minutes)\s*walk", text)
        if match:
            return int(match.group(1))
        return None

    def _parse_station_distance(self, text: str) -> float | None:
        miles = re.search(r"(?:within|under|less than|about|around)?\s*(\d+(?:\.\d+)?)\s*(?:mi|mile|miles)\b", text)
        if miles:
            return float(miles.group(1))
        km = re.search(r"(?:within|under|less than|about|around)?\s*(\d+(?:\.\d+)?)\s*km\b", text)
        if km:
            return float(km.group(1)) * 0.621371
        return None

    def _parse_landmark(self, text: str) -> str | None:
        alias_rows = []
        for canonical, aliases in LANDMARK_ALIASES.items():
            for alias in aliases:
                alias_rows.append((len(alias), canonical, alias))
        for _, canonical, alias in sorted(alias_rows, reverse=True):
            if re.search(rf"\b{re.escape(alias)}\b", text):
                return canonical
        return None

    def _parse_landmark_scope(self, text: str, landmark: str | None) -> str | None:
        if landmark != "UCL":
            return None
        if re.search(r"\bucl\s+bloomsbury\b", text):
            return "Bloomsbury"
        if re.search(r"\bucl\s+east\b", text):
            return "East"
        return None

    def _parse_landmark_walk(self, text: str, landmark: str | None) -> int | None:
        if not landmark:
            return None
        landmark_aliases = LANDMARK_ALIASES.get(landmark, {landmark.lower()})
        for alias in landmark_aliases:
            near_match = re.search(
                rf"(?:within|under|less than|no more than|about|around|roughly)?\s*(\d{{1,2}})\s*(?:min|mins|minutes)\s*(?:walk\s*)?(?:to|from|near)\s+{re.escape(alias)}\b",
                text,
            )
            if near_match:
                return int(near_match.group(1))
            reverse_match = re.search(
                rf"\b{re.escape(alias)}\b.*?(?:within|under|less than|no more than|about|around|roughly)?\s*(\d{{1,2}})\s*(?:min|mins|minutes)\s*walk",
                text,
            )
            if reverse_match:
                return int(reverse_match.group(1))
        return None

    def _nearest_station_walk(self, prop: dict[str, Any]) -> tuple[float | None, str | None]:
        stations = prop.get("nearby_stations") or []
        if stations:
            ranked = []
            for station in stations:
                walk = self._num_or_none(station.get("walk_minutes"))
                if walk is not None:
                    ranked.append((walk, str(station.get("name", "")).strip() or None))
            if ranked:
                return min(ranked, key=lambda item: item[0])
        lat = self._num_or_none(prop.get("lat"))
        lng = self._num_or_none(prop.get("lng"))
        if lat is not None and lng is not None and STATIONS:
            ranked = []
            for station in STATIONS:
                distance = self._haversine_miles(lat, lng, float(station["lat"]), float(station["lng"]))
                ranked.append((self._walk_minutes_from_miles(distance), station["name"]))
            return min(ranked, key=lambda item: item[0])
        return self._num_or_none(prop.get("station_walk_minutes")), str(prop.get("station", "")).strip() or None

    def _score_landmark(self, prop: dict[str, Any], landmark: str) -> tuple[float, float | None]:
        best_score = 0.0
        best_walk = None
        for item in prop.get("nearby_landmarks", []):
            name = str(item.get("name", ""))
            if not self._same_landmark_name(landmark, name):
                continue
            name_score = 1.0
            walk = self._num_or_none(item.get("walk_minutes"))
            distance = self._num_or_none(item.get("distance_miles"))
            proximity_bonus = 0.0
            if walk is not None:
                proximity_bonus = max(0, 18 - walk)
            elif distance is not None:
                proximity_bonus = max(0, 12 - distance * 8)
            score = 24 * name_score + proximity_bonus
            if score > best_score:
                best_score = score
                best_walk = walk
        if best_score > 0:
            return best_score, best_walk

        lat = self._num_or_none(prop.get("lat"))
        lng = self._num_or_none(prop.get("lng"))
        if lat is None or lng is None:
            return best_score, best_walk

        for item in LANDMARKS:
            if not self._same_landmark_name(landmark, str(item.get("name", ""))):
                continue
            name_score = 1.0
            distance = self._haversine_miles(lat, lng, float(item["lat"]), float(item["lng"]))
            walk = self._walk_minutes_from_miles(distance)
            if distance > 1.25:
                continue
            proximity_bonus = max(0, 18 - walk)
            score = 24 * name_score + proximity_bonus
            if score > best_score:
                best_score = score
                best_walk = walk
        return best_score, best_walk

    def _same_landmark_name(self, requested: str, candidate: str) -> bool:
        requested_norm = self._normalize_label(requested)
        candidate_norm = self._normalize_label(candidate)
        requested_aliases = {requested_norm}
        for alias in LANDMARK_ALIASES.get(requested, set()):
            requested_aliases.add(self._normalize_label(alias))
        return candidate_norm in requested_aliases

    def _normalize_label(self, value: str) -> str:
        value = re.sub(r"[^\w\s]", " ", value.lower())
        return re.sub(r"\s+", " ", value).strip()

    def _parse_station_name(self, text: str) -> str | None:
        if re.search(r"\b(?:near|nearby|near by|close to|walking distance to)\s+station\b", text):
            return None
        stop_words = {
            "studio",
            "flat",
            "apartment",
            "house",
            "room",
            "new",
            "build",
            "old",
            "period",
            "modern",
            "near",
            "close",
            "to",
            "by",
            "beside",
            "next",
            "station",
            "under",
            "max",
            "maximum",
            "around",
            "about",
            "with",
            "and",
        }
        patterns = [
            r"\b(?:near|close to|by|beside|next to)\s+([a-z][a-z\s]{1,40}?)\s+station\b",
            r"\b([a-z][a-z\s]{1,40}?)\s+station\b",
            r"\bstation\s+(?:near|at|by|in)\s+([a-z][a-z\s]{1,40})\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            candidate = match.group(1).strip()
            if re.search(r"\b(?:min|mins|minutes|walk|walking|near|nearby|near by)\b", candidate):
                continue
            words = [word for word in candidate.split() if word not in stop_words]
            if not words:
                continue
            cleaned = " ".join(words)
            return cleaned.title()
        return None

    def _parse_explicit_station(self, text: str) -> str | None:
        return self._find_best_phrase(text, self.known_stations)

    def _extract_keywords(self, tokens: list[str]) -> list[str]:
        allowed = set(SYNONYMS.get("amenity", {}).keys()) | {
            "balcony",
            "garden",
            "concierge",
            "gym",
            "parking",
            "lift",
            "step",
            "free",
            "accessible",
            "wheelchair",
            "bills",
            "included",
            "pet",
            "pets",
            "furnished",
            "unfurnished",
            "short",
            "let",
            "noisy",
            "waterfront",
            "riverside",
            "loft",
            "period",
            "converted",
            "modern",
            "luxury",
            "commuter",
            "family",
            "quiet",
            "spacious",
            "refurbished",
        }
        keywords = [token for token in tokens if token in allowed]
        joined = " ".join(tokens)
        phrase_keywords = []
        for phrase in ("step free", "bills included", "pet friendly", "short let"):
            if phrase in joined:
                phrase_keywords.append(phrase)
        return phrase_keywords + keywords

    def _extract_excludes(self, text: str) -> list[str]:
        matches = []
        protected_first_words = set()
        for phrase in (
            "basement",
            "noisy",
            "nightlife",
            "main road",
            "busy road",
            "stairs only",
            "walk up",
            "no lift",
            "house share",
            "shared bathroom",
            "pets",
            "pet friendly",
            "bills included",
            "parking",
            "garden",
            "students",
            "short let",
            "corporate let",
        ):
            if re.search(rf"\b(?:not|no|without|avoid)\s+{re.escape(phrase)}\b", text):
                matches.append(phrase)
                protected_first_words.add(phrase.split()[0])
        for match in re.findall(r"(?:no|not|without|avoid)\s+([a-z0-9]+)", text):
            if match not in protected_first_words:
                matches.append(match)
        return list(dict.fromkeys(matches))

    def _find_best_phrase(self, text: str, options: list[str]) -> str | None:
        if not options:
            return None
        matches = [(self._phrase_score(option, text), option) for option in options]
        best_score, best_option = max(matches, key=lambda item: item[0])
        return best_option if best_score >= 0.7 else None

    def _phrase_score(self, phrase: str, text: str) -> float:
        phrase_l = phrase.lower()
        text_l = text.lower()
        if phrase_l in text_l:
            return 1.0
        phrase_tokens = set(self._tokenize(phrase_l))
        text_tokens = set(self._tokenize(text_l))
        if not phrase_tokens:
            return 0.0
        overlap = len(phrase_tokens & text_tokens) / len(phrase_tokens)
        fuzzy = SequenceMatcher(None, phrase_l, text_l).ratio()
        return max(overlap, fuzzy)

    def _category_score(self, query_category: str, property_value: str) -> float:
        q = query_category.lower()
        p = property_value.lower()
        if q == p:
            return 1.0
        if q == "house":
            if p in {"house", "townhouse", "terrace", "terraced", "detached", "semi detached", "semi-detached"}:
                return 1.0
            return 0.0
        for canonical, options in {**BUILDING_SYNONYMS, **ROOM_SYNONYMS}.items():
            if q == canonical:
                if any(opt in p for opt in options):
                    return 1.0
            if q in options and (canonical in p or any(opt in p for opt in options)):
                return 1.0
        return self._phrase_score(q, p)

    def _text_similarity(self, query: str, text: str) -> float:
        query_tokens = set(self._tokenize(query))
        text_tokens = set(self._tokenize(text))
        if not query_tokens or not text_tokens:
            return 0.0
        overlap = len(query_tokens & text_tokens) / len(query_tokens)
        fuzzy = SequenceMatcher(None, query.lower(), text.lower()).ratio()
        return max(overlap, fuzzy)

    def _num_or_none(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


def load_properties(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def format_results(payload: dict[str, Any]) -> str:
    lines = ["Parsed query:"]
    lines.append(json.dumps(payload["parsed_query"], indent=2))
    lines.append("")
    lines.append("Top matches:")
    for idx, item in enumerate(payload["results"], start=1):
        prop = item["property"]
        lines.append(
            f"{idx}. {prop['name']} | {prop['location']} | {prop['monthly_rent_gbp']} pcm | "
            f"{prop['room_type']} | {prop['council_tax_band']} | score {item['score']}"
        )
        if item["reasons"]:
            lines.append(f"   - {', '.join(item['reasons'][:4])}")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse a property search query and rank dummy listings.")
    parser.add_argument("query", help="Natural language search input, e.g. '2 bed new build near Stratford under 2800'.")
    parser.add_argument(
        "--properties",
        default=str(Path(__file__).resolve().parent / "json" / "properties_enriched.json"),
        help="Path to the properties JSON file.",
    )
    parser.add_argument("--top", type=int, default=5, help="Number of results to show.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON only.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    properties = load_properties(Path(args.properties))
    engine = PropertySearchEngine(properties)
    payload = engine.search(args.query, top_n=args.top)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(format_results(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
