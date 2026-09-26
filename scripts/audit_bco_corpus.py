#!/usr/bin/env python3
"""Audit adapters without claiming semantic coverage or repairing source masters."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.bco.source import parse_ufc, parse_ufgs

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--ufc-dir", type=Path, required=True)
parser.add_argument("--ufgs-archive", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
rows = []


def audit(name, payload, parse):
    row = {"name": name, "sha256": hashlib.sha256(payload).hexdigest()}
    try:
        source = parse(payload)
        row.update(status="parsed", designation=source.designation, source_units=len(source.units),
                   guide_notes=sum(u.kind == "guide_note" for u in source.units), coverage=source.coverage)
    except Exception as exc:
        row.update(status="quarantined", error_type=type(exc).__name__, reason=str(exc))
    rows.append(row)


for path in sorted(args.ufc_dir.glob("UFC_*.json")):
    audit(path.name, path.read_bytes(), parse_ufc)
with zipfile.ZipFile(args.ufgs_archive) as archive:
    for name in sorted(archive.namelist()):
        if name.lower().endswith(".sec"):
            audit(name, archive.read(name), parse_ufgs)
report = {"scope": "adapter and source-span validation only; semantic accuracy not measured",
          "ufgs_archive": args.ufgs_archive.name, "ufgs_archive_sha256": hashlib.sha256(args.ufgs_archive.read_bytes()).hexdigest(),
          "parsed": sum(r["status"] == "parsed" for r in rows),
          "quarantined": sum(r["status"] == "quarantined" for r in rows), "sources": rows}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({k:v for k,v in report.items() if k != "sources"}, indent=2))
