#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
JSON_DIR = BASE_DIR / "json"
SOURCE_PROPERTIES = JSON_DIR / "properties_30.json"
LANDMARKS_PATH = JSON_DIR / "landmarks.json"
STATIONS_PATH = JSON_DIR / "stations.json"
OUTPUT_PROPERTIES = JSON_DIR / "properties_enriched.json"

PROPERTY_COORDS = {
    "P1001": (51.5018, -0.0179),
    "P1002": (51.5327, -0.1062),
    "P1003": (51.5410, -0.0045),
    "P1004": (51.4648, -0.1290),
    "P1005": (51.5330, -0.1255),
    "P1006": (51.5841, -0.0208),
    "P1007": (51.4790, -0.0128),
    "P1008": (51.4620, -0.1142),
    "P1009": (51.4902, -0.2255),
    "P1010": (51.5096, -0.1972),
    "P1011": (51.5226, -0.1278),
    "P1012": (51.5232, -0.0770),
    "P1013": (51.4807, -0.1260),
    "P1014": (51.5405, -0.1430),
    "P1015": (51.4770, -0.1495),
    "P1016": (51.5150, -0.3032),
    "P1017": (51.5439, -0.0258),
    "P1018": (51.5218, -0.1540),
    "P1019": (51.4937, -0.0992),
    "P1020": (51.4800, -0.1965),
    "P1021": (51.5060, -0.1132),
    "P1022": (51.5652, -0.1052),
    "P1023": (51.5460, -0.1048),
    "P1024": (51.5190, -0.0610),
    "P1025": (51.4961, -0.1434),
    "P1026": (51.4988, -0.0508),
    "P1027": (51.4689, -0.2102),
    "P1028": (51.5248, -0.0345),
    "P1029": (51.4898, -0.1615),
    "P1030": (51.5888, -0.0615),
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_miles = 3958.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_miles * c


def walk_minutes(distance_miles: float) -> int:
    return max(1, int(round(distance_miles / 3.0 * 60)))


def nearby_items(
    lat: float,
    lng: float,
    items: list[dict[str, Any]],
    *,
    max_miles: float,
    limit: int,
) -> list[dict[str, Any]]:
    enriched = []
    for item in items:
        distance = haversine_miles(lat, lng, float(item["lat"]), float(item["lng"]))
        if distance > max_miles:
            continue
        payload = {
            "name": item["name"],
            "distance_miles": round(distance, 2),
            "walk_minutes": walk_minutes(distance),
        }
        if item.get("line"):
            payload["line"] = item["line"]
        if item.get("category"):
            payload["category"] = item["category"]
        enriched.append(payload)
    enriched.sort(key=lambda row: (row["walk_minutes"], row["distance_miles"], row["name"]))
    return enriched[:limit]


def main() -> int:
    properties = load_json(SOURCE_PROPERTIES)
    landmarks = load_json(LANDMARKS_PATH)
    stations = load_json(STATIONS_PATH)

    for prop in properties:
        prop_id = prop["id"]
        if prop.get("lat") is not None and prop.get("lng") is not None:
            lat, lng = float(prop["lat"]), float(prop["lng"])
        elif prop_id in PROPERTY_COORDS:
            lat, lng = PROPERTY_COORDS[prop_id]
        else:
            raise KeyError(f"Missing coordinates for {prop_id}")
        prop["lat"] = lat
        prop["lng"] = lng

        prop["nearby_stations"] = nearby_items(lat, lng, stations, max_miles=0.75, limit=5)
        prop["nearby_landmarks"] = nearby_items(lat, lng, landmarks, max_miles=1.25, limit=6)

        nearest_station = prop["nearby_stations"][0] if prop["nearby_stations"] else None
        if nearest_station:
            prop["station"] = nearest_station["name"]
            prop["station_line"] = nearest_station.get("line", prop.get("station_line", ""))
            prop["station_distance_miles"] = nearest_station["distance_miles"]
            prop["station_walk_minutes"] = nearest_station["walk_minutes"]

    write_json(OUTPUT_PROPERTIES, properties)
    print(f"Wrote {len(properties)} enriched properties to {OUTPUT_PROPERTIES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
