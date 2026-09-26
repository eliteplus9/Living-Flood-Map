# Living Flood Map

## Cloudflare application (Mailles's integration branch)

The active Cloudflare UI lives in `frontend/`, with Worker API routes in
`worker/` and shared request types in `shared/`. The original Python
Streamlit scaffold remains below for reference and teammate integration.

With Node.js 22.12+ installed, run:

```bash
npm install
npm run verify
npm run dev:worker
```

In a second terminal, run `npm run dev`, then open
`http://localhost:5173`. The app can load the supplied historical CSV
or an unseen CSV selected in the browser.

The Investigate view links report text, evidence types, map places and
session-only reviewer annotations. The Worker can use Edward's classifier
and Mutasim's location service when separately configured. Without those
services, the app clearly labels its local keyword and Alberta-gazetteer
preview. The overview and Markdown briefing state the limits of their
evidence. See [INTEGRATION.md](INTEGRATION.md) for setup and contracts.

This branch is a local-review and integration contribution. It does not
deploy itself or replace teammates' Python work. Edward's 3D map experiment
is not merged into this branch.

---

Thunder Bay AI Hackathon 2026 — Living Flood Map

Overview
--------

Living Flood Map is a fast prototype to identify and map flood-related
reports from social media (tweets). This repo scaffolds a Streamlit
frontend today and a clean `src/` Python package so the core logic can be
reused by a future FastAPI backend and React frontend.

Key capabilities (planned)
- Classify tweets as flood/disaster-related or noise
- Semantic search / RAG over relevant tweets
- Summarize retrieved reports with an LLM
- Extract mentioned locations and geocode them
- Display results on an interactive map
- Accept uploaded CSVs (same format) for ad-hoc runs

Repository layout
-----------------
- `app.py` — Streamlit UI (calls into `src/` only)
- `src/` — Reusable business logic modules (classification, rag, geocode, map)
- `data/main_contestant.csv` — Local dataset (do not move)
- `.env.example` — Example env vars
- `requirements.txt` — Python dependencies

Setup
-----

1. Create a Python virtual environment (recommended) and activate it.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and populate any keys (e.g. `OPENAI_API_KEY`).

Running the Streamlit app
-------------------------

From the repository root run:

```bash
streamlit run app.py
```

This starts the Streamlit UI which uses the `src/` package for all data and
processing. `app.py` contains only UI wiring and should remain free of
business logic so it can be replaced later by a FastAPI + React frontend.

Future work
-----------

- Replace placeholder functions in `src/` with real model-based
	classifiers, embedding pipelines (ChromaDB), and LLM summarizers.
- Add a FastAPI backend that imports `src/` and exposes endpoints for
	classification, search, and geocoding so a React frontend can be built.

Notes
-----
- The `data/` folder and real `.env` are expected to be ignored by Git.
- This repository intentionally contains minimal implementations — the
	scaffolding emphasizes clear interfaces and separation of concerns.

