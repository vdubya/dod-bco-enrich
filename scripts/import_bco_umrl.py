#!/usr/bin/env python3
"""Reimport processed UMRL data, preserving prior snapshots and source evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.bco.umrl import DATA, json_bytes
from app.bco.umrl_import import import_snapshot, prepare_import


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path, help="Criteria Atlas workspace containing the updated processed UMRL catalog")
    parser.add_argument("--output", type=Path, default=DATA, help="BCO UMRL snapshot store")
    parser.add_argument("--catalog-only", action="store_true", help="Refresh catalog metadata before document reference analyses have been rerun")
    parser.add_argument("--dry-run", action="store_true", help="Show differences without writing to the snapshot store")
    parser.add_argument("--report", type=Path, help="Also save the full change report to a new JSON file")
    args = parser.parse_args()
    if args.report and args.report.exists():
        parser.error("Use a new report file; an existing report will not be replaced.")
    try:
        payloads = prepare_import(args.workspace, catalog_only=args.catalog_only)
        report = import_snapshot(payloads, args.output, dry_run=args.dry_run)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"UMRL import failed: {exc}\n")
    print(json.dumps({key: report[key] for key in ("status", "from_revision_id", "to_revision_id",
        "counts", "current_summary", "reference_evidence_status")}, indent=2))
    if args.report:
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            # Never replace an import artifact or a concurrently created report.
            with args.report.open("xb") as stream:
                stream.write(json_bytes(report))
        except OSError as exc:
            parser.exit(1, f"UMRL status is {report['status']}; the separate report could not be written: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
