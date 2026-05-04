# GitHub Pages Plan

## Goal

Host the editorial case study and the interactive demo on GitHub Pages so reviewers can inspect the product without running Python.

## What goes on Pages

- `index.html` as the editorial landing page
- `demo/search.html` as the interactive search prototype
- `demo/onboarding.html` as the launch narrative

## What stays local

- `engine/property_search.py`
- `engine/precompute_geo.py`
- the full Python-backed search workflow

## Deployment method

1. push this repo to GitHub
2. enable GitHub Pages on the repository
3. serve from the root branch or `gh-pages`
4. keep the demo pages static and fetch JSON from `data/`

## Why this split matters

GitHub Pages is ideal for the portfolio story and interaction proof.
The Python engine is ideal for the implementation proof.
Together, they cover both design credibility and technical credibility.

