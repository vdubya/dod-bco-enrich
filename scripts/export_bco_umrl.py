#!/usr/bin/env python3
"""Export the reused UMRL named entities without model calls or source mining."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.bco.entities import atomic_json
from app.bco.umrl import default_umrl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New JSON export file")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output file; an existing export will not be replaced.")
    catalog = default_umrl()
    value = {"schema_version": 1, "method": "reuse_existing_criteria_atlas_artifacts",
        "source": catalog.provenance, "summary": catalog.summary,
        "entities": list(catalog.records.values()), "organizations": list(catalog.organizations.values()),
        "legacy_graph_id_collisions": catalog.collisions,
        "catalog_membership_establishes_project_adoption": False}
    atomic_json(args.output, value)
    print(json.dumps({"summary": catalog.summary, "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
