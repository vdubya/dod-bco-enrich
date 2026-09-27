"""Official UFC master glossary: scoped evidence and repeatable source imports."""
import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
import pytest

from app.bco import glossary, glossary_import
from app.bco.entities import EntityOptions, plan_batches, validate_response
from app.bco.glossary import index_pdf, load_glossary, read_snapshot, source_bundle
from app.bco.glossary_import import import_pdf
from app.bco.source import parse_source


def fixture_pdf(*, changed=False, mismatch=False, unscoped=False, many_pages=1, remove_second=False):
    """Minimal text PDF with the same two-level publisher outline contract."""
    writer = PdfWriter()
    writer.add_metadata({"/Title": "Fixture UFC glossary", "/ModDate": "D:20260927000000Z"})
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    font_ref = writer._add_object(font)

    def page(text):
        current = writer.add_blank_page(width=612, height=792)
        current[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})})
        stream = DecodedStreamObject()
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.set_data(f"BT /F1 10 Tf 40 750 Td ({escaped}) Tj ET".encode())
        current[NameObject("/Contents")] = writer._add_object(stream)

    for designation in (["UFC 1-200-01"] if remove_second else ["UFC 1-200-01", "UFC 3-130-01"]):
        first = len(writer.pages)
        page(f"APPENDIX A {designation} GLOSSARY\nOwner: The {'revised ' if changed and first == 0 else ''}designated official for {designation}.")
        for i in range(1, many_pages):
            page(f"More glossary text on page {i + 1}. " + "x" * 380)
        reference_page = len(writer.pages)
        page(f"APPENDIX B {designation} REFERENCES\nASTM TEST 1 (2024). Use the edition required by {designation}.")
        if not unscoped:
            parent = writer.add_outline_item(designation, first)
            writer.add_outline_item(f"APPENDIX A {designation} {'references' if mismatch else 'GLOSSARY'}", first, parent=parent)
            writer.add_outline_item(f"APPENDIX B {designation} REFERENCES", reference_page, parent=parent)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


ACQUISITION = {"method": "local_file", "filename": "fixture.pdf", "remote_origin_verified": False}


def saved_files(path):
    return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob("*") if p.is_file()}


def test_index_keeps_scope_source_bytes_and_exact_page_text():
    payload = fixture_pdf()
    index = index_pdf(payload)
    assert index["source_sha256"] == hashlib.sha256(payload).hexdigest()
    assert index["summary"] == {"pdf_pages": 4, "ufc_contexts": 2,
        "sections_by_kind": {"glossary": 2, "references": 2},
        "pages_without_extracted_text": [], "structure_findings": 0}
    assert index["extraction"]["semantic_entity_extraction"] == "not_performed"
    assert "not_inferred" in index["source_edition"]
    bundle = source_bundle(index, payload)
    for unit, page in zip(bundle.units, index["pages"]):
        assert bundle.text[unit.start:unit.end] == unit.text == page["text_exact"]
        assert unit.section_path[0] == page["designation"]
        assert unit.source_node_id == page["page_id"]
        assert unit.container_id == page["section_id"]
        assert unit.locator == f"pdf:page:{page['pdf_page']}:text"
    assert bundle.units[0].unit_id != bundle.units[2].unit_id


def test_printed_heading_wins_over_erroneous_bookmark_without_erasing_it():
    index = index_pdf(fixture_pdf(mismatch=True))
    assert index["pages"][0]["kind"] == "glossary"
    assert len(index["findings"]) == 2
    assert index["findings"][0]["classification_basis"] == "printed_heading"
    assert index["findings"][0]["bookmark_title_exact"].endswith("references")


@pytest.mark.parametrize("payload", [b"<html>blocked</html>", fixture_pdf(unscoped=True)])
def test_rejects_non_pdf_or_missing_scope_structure(payload):
    with pytest.raises(ValueError):
        index_pdf(payload)


def test_scoped_parse_keeps_ids_and_rejects_bad_selection():
    payload = fixture_pdf()
    complete = parse_source(payload, "ufc_glossary_pdf")
    selected = parse_source(payload, "ufc_glossary_pdf", source_designation="UFC 3-130-01", source_section_kind="glossary")
    assert len(selected.units) == 1 and selected.units[0].unit_id == complete.units[2].unit_id
    assert selected.coverage["selected_pdf_pages"] == [3]
    with pytest.raises(ValueError, match="absent"):
        parse_source(payload, "ufc_glossary_pdf", source_designation="UFC 9-999-99")
    with pytest.raises(ValueError, match="Unknown"):
        parse_source(payload, "ufc_glossary_pdf", source_section_kind="invented")
    with pytest.raises(ValueError):
        parse_source(b"{}", "ufc_json", source_designation="UFC 3-130-01")


