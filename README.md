# Living Flood Map

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

