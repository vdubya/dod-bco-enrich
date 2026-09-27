"""UMRL release transitions: repeatability, retained evidence, and live readers."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from app.bco import umrl, umrl_import
from app.bco.entities import extract_entities
from app.bco.source import parse_ufc
from app.bco.umrl import catalog_from_artifacts, json_bytes, load_umrl
from app.bco.umrl_import import import_snapshot, prepare_import


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "workspace"
    records = [{"reference_id": rid, "reference_title": f"(2017) {title}", "title_without_edition": title,
        "organization": "TEST ORGANIZATION (TO)", "organization_acronyms": ["TO"]}
        for rid, title in [("TEST 1", "Testing requirements"), ("OLD 2", "Old publication"), ("STABLE 3", "Stable publication")]]
    catalog = {"source_archive": "fixture-old.zip", "source_member": "MASTER.REF", "record_count": 3, "records": records}
    match = {"match_id": "UMRL-MATCH-original", "axiom_id": "axiom-original", "reference_id": "TEST 1",
        "reference_title": records[0]["reference_title"], "organization": records[0]["organization"],
        "match_basis": "reference_id_exact", "matched_value": "TEST 1", "confidence": 0.97,
        "review_status": "machine_extracted", "source_text_exact": "Apply TEST 1.", "source_anchor": "anchor-original"}
    analysis = {"source_archive": catalog["source_archive"], "source_member": "MASTER.REF",
        "catalog_record_count": 3, "match_count": 1, "matches": [match],
        "unresolved_candidate_count": 1, "unresolved_candidates": [{"mention_text": "UNKNOWN 5", "source_anchor": "anchor-original"}]}
    viewer = umrl_import._catalog_viewer(catalog)
    viewer.update(processed_document_count=1, match_count=1, used_record_count=1)
    viewer["records"][0].update(usage_count=1, document_count=1, usages=[{**match, "designation": "UFC TEST"}])
    write_json(root / "data/output/umrl/umrl_catalog.json", catalog)
    write_json(root / "data/source/umrl/source_manifest.json", {"archive": "fixture-old.zip", "umrl_member": "MASTER.REF", "release_date": "2026-05-28"})
    write_json(root / "webapp/public/corpus/umrl-viewer.json", viewer)
    write_json(root / "webapp/public/corpus/manifest.json", {"documents": [{"designation": "UFC TEST",
        "source_file": "data/source/ufc/UFC_TEST.json", "document_version_id": "UFC-TEST-v1"}]})
    write_json(root / "data/output/ufc/UFC_TEST/umrl_analysis.json", analysis)
    return root


def update_catalog(workspace):
    path = workspace / "data/output/umrl/umrl_catalog.json"
    catalog = json.loads(path.read_bytes())
    catalog["source_archive"] = "fixture-new.zip"
    catalog["records"][0]["reference_title"] = "(2026) Revised testing requirements"
    catalog["records"][0]["title_without_edition"] = "Revised testing requirements"
    catalog["records"] = [r for r in catalog["records"] if r["reference_id"] != "OLD 2"]
    catalog["records"].append({"reference_id": "NEW 4", "reference_title": "(2026) New publication",
        "title_without_edition": "New publication", "organization": "NEW ORGANIZATION (NO)", "organization_acronyms": ["NO"]})
    write_json(path, catalog)
    write_json(workspace / "data/source/umrl/source_manifest.json", {"archive": "fixture-new.zip", "umrl_member": "MASTER.REF", "release_date": "2026-09-01"})
    return prepare_import(workspace, catalog_only=True)


def files(directory):
    return {str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob("*") if p.is_file()}


def test_repeat_import_is_noop_and_dry_run_writes_nothing(workspace, tmp_path):
    store = tmp_path / "store"
    payloads = prepare_import(workspace)
    plan = import_snapshot(payloads, store, dry_run=True)
    assert plan["status"] == "would_import" and not store.exists()
    imported = import_snapshot(payloads, store)
    saved = files(store)
    assert import_snapshot(payloads, store)["status"] == "unchanged"
    assert files(store) == saved
    incoming = update_catalog(workspace)
    plan = import_snapshot(incoming, store, dry_run=True)
    assert plan["from_revision_id"] == imported["to_revision_id"]
    assert plan["counts"] == {"added": 1, "changed": 1, "absent_from_new_catalog": 1, "unchanged": 1}
    assert files(store) == saved


def test_new_release_preserves_original_evidence_and_flags_changed_editions(workspace, tmp_path):
    store = tmp_path / "store"
    old = prepare_import(workspace)
    original = import_snapshot(old, store)
    before = load_umrl(store)
    report = import_snapshot(update_catalog(workspace), store)
    current = load_umrl(store)
    history = load_umrl(store, revision=original["to_revision_id"])
    assert current.get("TEST 1")["entity_id"] == history.get("TEST 1")["entity_id"]
    assert current.get("TEST 1")["catalog_entry_id"] != history.get("TEST 1")["catalog_entry_id"]
    assert current.get("TEST 1")["listed_edition_statement"] == "(2026)"
    assert history.get("TEST 1") == before.get("TEST 1")
    assert history.get("TEST 1")["prior_matches"][0]["match_id"] == "UMRL-MATCH-original"
    assert current.get("TEST 1")["prior_matches"] == []
    assert current.get("OLD 2") is None and history.get("OLD 2") is not None
    assert report["absent_from_new_catalog"] == ["OLD 2"]
    assert report["absent_does_not_mean_withdrawn"] is True
    assert report["changed"][0]["fields"]["listed_edition_statement"] == {"before": "(2017)", "after": "(2026)"}
    assert report["changed"][0]["review_required"] is True
    assert report["review_decisions_modified"] is False
    assert report["reference_evidence_status"] == "not_reconciled_against_this_catalog"
    prior_bytes = (store / "snapshots" / original["to_revision_id"] / "prior-analyses.json").read_bytes()
    assert prior_bytes == old["prior-analyses.json"]


def test_legacy_flat_snapshot_is_archived_before_switching(workspace, tmp_path):
    store = tmp_path / "legacy"
    store.mkdir()
    original = prepare_import(workspace)
    for name, payload in original.items():
        (store / name).write_bytes(payload)
    revision = load_umrl(store).revision_id
    import_snapshot(update_catalog(workspace), store)
    assert load_umrl(store, revision).get("OLD 2") is not None
    assert len(umrl.umrl_history(store)["revisions"]) == 2
    for name, payload in original.items():
        assert (store / name).read_bytes() == payload
        assert (store / "snapshots" / revision / name).read_bytes() == payload


def test_stale_viewer_rejected_but_catalog_only_needs_no_refreshed_analyses(workspace):
    update_catalog(workspace)
    with pytest.raises(ValueError, match="disagree"):
        prepare_import(workspace)
    (workspace / "webapp/public/corpus/manifest.json").unlink()
    (workspace / "webapp/public/corpus/umrl-viewer.json").unlink()
    catalog = catalog_from_artifacts(prepare_import(workspace, catalog_only=True))
    assert catalog.summary["publications"] == 3 and catalog.summary["prior_matches"] == 0


@pytest.mark.parametrize("damage", ["empty", "duplicate", "wrong_source"])
def test_invalid_catalog_cannot_replace_active_release(workspace, tmp_path, damage):
    store = tmp_path / "store"
    import_snapshot(prepare_import(workspace), store)
    previous = files(store)
    path = workspace / "data/output/umrl/umrl_catalog.json"
    catalog = json.loads(path.read_bytes())
    if damage == "empty":
        catalog.update(records=[], record_count=0)
    elif damage == "duplicate":
        catalog["records"][1]["reference_id"] = catalog["records"][0]["reference_id"]
    else:
        catalog["source_archive"] = "mismatched.zip"
    write_json(path, catalog)
    with pytest.raises(ValueError):
        import_snapshot(prepare_import(workspace, catalog_only=True), store)
    assert files(store) == previous


def test_corrupt_payload_rejected_before_any_writes(workspace, tmp_path):
    incoming = prepare_import(workspace)
    incoming["umrl-viewer.json"] += b" "
    store = tmp_path / "store"
    with pytest.raises(ValueError, match="pinned manifest"):
        import_snapshot(incoming, store)
    assert not store.exists()


def test_interrupted_activation_keeps_old_snapshot_and_retry_completes(workspace, tmp_path, monkeypatch):
    store = tmp_path / "store"
    old = import_snapshot(prepare_import(workspace), store)["to_revision_id"]
    incoming = update_catalog(workspace)
    original_write = umrl_import._atomic_write
    def fail_pointer(path, payload):
        if path.name == "current.json":
            raise OSError("simulated interrupted write")
        original_write(path, payload)
    with monkeypatch.context() as patch:
        patch.setattr(umrl_import, "_atomic_write", fail_pointer)
        with pytest.raises(OSError):
            import_snapshot(incoming, store)
    assert load_umrl(store).revision_id == old
    assert load_umrl(store).get("TEST 1")["listed_edition_statement"] == "(2017)"
    report = import_snapshot(incoming, store)
    assert load_umrl(store).revision_id == report["to_revision_id"]
    assert not list(store.glob(".staging-*"))


def test_concurrent_writer_cannot_interleave_imports(workspace, tmp_path):
    store = tmp_path / "store"
    import_snapshot(prepare_import(workspace), store)
    previous = files(store)
    with umrl_import._import_lock(store):
        with pytest.raises(OSError):
            import_snapshot(update_catalog(workspace), store)
    assert files(store) == previous


def test_cache_refreshes_after_import_without_changing_existing_readers(workspace, tmp_path, monkeypatch):
    store = tmp_path / "store"
    import_snapshot(prepare_import(workspace), store)
    monkeypatch.setattr(umrl, "DATA", store)
    before = umrl.default_umrl()
    import_snapshot(update_catalog(workspace), store)
    after = umrl.default_umrl()
    assert after.revision_id != before.revision_id
    assert after.get("TEST 1")["listed_edition_statement"] == "(2026)"
    assert before.get("TEST 1")["listed_edition_statement"] == "(2017)"
    assert umrl.default_umrl(before.revision_id) is before


@pytest.mark.asyncio
async def test_extraction_pins_one_snapshot_when_import_finishes_mid_run(workspace, tmp_path, monkeypatch):
    store = tmp_path / "store"
    import_snapshot(prepare_import(workspace), store)
    monkeypatch.setattr(umrl, "DATA", store)
    old = umrl.default_umrl().revision_id
    incoming = update_catalog(workspace)
    source = parse_ufc(json_bytes({"criterion": {"designation": "UFC fixture", "versionId": "fixture"},
        "sections": [{"sentences": [{"text": "Apply TEST 1."}]}]}))
    class Provider:
        model = "test-model-no-network"
        async def structured(self, prompt, schema):
            import_snapshot(incoming, store)
            return {"reviewed_unit_ids": [source.units[0].unit_id], "entities": [{
                "unit_id": source.units[0].unit_id, "mention_exact": "TEST 1", "label_proposed": "TEST 1",
                "entity_type": "document", "entity_kind": "named_individual", "description_proposed": "",
                "definition_evidence": [], "scope_evidence": [], "confidence": 0.9}]}
    report = await extract_entities(source, Provider(), provider="fixture")
    assert report["umrl"]["revision_id"] == old
    assert report["umrl"]["entities"][0]["listed_edition_statement"] == "(2017)"
    assert umrl.default_umrl().revision_id != old


@pytest.mark.asyncio
async def test_api_history_selects_old_revisions_and_keeps_missing_ids_accessible(workspace, tmp_path, monkeypatch, client):
    store = tmp_path / "store"
    original = import_snapshot(prepare_import(workspace), store)
    import_snapshot(update_catalog(workspace), store)
    monkeypatch.setattr(umrl, "DATA", store)
    history = await client.get("/bco/umrl/history")
    assert history.status_code == 200 and len(history.json()["revisions"]) == 2
    assert history.json()["last_change_report"]["counts"]["changed"] == 1
    assert (await client.get("/bco/umrl/entity", params={"reference_id": "OLD 2"})).status_code == 404
    prior = await client.get("/bco/umrl/entity", params={"reference_id": "OLD 2", "revision": original["to_revision_id"]})
    assert prior.status_code == 200 and prior.json()["entity"]["entity_id"] == "OLD 2"
    assert (await client.get("/bco/umrl", params={"revision": "0" * 64})).status_code == 404
    assert (await client.get("/bco/umrl", params={"revision": "../manifest.json"})).status_code == 422


def test_cli_reimport_and_dry_run_require_no_model(workspace, tmp_path):
    root = Path(__file__).resolve().parents[2]
    store = tmp_path / "store"
    command = [sys.executable, str(root / "scripts/import_bco_umrl.py"), str(workspace), "--output", str(store)]
    result = subprocess.run(command + ["--dry-run"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "would_import" and not store.exists()
    assert subprocess.run(command, capture_output=True).returncode == 0
    assert json.loads(subprocess.check_output(command, text=True))["status"] == "unchanged"
    update_catalog(workspace)
    result = subprocess.run(command + ["--catalog-only", "--report", str(tmp_path / "changes.json")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads((tmp_path / "changes.json").read_text())["counts"]["changed"] == 1