def test_batches_and_citations_cannot_cross_ufc_or_section_scope():
    bundle = parse_source(fixture_pdf(), "ufc_glossary_pdf")
    batches = plan_batches(bundle, EntityOptions())
    assert len(batches) == 4
    assert all(len(b["target_ids"]) == 1 and not b["context_ids"] for b in batches)
    proposal = {"unit_id": bundle.units[0].unit_id, "mention_exact": "Owner", "label_proposed": "Owner",
        "entity_type": "responsibility_role", "entity_kind": "concept", "description_proposed": "A role",
        "definition_evidence": [{"unit_id": bundle.units[2].unit_id, "text_exact": "Owner"}],
        "scope_evidence": [], "confidence": 0.8}
    rows, findings = validate_response({"reviewed_unit_ids": batches[0]["target_ids"], "entities": [proposal]}, bundle, batches[0])
    assert not rows and findings[0]["code"] == "invalid_entity_proposal"
    proposal["definition_evidence"][0] = {"unit_id": bundle.units[0].unit_id, "text_exact": "Owner: The designated official for UFC 1-200-01."}
    rows, findings = validate_response({"reviewed_unit_ids": batches[0]["target_ids"], "entities": [proposal]}, bundle, batches[0])
    assert len(rows) == 1 and not findings
    assert rows[0]["accepted_concept_id"] is None


def test_adjacent_page_context_preferred_within_same_appendix():
    bundle = parse_source(fixture_pdf(many_pages=16), "ufc_glossary_pdf")
    batches = plan_batches(bundle, EntityOptions(max_units=1, max_characters=500))
    assert batches[14]["context_ids"][0] == bundle.units[13].unit_id
    assert batches[14]["context_characters"] <= 500
    containers = {u.unit_id: u.container_id for u in bundle.units}
    assert all(len({containers[k] for k in b["target_ids"] + b["context_ids"]}) == 1 for b in batches)


def test_repeat_import_is_noop_and_dry_run_writes_nothing(tmp_path):
    store, payload = tmp_path / "store", fixture_pdf()
    assert import_pdf(payload, store, acquisition=ACQUISITION, dry_run=True)["status"] == "would_import"
    assert not store.exists()
    imported = import_pdf(payload, store, acquisition=ACQUISITION)
    saved = saved_files(store)
    assert import_pdf(payload, store, acquisition={**ACQUISITION, "another_retrieval": True})["status"] == "unchanged"
    assert saved_files(store) == saved
    planned = import_pdf(fixture_pdf(changed=True), store, acquisition=ACQUISITION, dry_run=True)
    assert planned["counts"] == {"added": 0, "changed": 1, "absent_from_new_snapshot": 0, "unchanged": 3}
    assert planned["from_source_sha256"] == imported["to_source_sha256"]
    assert saved_files(store) == saved


def test_new_snapshot_retains_prior_source_and_refreshes_live_reader(tmp_path, monkeypatch):
    monkeypatch.setattr(glossary, "DATA", tmp_path)
    payload = fixture_pdf()
    first = import_pdf(payload, tmp_path, acquisition=ACQUISITION)["to_source_sha256"]
    old_manifest, old_index = load_glossary()
    report = import_pdf(fixture_pdf(changed=True, remove_second=True), tmp_path, acquisition=ACQUISITION)
    manifest, current = load_glossary()
    assert current["source_sha256"] != old_index["source_sha256"]
    assert load_glossary(first) == (old_manifest, old_index)
    assert report["counts"] == {"added": 0, "changed": 1, "absent_from_new_snapshot": 2, "unchanged": 1}
    assert report["absent_does_not_mean_withdrawn"] and not report["review_decisions_modified"]
    assert (tmp_path / "snapshots" / first / "source.pdf").read_bytes() == payload
    assert len(list((tmp_path / "snapshots").iterdir())) == 2
    assert manifest["source_sha256"] == current["source_sha256"]


def test_invalid_new_source_cannot_replace_active_snapshot(tmp_path):
    import_pdf(fixture_pdf(), tmp_path, acquisition=ACQUISITION)
    saved = saved_files(tmp_path)
    with pytest.raises(ValueError):
        import_pdf(fixture_pdf(unscoped=True), tmp_path, acquisition=ACQUISITION)
    assert saved_files(tmp_path) == saved


