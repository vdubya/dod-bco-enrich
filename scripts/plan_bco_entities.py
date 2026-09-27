#!/usr/bin/env python3
"""Inventory bounded entity-extraction batches; never contacts an LLM."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.bco.entities import EntityOptions, atomic_json, plan_summary
from app.bco.source import parse_ufc, parse_ufgs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ufc-directory", type=Path)
    parser.add_argument("--ufgs-archive", type=Path)
    parser.add_argument("--max-characters", type=int, default=12000)
    parser.add_argument("--max-units", type=int, default=24)
    parser.add_argument("--max-batches", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.ufc_directory and not args.ufgs_archive:
        parser.error("Supply --ufc-directory, --ufgs-archive, or both.")
    options = EntityOptions(max_characters=args.max_characters, max_units=args.max_units, max_batches=args.max_batches)
    rows = []
    def inspect(name, payload, adapter):
        row = {"name": name, "source_sha256": hashlib.sha256(payload).hexdigest()}
        try:
            bundle = adapter(payload)
        except Exception as exc:
            rows.append({**row, "planning_status": "blocked", "reason": "source_parse_failed", "error_type": type(exc).__name__})
            return
        row.update(source_family=bundle.source_family, designation=bundle.designation, version_id=bundle.version_id,
                   source_units=len(bundle.units), largest_unit_characters=max(len(u.text) for u in bundle.units))
        try:
            plan = plan_summary(bundle, options)
            row.update(planning_status="ready", batches_total=plan["batches_total"],
                       first_run_batches=plan["batches_selected"], first_run_units=plan["units_selected"])
        except ValueError:
            row.update(planning_status="blocked", reason="unit_exceeds_character_limit")
        rows.append(row)
    if args.ufc_directory:
        for source in sorted(args.ufc_directory.glob("UFC*.json")):
            inspect(source.name, source.read_bytes(), parse_ufc)
    if args.ufgs_archive:
        with zipfile.ZipFile(args.ufgs_archive) as archive:
            for name in sorted(archive.namelist()):
                if name.lower().endswith(".sec"):
                    inspect(name, archive.read(name), parse_ufgs)
    result = {"schema_version": 1, "method": "llm_entity_discovery", "status": "plan_only_no_llm_run",
              "network_calls_made": 0, "generated_entities": 0, "accepted_concepts": 0,
              "options": options.model_dump(), "sources": rows,
              "summary": {"source_files": len(rows), "ready": sum(r["planning_status"] == "ready" for r in rows),
                          "blocked": sum(r["planning_status"] == "blocked" for r in rows),
                          "source_units_in_parsed_documents": sum(r.get("source_units", 0) for r in rows),
                          "batches_in_ready_documents": sum(r.get("batches_total", 0) for r in rows)}}
    if args.ufgs_archive:
        result.update(ufgs_archive=args.ufgs_archive.name,
                      ufgs_archive_sha256=hashlib.sha256(args.ufgs_archive.read_bytes()).hexdigest())
    atomic_json(args.output, result)
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
