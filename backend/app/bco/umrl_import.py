"""Repeatable UMRL imports with immutable snapshots and an atomic active pointer."""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from app.bco.umrl import (UMRLCatalog, catalog_from_artifacts, json_bytes,
                          read_artifacts, snapshot_location)


def _catalog_viewer(catalog: dict) -> dict:
    """Prepare new catalog metadata without reusing stale reference matches."""
    organizations = Counter(r["organization"] for r in catalog["records"])
    return {**catalog, "organization_count": len(organizations),
        "processed_document_count": 0, "used_record_count": 0, "match_count": 0,
        "organizations": [{"organization": name, "record_count": count,
            "used_record_count": 0, "mention_count": 0} for name, count in sorted(organizations.items())],
        "records": [{**record, "usage_count": 0, "document_count": 0, "usages": []}
                    for record in catalog["records"]]}


def prepare_import(workspace: Path, *, catalog_only: bool = False) -> dict[str, bytes]:
    paths = {"catalog": "data/output/umrl/umrl_catalog.json",
             "viewer": "webapp/public/corpus/umrl-viewer.json",
             "corpus": "webapp/public/corpus/manifest.json",
             "source_manifest": "data/source/umrl/source_manifest.json"}
    names = ("catalog", "source_manifest") if catalog_only else tuple(paths)
    payloads = {name: (workspace / paths[name]).read_bytes() for name in names}
    values = {name: json.loads(payload) for name, payload in payloads.items()}
    catalog = values["catalog"]
    if not catalog["records"] or catalog["record_count"] != len(catalog["records"]):
        raise ValueError("UMRL import requires a nonempty catalog with consistent counts")
    if catalog["source_archive"] != values["source_manifest"]["archive"] or catalog["source_member"] != values["source_manifest"]["umrl_member"]:
        raise ValueError("Catalog and UMRL source manifest refer to different sources")
    by_id = {record["reference_id"]: record for record in catalog["records"]}
    if len(by_id) != len(catalog["records"]):
        raise ValueError("Existing catalog has duplicate reference IDs")
    if catalog_only:
        viewer = _catalog_viewer(catalog)
        viewer_payload = json_bytes(viewer)
    else:
        viewer, viewer_payload = values["viewer"], payloads["viewer"]
        if len(catalog["records"]) != len(viewer["records"]):
            raise ValueError("Existing UMRL catalog and viewer have different record counts")
        for record in viewer["records"]:
            prior = by_id.get(record["reference_id"])
            if prior is None or any(record.get(key) != value for key, value in prior.items()):
                raise ValueError("Existing UMRL catalog and viewer metadata disagree; refresh the viewer or use --catalog-only")
        for field in ("source_archive", "source_member"):
            if catalog[field] != viewer[field]:
                raise ValueError("Existing UMRL catalog and viewer source provenance disagree")
    analyses, origins = [], []
    for document in values.get("corpus", {}).get("documents", []):
        stem = Path(document.get("source_file") or document["designation"].replace(" ", "_")).stem
        relative = f"data/output/ufc/{stem}/umrl_analysis.json"
        if not (workspace / relative).exists():
            continue
        payload = (workspace / relative).read_bytes()
        analysis = json.loads(payload)
        if analysis["catalog_record_count"] != catalog["record_count"] or any(
                analysis[field] != catalog[field] for field in ("source_archive", "source_member")):
            raise ValueError("Saved UMRL analysis was produced from a different catalog; refresh it or use --catalog-only")
        analyses.append({"designation": document["designation"], "source_file": relative,
                         "document_version_id": document["document_version_id"], "analysis": analysis})
        origins.append({"source_path": relative, "sha256": hashlib.sha256(payload).hexdigest()})
    analysis_payload = json_bytes(analyses)
    manifest = {
        "schema_version": 1, "snapshot_id": "umrl-catalog:" + hashlib.sha256(payloads["catalog"]).hexdigest(),
        "method": "reuse_existing_criteria_atlas_artifacts",
        "upstream_source_provenance": values["source_manifest"],
        "original_inputs": {name: {"source_path": paths[name], "sha256": hashlib.sha256(payload).hexdigest()}
                            for name, payload in payloads.items()},
        "artifacts": {
            "umrl-viewer.json": {"source_path": paths["catalog"] if catalog_only else paths["viewer"],
                "sha256": hashlib.sha256(viewer_payload).hexdigest(),
                "copy_method": "catalog_metadata_without_reconciled_usages" if catalog_only else "byte_for_byte"},
            "prior-analyses.json": {"sha256": hashlib.sha256(analysis_payload).hexdigest(), "original_files": origins},
        },
        "viewer_implementation": "webapp/src/criteria-atlas-app.ts",
        "resolver_implementation": "src/criteria_graph/umrl_pass.py",
        "identity_policy": "Preserve viewer reference_id and saved match IDs; legacy graph slugs are secondary and may collide.",
        "new_extraction_calls": 0,
    }
    if catalog_only:
        manifest.update(import_mode="catalog_only", reference_evidence_status="not_reconciled_against_this_catalog")
    result = {"manifest.json": json_bytes(manifest), "umrl-viewer.json": viewer_payload,
              "prior-analyses.json": analysis_payload}
    catalog_from_artifacts(result)
    return result


