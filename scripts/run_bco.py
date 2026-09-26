#!/usr/bin/env python3
"""Run the local BCO profile. Explicit environment settings can override defaults."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=8765)
args = parser.parse_args()
defaults = {
    "APP_NAME": "DoD BCO Enrich",
    "DEFAULT_ONTOLOGY": "dod-bco",
    "ENABLED_ONTOLOGIES": '["dod-bco"]',
    "EMBEDDING_DISABLED": "true",
    "FOLIO_AUTO_UPDATE": "false",
    "OLLAMA_AUTO_MANAGE": "false",
    "LLM_PROVIDER": "disabled",
    "JOBS_DIR": str(ROOT / ".bco-state/jobs"),
    "FEEDBACK_DIR": str(ROOT / ".bco-state/feedback"),
}
for key, value in defaults.items():
    os.environ.setdefault("FOLIO_ENRICH_" + key, value)
sys.path.insert(0, str(ROOT / "backend"))
import uvicorn
print(f"DoD BCO (beeco): http://127.0.0.1:{args.port}/?ontology=dod-bco", flush=True)
uvicorn.run("app.main:app", host="127.0.0.1", port=args.port)
