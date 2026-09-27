"""Repeatable imports of the official UFC master PDF without replacing old evidence."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import httpx

from app.bco.glossary import SOURCE_URL, index_pdf, read_snapshot
from app.bco.umrl import json_bytes
from app.bco.umrl_import import _atomic_write, _import_lock, _write_bytes

MAX_BYTES = 40 * 1024 * 1024


def download_official() -> tuple[bytes, dict]:
    """Fetch the fixed publisher URL; do not fetch publications it references."""
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        with client.stream("GET", SOURCE_URL) as response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError("Glossary PDF exceeds the import size limit")
                chunks.append(chunk)
            acquisition = {"method": "download_official_url", "requested_url": SOURCE_URL,
                "final_url": str(response.url), "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "http_metadata": {k: response.headers[k] for k in ("content-type", "etag", "last-modified") if k in response.headers},
                "publication_edition_inferred_from_http_metadata": False}
    return b"".join(chunks), acquisition


def compare_indexes(before: dict | None, after: dict) -> dict:
    old = {s["section_id"]: s for s in before["sections"]} if before else {}
    new = {s["section_id"]: s for s in after["sections"]}
    changed = []
    for sid in sorted(old.keys() & new.keys()):
        fields = {key: {"before": old[sid][key], "after": new[sid][key]}
                  for key in ("text_sha256", "pdf_page_start", "pdf_page_end", "bookmark_title_exact")
                  if old[sid][key] != new[sid][key]}
        if fields:
            changed.append({"section_id": sid, "fields": fields, "review_required": True})
    added, absent = sorted(new.keys() - old.keys()), sorted(old.keys() - new.keys())
    return {"schema_version": 1, "source_id": after["source_id"],
        "from_source_sha256": before["source_sha256"] if before else None,
        "to_source_sha256": after["source_sha256"],
        "comparison_unit": "UFC_and_section_role_not_individual_terms",
        "counts": {"added": len(added), "changed": len(changed), "absent_from_new_snapshot": len(absent),
                   "unchanged": len(old.keys() & new.keys()) - len(changed)},
        "added": added, "changed": changed, "absent_from_new_snapshot": absent,
        "absent_does_not_mean_withdrawn": True, "current_summary": after["summary"],
        "structure_findings": after["findings"], "review_decisions_modified": False,
        "project_adoption_inferred": False, "new_extraction_calls": 0}


def _existing(directory: Path):
    if not (directory / "current.json").exists():
        return None
    revision = json.loads((directory / "current.json").read_bytes())["source_sha256"]
    if not isinstance(revision, str) or len(revision) != 64 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("Invalid current glossary snapshot ID")
    return read_snapshot(directory / "snapshots" / revision, revision)[1]


def import_pdf(payload: bytes, directory: Path, *, acquisition: dict, dry_run: bool = False) -> dict:
    if not payload.startswith(b"%PDF-") or len(payload) > MAX_BYTES:
        raise ValueError("Expected a PDF within the import size limit")
    revision = hashlib.sha256(payload).hexdigest()
    destination = directory / "snapshots" / revision
    if destination.exists():
        # Same source bytes retain their original parser output and provenance.
        # Parser upgrades never silently rewrite a previously cited snapshot.
        _, incoming = read_snapshot(destination, revision)
    else:
        incoming = index_pdf(payload)
    if dry_run:
        before = _existing(directory)
        return {**compare_indexes(before, incoming),
                "status": "unchanged" if before and before["source_sha256"] == revision else "would_import"}
    directory.mkdir(parents=True, exist_ok=True)
    with _import_lock(directory):
        before = _existing(directory)
        # Recheck under the writer lock to handle simultaneous import attempts.
        if destination.exists():
            _, incoming = read_snapshot(destination, revision)
        report = compare_indexes(before, incoming)
        if before and before["source_sha256"] == revision:
            return {**report, "status": "unchanged"}
        if not destination.exists():
            index_payload = json_bytes(incoming)
            manifest = {"schema_version": 1, "source_id": incoming["source_id"],
                "source_family": incoming["source_family"], "source_url": SOURCE_URL,
                "source_sha256": revision, "title": incoming["title"], "acquisition": acquisition,
                "source_edition": incoming["source_edition"], "pdf_metadata": incoming["pdf_metadata"],
                "summary": incoming["summary"], "extraction": incoming["extraction"],
                "artifacts": {"source.pdf": {"sha256": revision, "bytes": len(payload), "copy_method": "byte_for_byte"},
                    "page-index.json": {"sha256": hashlib.sha256(index_payload).hexdigest(), "bytes": len(index_payload)}},
                "source_role": "UFC_scoped_glossary_and_reference_assertions",
                "umrl_is_separate_publication_catalog": True, "project_adoption_inferred": False}
            destination.parent.mkdir(exist_ok=True)
            stage = Path(tempfile.mkdtemp(prefix=".staging-", dir=directory))
            try:
                for name, data in {"source.pdf": payload, "page-index.json": index_payload,
                                   "manifest.json": json_bytes(manifest)}.items():
                    _write_bytes(stage / name, data)
                read_snapshot(stage, revision)
                os.rename(stage, destination)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
        report["status"] = "imported"
        report_payload = json_bytes(report)
        report_id = hashlib.sha256(report_payload).hexdigest()
        changes = directory / "changes"
        changes.mkdir(exist_ok=True)
        report_path = changes / (report_id + ".json")
        if report_path.exists():
            if report_path.read_bytes() != report_payload:
                raise ValueError("An immutable glossary change report has different bytes")
        else:
            _atomic_write(report_path, report_payload)
        # Readers see the new release only after all artifacts pass validation.
        _atomic_write(directory / "current.json", json_bytes({"schema_version": 1,
            "source_sha256": revision, "previous_source_sha256": before["source_sha256"] if before else None,
            "change_report_id": report_id}))
        return report