def compare_catalogs(before: UMRLCatalog | None, after: UMRLCatalog) -> dict:
    old, new = before.records if before else {}, after.records
    fields = ("reference_title", "title_without_edition", "organization", "organization_acronyms", "listed_edition_statement")
    changed = []
    for rid in sorted(old.keys() & new.keys()):
        differences = {field: {"before": old[rid][field], "after": new[rid][field]}
                       for field in fields if old[rid][field] != new[rid][field]}
        if differences:
            changed.append({"entity_id": rid, "fields": differences,
                "prior_catalog_entry_id": old[rid]["catalog_entry_id"],
                "new_catalog_entry_id": new[rid]["catalog_entry_id"], "review_required": True})
    added, absent = sorted(new.keys() - old.keys()), sorted(old.keys() - new.keys())
    return {"schema_version": 1, "from_revision_id": before.revision_id if before else None,
        "to_revision_id": after.revision_id, "from_snapshot_id": before.provenance["snapshot_id"] if before else None,
        "to_snapshot_id": after.provenance["snapshot_id"],
        "counts": {"added": len(added), "changed": len(changed), "absent_from_new_catalog": len(absent),
                   "unchanged": len(old.keys() & new.keys()) - len(changed)},
        "added": added, "changed": changed, "absent_from_new_catalog": absent,
        "absent_does_not_mean_withdrawn": True,
        "previous_summary": before.summary if before else None, "current_summary": after.summary,
        "reference_evidence_status": after.provenance.get("reference_evidence_status", "saved_analysis_joins_validated"),
        "legacy_graph_id_collisions": after.collisions,
        "review_decisions_modified": False, "project_adoption_inferred": False,
        "new_extraction_calls": 0}


@contextmanager
def _import_lock(directory: Path):
    """Serialize writers; readers never need this lock."""
    with (directory / ".import.lock").open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


def _write_bytes(path: Path, payload: bytes):
    with path.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _atomic_write(path: Path, payload: bytes):
    fd, temporary = tempfile.mkstemp(prefix=".staging-", dir=path.parent)
    os.close(fd)
    try:
        _write_bytes(Path(temporary), payload)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _save_revision(directory: Path, payloads: dict[str, bytes], revision: str):
    snapshots = directory / "snapshots"
    snapshots.mkdir(exist_ok=True)
    destination = snapshots / revision
    if destination.exists():
        if read_artifacts(destination) != payloads:
            raise ValueError("An immutable UMRL revision has different bytes")
        return
    stage = Path(tempfile.mkdtemp(prefix=".staging-", dir=directory))
    try:
        for name, payload in payloads.items():
            _write_bytes(stage / name, payload)
        checked = catalog_from_artifacts(read_artifacts(stage))
        if checked.revision_id != revision:
            raise ValueError("Staged UMRL revision failed validation")
        os.rename(stage, destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _existing(directory: Path):
    if not (directory / "current.json").exists() and not (directory / "manifest.json").exists():
        return None, None
    location, expected = snapshot_location(directory)
    payloads = read_artifacts(location)
    catalog = catalog_from_artifacts(payloads)
    if catalog.revision_id != expected:
        raise ValueError("Existing active UMRL revision failed validation")
    return payloads, catalog


def import_snapshot(payloads: dict[str, bytes], directory: Path, *, dry_run: bool = False) -> dict:
    incoming = catalog_from_artifacts(payloads)
    if dry_run:
        _, before = _existing(directory)
        report = compare_catalogs(before, incoming)
        return {**report, "status": "unchanged" if before and before.revision_id == incoming.revision_id else "would_import"}
    directory.mkdir(parents=True, exist_ok=True)
    with _import_lock(directory):
        prior_payloads, before = _existing(directory)
        report = compare_catalogs(before, incoming)
        if before and before.revision_id == incoming.revision_id:
            return {**report, "status": "unchanged"}
        if before:
            _save_revision(directory, prior_payloads, before.revision_id)
        _save_revision(directory, payloads, incoming.revision_id)
        report["status"] = "imported"
        report_payload = json_bytes(report)
        report_id = hashlib.sha256(report_payload).hexdigest()
        changes = directory / "changes"
        changes.mkdir(exist_ok=True)
        report_path = changes / (report_id + ".json")
        if report_path.exists():
            if report_path.read_bytes() != report_payload:
                raise ValueError("An immutable UMRL change report has different bytes")
        else:
            _atomic_write(report_path, report_payload)
        # Only this final replace makes the validated release visible to readers.
        _atomic_write(directory / "current.json", json_bytes({"schema_version": 1,
            "revision_id": incoming.revision_id, "previous_revision_id": before.revision_id if before else None,
            "change_report_id": report_id}))
        return report
