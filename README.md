# Property NLP Search Demo

An interview-ready prototype showing how natural-language property search could sit inside a modern property portal experience.

The bundle includes a polished iPhone product demo, a first-run onboarding flow, a full web app, a Python search backend, explainable ranking logic, and the JSON data used by the demo.

## What to open

The main interview surface is:

```text
demo/iphone-frame.html
```

When served through the Python backend, the iPhone frame loads the bundled live app and calls the local API.

The infrastructure view is:

```text
demo/dev_whiteboard.html
```

It shows the query parser, search flow, result scoring, and backend data model in a presentation-friendly dashboard.

## Run locally

From the repo root:

```bash
python3 engine/server.py
```

Then open:

```text
http://127.0.0.1:8787/demo/iphone-frame.html
```

Useful direct routes:

```text
http://127.0.0.1:8787/demo/live-demo.html
http://127.0.0.1:8787/demo/dev_whiteboard.html
http://127.0.0.1:8787/api/search?q=studio%20near%20ucl%20under%202500&top=8&min_score=35
http://127.0.0.1:8787/api/properties
```

## Project Structure

```text
.
├── demo/
│   ├── iphone-frame.html          # main product demo in an iPhone frame
│   ├── live-demo.html             # bundled property NLP web app
│   ├── property-nlp-onboarding.html # first-run onboarding shown before search
│   └── dev_whiteboard.html        # infrastructure and scoring dashboard
├── engine/
│   ├── server.py                  # local HTTP server and API endpoints
│   ├── property_search.py         # parser, filters, scoring, explanations
│   ├── vector_search.py           # lightweight TF-IDF semantic match layer
│   └── json/
│       ├── properties_enriched.json
│       ├── stations.json
│       ├── landmarks.json
│       └── synonyms.json
├── assets/                        # legacy static demo assets
├── data/                          # legacy static demo data mirror
├── docs/                          # case study notes and journey docs
└── index.html                     # redirect to the main demo surface
```

## Backend API

`GET /api/search`

Parameters:

- `q`: natural-language search query
- `top`: number of results to return
- `min_score`: match strictness threshold used by the UI

Example:

```bash
curl "http://127.0.0.1:8787/api/search?q=studio%20near%20ucl%20under%202500&top=8&min_score=35"
```

`GET /api/properties`

Returns the property JSON used by the frontend filter controls.

## Python CLI

Run the ranking engine directly:

```bash
python3 engine/property_search.py "studio near ucl under 2500 not basement"
```

Machine-readable output:

```bash
python3 engine/property_search.py "studio near ucl under 2500 not basement" --json
```

## GitHub Pages Note

The HTML can be hosted statically, but GitHub Pages cannot run the Python backend. For a fully live remote demo, point the frontend at a hosted API such as Hugging Face Spaces, Render, or another small Python service.

For interview use, the most reliable path is the local Python server:

```bash
python3 engine/server.py
```

## Positioning

This is a concept prototype, not a production integration with any live property portal. It is designed to show product judgment, UI polish, explainable search ranking, backend data thinking, and the ability to package a technical idea into a demo that a reviewer can actually use.
