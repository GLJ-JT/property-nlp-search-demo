#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from property_search import PropertySearchEngine, load_properties


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = ROOT_DIR / "engine" / "json" / "properties_enriched.json"


class SearchDemoHandler(SimpleHTTPRequestHandler):
    engine: PropertySearchEngine

    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory or str(ROOT_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/api/search", "/api/properties"}:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        super().do_HEAD()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/search":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0]
            top = self._parse_top(params.get("top", ["8"])[0])
            min_score = self._parse_min_score(params.get("min_score", ["35"])[0])
            self._send_search(query, top, min_score)
            return
        if parsed.path == "/api/properties":
            self._send_json({"properties": self.engine.properties})
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/search":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Request body must be JSON.")
            return

        query = str(payload.get("query", ""))
        top = self._parse_top(payload.get("top", 8))
        min_score = self._parse_min_score(payload.get("min_score", 35))
        self._send_search(query, top, min_score)

    def _parse_top(self, value: object) -> int:
        try:
            return max(1, min(12, int(value)))
        except (TypeError, ValueError):
            return 8

    def _parse_min_score(self, value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 35.0

    def _send_search(self, query: str, top: int, min_score: float) -> None:
        if not query.strip():
            self._send_json({"error": "Missing q query parameter."}, status=400)
            return

        payload = self.engine.search(query, top_n=top, min_score=min_score)
        payload["engine"] = {
            "name": "PropertySearchEngine",
            "source": "engine/property_search.py",
            "data": str(DEFAULT_DATA_PATH.relative_to(ROOT_DIR)),
            "mode": "python-backend",
        }
        self._send_json(payload)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the Property NLP demo with a Python search API.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--port", type=int, default=8787, help="Port to bind.")
    parser.add_argument("--properties", default=str(DEFAULT_DATA_PATH), help="Property JSON path.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    properties = load_properties(Path(args.properties))
    SearchDemoHandler.engine = PropertySearchEngine(properties)
    server = ThreadingHTTPServer((args.host, args.port), SearchDemoHandler)
    print(f"Serving Property NLP demo at http://{args.host}:{args.port}/")
    print(f"API: http://{args.host}:{args.port}/api/search?q=studio%20near%20ucl%20under%202500%20not%20basement")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