def test_same_pdf_reuses_pinned_index_after_parser_upgrade(tmp_path, monkeypatch):
    payload = fixture_pdf()
    import_pdf(payload, tmp_path, acquisition=ACQUISITION)
    before = saved_files(tmp_path)
    def forbidden(*args):
        raise AssertionError("An immutable indexed snapshot must not be reparsed")
    monkeypatch.setattr(glossary_import, "index_pdf", forbidden)
    assert import_pdf(payload, tmp_path, acquisition=ACQUISITION)["status"] == "unchanged"
    assert saved_files(tmp_path) == before


@pytest.mark.parametrize("name", ["source.pdf", "page-index.json"])
def test_corrupted_snapshot_cannot_be_reused(tmp_path, name):
    payload = fixture_pdf()
    revision = import_pdf(payload, tmp_path, acquisition=ACQUISITION)["to_source_sha256"]
    path = tmp_path / "snapshots" / revision / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        import_pdf(payload, tmp_path, acquisition=ACQUISITION)


def test_interrupted_activation_keeps_old_pointer_and_retry_completes(tmp_path, monkeypatch):
    old = import_pdf(fixture_pdf(), tmp_path, acquisition=ACQUISITION)["to_source_sha256"]
    incoming = fixture_pdf(changed=True)
    original_write = glossary_import._atomic_write
    def fail_pointer(path, payload):
        if path.name == "current.json":
            raise OSError("simulated interrupted activation")
        original_write(path, payload)
    with monkeypatch.context() as patch:
        patch.setattr(glossary_import, "_atomic_write", fail_pointer)
        with pytest.raises(OSError):
            import_pdf(incoming, tmp_path, acquisition=ACQUISITION)
    assert json.loads((tmp_path / "current.json").read_bytes())["source_sha256"] == old
    retry = import_pdf(incoming, tmp_path, acquisition=ACQUISITION)
    assert retry["status"] == "imported"
    assert retry["to_source_sha256"] != old


async def test_api_search_revision_and_no_call_plan(client, tmp_path, monkeypatch):
    monkeypatch.setattr(glossary, "DATA", tmp_path)
    payload = fixture_pdf()
    original = import_pdf(payload, tmp_path, acquisition=ACQUISITION)["to_source_sha256"]
    response = await client.get("/bco/glossary", params={"q": "Owner", "designation": "UFC 1-200-01", "kind": "glossary"})
    assert response.status_code == 200
    assert response.json()["total_pages_matched"] == 1
    assert response.json()["pages"][0]["pdf_page"] == 1
    import_pdf(fixture_pdf(changed=True), tmp_path, acquisition=ACQUISITION)
    historical = await client.get("/bco/glossary", params={"revision": original})
    assert historical.json()["source"]["source_sha256"] == original
    assert (await client.get("/bco/glossary", params={"revision": "f" * 64})).status_code == 404
    response = await client.post("/bco/entities/plan", json={"content_base64": base64.b64encode(payload).decode(),
        "source_format": "ufc_glossary_pdf", "source_designation": "UFC 1-200-01", "source_section_kind": "glossary"})
    assert response.status_code == 200, response.text
    assert response.json()["source_units"] == 1 and response.json()["network_calls_made"] == 0


def test_cli_auto_detects_pdf_and_plans_selected_scope(tmp_path):
    path = tmp_path / "fixture.pdf"
    path.write_bytes(fixture_pdf())
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, str(root / "scripts/extract_bco_entities.py"), str(path),
        "--source-designation", "UFC 3-130-01", "--source-section-kind", "references"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["network_calls_made"] == 0 and plan["source_units"] == 1
    assert plan["source"]["coverage"]["selected_pdf_pages"] == [4]


def test_archived_official_source_integrity_and_known_scope_boundaries():
    store = Path(glossary.__file__).with_name("data") / "ufc-glossary"
    revision = "db8e5e076be7dbc08ceadbe25544e69756961ff2c8767869e98d4bb5dbc341c9"
    manifest, index = read_snapshot(store / "snapshots" / revision, revision)
    assert manifest["acquisition"]["method"] == "download_official_url"
    assert index["summary"]["pdf_pages"] == 481 and index["summary"]["ufc_contexts"] == 52
    assert index["summary"]["sections_by_kind"] == {"glossary": 52, "references": 52, "supplemental_resources": 2}
    assert {f["pdf_page"] for f in index["findings"]} == {55, 123, 158, 161, 399}
    assert index["pages"][398]["designation"] == "UFC 3-600-01"
    assert index["pages"][398]["kind"] == "glossary"
    assert "Critical Asset" in index["pages"][4]["text_exact"]
    assert "2024" in index["pages"][5]["text_exact"]
    for page in index["pages"]:
        assert hashlib.sha256(page["text_exact"].encode()).hexdigest() == page["text_sha256"]
        assert page["source_url"].endswith(f"#page={page['pdf_page']}")
