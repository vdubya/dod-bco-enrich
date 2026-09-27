#!/usr/bin/env python3
"""Pin the existing Criteria Atlas UMRL catalog, usages, and analyses in BCO."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.bco.entities import atomic_json
from app.bco.umrl import DATA, UMRLCatalog


def prepare_import(workspace: Path):
    paths = {"catalog": "data/output/umrl/umrl_catalog.json",
             "viewer": "webapp/public/corpus/umrl-viewer.json",
             "corpus": "webapp/public/corpus/manifest.json",
             "source_manifest": "data/source/umrl/source_manifest.json"}
    payloads = {name: (workspace / path).read_bytes() for name, path in paths.items()}
    values = {name: json.loads(payload) for name, payload in payloads.items()}
    catalog, viewer = values["catalog"], values["viewer"]
    if catalog["record_count"] != len(catalog["records"]) or len(catalog["records"]) != len(viewer["records"]):
        raise ValueError("Existing UMRL catalog and viewer have different record counts")
    by_id = {record["reference_id"]: record for record in catalog["records"]}
    if len(by_id) != len(catalog["records"]):
        raise ValueError("Existing catalog has duplicate reference IDs")
    for record in viewer["records"]:
        prior = by_id.get(record["reference_id"])
        if prior is None or any(record.get(key) != value for key, value in prior.items()):
            raise ValueError("Existing UMRL catalog and viewer metadata disagree")
    for field in ("source_archive", "source_member"):
        if catalog[field] != viewer[field]:
            raise ValueError("Existing UMRL catalog and viewer source provenance disagree")
    analyses, origins = [], []
    for document in values["corpus"]["documents"]:
        stem = Path(document.get("source_file") or document["designation"].replace(" ", "_")).stem
        relative = f"data/output/ufc/{stem}/umrl_analysis.json"
        # Match build-corpus.mjs: older document summaries have no umrl_status.
        if not (workspace / relative).exists():
            continue
        payload = (workspace / relative).read_bytes()
        analysis = json.loads(payload)
        if analysis["catalog_record_count"] != catalog["record_count"] or any(
                analysis[field] != catalog[field] for field in ("source_archive", "source_member")):
            raise ValueError("Saved UMRL analysis was produced from a different catalog")
        analyses.append({"designation": document["designation"], "source_file": relative,
                         "document_version_id": document["document_version_id"], "analysis": analysis})
        origins.append({"source_path": relative, "sha256": hashlib.sha256(payload).hexdigest()})
    analysis_payload = (json.dumps(analyses, ensure_ascii=False, indent=2) + "\n").encode()
    catalog_sha = hashlib.sha256(payloads["catalog"]).hexdigest()
    manifest = {
        "schema_version": 1, "snapshot_id": "umrl-catalog:" + catalog_sha,
        "method": "reuse_existing_criteria_atlas_artifacts",
        "upstream_source_provenance": values["source_manifest"],
        "original_inputs": {name: {"source_path": paths[name], "sha256": hashlib.sha256(payload).hexdigest()}
                            for name, payload in payloads.items()},
        "artifacts": {
            "umrl-viewer.json": {"source_path": paths["viewer"], "sha256": hashlib.sha256(payloads["viewer"]).hexdigest(), "copy_method": "byte_for_byte"},
            "prior-analyses.json": {"sha256": hashlib.sha256(analysis_payload).hexdigest(), "original_files": origins},
        },
        "viewer_implementation": "webapp/src/criteria-atlas-app.ts",
        "resolver_implementation": "src/criteria_graph/umrl_pass.py",
        "identity_policy": "Preserve viewer reference_id and saved match IDs; legacy graph slugs are secondary and may collide.",
        "new_extraction_calls": 0,
    }
    imported = UMRLCatalog(viewer, analyses, manifest)
    return payloads["viewer"], analysis_payload, manifest, imported


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path, help="Existing Criteria Atlas workspace")
    parser.add_argument("--output", type=Path, default=DATA)
    args = parser.parse_args()
    viewer, analyses, manifest, catalog = prepare_import(args.workspace)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "umrl-viewer.json").write_bytes(viewer)
    (args.output / "prior-analyses.json").write_bytes(analyses)
    atomic_json(args.output / "manifest.json", manifest)
    print(json.dumps({"summary": catalog.summary, "legacy_graph_id_collisions": catalog.collisions,
                      "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
