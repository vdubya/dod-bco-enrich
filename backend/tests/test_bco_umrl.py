"""Reuse contracts: existing identities, evidence, ambiguity, and LLM links."""
import json
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from app.bco.entities import extract_entities, export_review_bundle, plan_summary, EntityOptions
from app.bco.source import parse_ufc
from app.bco import umrl
from app.bco.umrl import ARTIFACTS, DATA, UMRLCatalog, default_umrl, load_umrl


@pytest.fixture(autouse=True)
def pinned_original_snapshot(tmp_path, monkeypatch):
    # These are May 2026 regression fixtures, independent of later active imports.
    directory = tmp_path / "original-umrl"
    directory.mkdir()
    for name in ARTIFACTS:
        shutil.copyfile(DATA / name, directory / name)
    monkeypatch.setattr(umrl, "DATA", directory)


def inputs():
    return [json.loads((DATA / name).read_text())
            for name in ("umrl-viewer.json", "prior-analyses.json", "manifest.json")]


def test_all_existing_viewer_records_and_original_matches_survive():
    viewer, analyses, _ = inputs()
    catalog = default_umrl()
    assert catalog.summary == {"publications": 4972, "organizations": 304, "processed_documents": 2,
        "prior_matches": 31, "used_publications": 18, "legacy_graph_id_collisions": 1,
        "accepted_ontology_concepts": 0, "new_extraction_calls": 0}
    for original in viewer["records"]:
        entity = catalog.get(original["reference_id"])
        assert entity["entity_id"] == original["reference_id"]
        assert all(entity[key] == value for key, value in original.items())
        assert entity["accepted_concept_id"] is None
    joined = {m["match_id"]: m for r in catalog.records.values() for m in r["prior_matches"]}
    for document in analyses:
        for match in document["analysis"]["matches"]:
            assert all(joined[match["match_id"]][key] == value for key, value in match.items())


def test_collision_never_merges_reference_ids():
    catalog = default_umrl()
    for rid in ("PL-109-58", "PL 109-58"):
        assert catalog.get(rid)["legacy_graph_id_is_ambiguous"] is True
        assert catalog.resolve_candidate(rid)["entity_id"] == rid
    result = catalog.resolve_candidate("pl 109 58")
    assert result["entity_id"] is None
    assert set(result["candidate_entity_ids"]) == {"PL-109-58", "PL 109-58"}
    assert result["resolution_status"] == "needs_review"


def test_catalog_edition_is_not_the_adopted_or_cited_edition():
    catalog = default_umrl()
    publication = catalog.get("ASCE 7")
    assert publication["listed_edition_statement"] == "(2017)"
    assert catalog.resolve_candidate("ASCE 7")["cited_edition"] is None
    assert publication["project_applicability"] == "not_evaluated"
    assert publication["prior_matches"][0]["match_basis"] == "reference_id_alias"
    assert catalog.resolve_candidate("IBC")["resolution_status"] == "unresolved"
    assert catalog.resolve_candidate("ASCE  7")["resolution_status"] == "needs_review"
    assert catalog.get("ASHRAE 90.1 - IP")["prior_matches"][0]["review_status"] == "needs_review"


def test_search_is_paginated_and_cannot_mutate_the_pinned_inventory():
    catalog = default_umrl()
    page = catalog.search("forensic schedule")
    assert page["entities"][0]["entity_id"] == "AACE 29R-03"
    page["entities"][0]["reference_title"] = "Changed by caller"
    assert catalog.get("AACE 29R-03")["reference_title"].startswith("(2011)")
    first, second = catalog.search(limit=7), catalog.search(offset=7, limit=7)
    assert not {r["entity_id"] for r in first["entities"]} & {r["entity_id"] for r in second["entities"]}
    assert catalog.search(offset=4972)["entities"] == []
    assert catalog.search("unmatched-fixture")['total_matches'] == 0


@pytest.mark.parametrize("offset,limit", [(-1, 20), (0, 0), (0, 201)])
def test_bad_pagination_is_rejected(offset, limit):
    with pytest.raises(ValueError):
        default_umrl().search(offset=offset, limit=limit)


def test_mismatched_artifact_hash_is_rejected(tmp_path):
    for name in ARTIFACTS:
        shutil.copyfile(DATA / name, tmp_path / name)
    with (tmp_path / "umrl-viewer.json").open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="pinned manifest"):
        load_umrl(tmp_path)


@pytest.mark.parametrize("alteration", ["count", "identity", "status", "anchor", "title"])
def test_broken_joins_fail_instead_of_erasing_or_relabeling_old_evidence(alteration):
    viewer, analyses, manifest = inputs()
    if alteration == "count":
        viewer["match_count"] += 1
    elif alteration == "identity":
        viewer["records"][1]["reference_id"] = viewer["records"][0]["reference_id"]
    else:
        field = {"status": "review_status", "anchor": "source_anchor", "title": "reference_title"}[alteration]
        analyses[0]["analysis"]["matches"][0][field] = "incorrect fixture value"
    with pytest.raises(ValueError):
        UMRLCatalog(viewer, analyses, manifest)


def test_identity_is_stable_when_catalog_snapshot_changes():
    viewer, analyses, manifest = inputs()
    before = UMRLCatalog(viewer, analyses, manifest)
    manifest["snapshot_id"] = "umrl-catalog:next-snapshot"
    after = UMRLCatalog(viewer, analyses, manifest)
    assert before.get("ASCE 7")["entity_id"] == after.get("ASCE 7")["entity_id"]
    assert before.get("ASCE 7")["catalog_entry_id"] != after.get("ASCE 7")["catalog_entry_id"]


def test_same_acronym_does_not_merge_different_organizations():
    viewer, analyses, manifest = inputs()
    viewer["records"][0]["organization_acronyms"] = ["SHARED"]
    viewer["records"][10]["organization_acronyms"] = ["SHARED"]
    assert viewer["records"][0]["organization"] != viewer["records"][10]["organization"]
    catalog = UMRLCatalog(viewer, analyses, manifest)
    assert catalog.summary["organizations"] == 304
    assert catalog.get(viewer["records"][0]["reference_id"])["organization_id"] != catalog.get(viewer["records"][10]["reference_id"])["organization_id"]


@pytest.mark.asyncio
async def test_llm_results_link_only_validated_mentions_and_keep_review_state(tmp_path):
    source = parse_ufc(json.dumps({"criterion": {"designation": "UFC fixture", "versionId": "fixture"},
        "sections": [{"id": "node", "sentences": [{"text": "Use ASCE 7 and ASTM Z9999; retain ASCE 7."}]}]}).encode())
    class Provider:
        model = "fixture-no-network"
        async def structured(self, prompt, schema):
            return {"reviewed_unit_ids": [source.units[0].unit_id], "entities": [
                {"unit_id": source.units[0].unit_id, "mention_exact": text, "label_proposed": text,
                 "entity_type": "document", "entity_kind": "named_individual", "description_proposed": "",
                 "definition_evidence": [], "scope_evidence": [], "confidence": 0.8}
                for text in ("ASCE 7", "ASTM Z9999", "invented source words")]}
    report = await extract_entities(source, Provider(), provider="fixture")
    assert report["status"] == "partial" and len(report["entities"]) == 3
    assert [e["entity_id"] for e in report["umrl"]["entities"]] == ["ASCE 7"]
    for entity in report["entities"]:
        assert entity["accepted_concept_id"] is None
        mention = entity["mention"]
        assert source.units[0].text[mention["start"]:mention["end"]] == mention["source_text_exact"]
        link = entity["umrl_reference"]
        assert link["cited_edition"] is None
        assert link["entity_id"] == ("ASCE 7" if mention["source_text_exact"] == "ASCE 7" else None)
    export_review_bundle(report, tmp_path / "review")
    exported = json.loads((tmp_path / "review/extraction-report.json").read_text())
    assert exported["umrl"] == report["umrl"]
    assert plan_summary(source, EntityOptions())["umrl"]["summary"]["publications"] == 4972


@pytest.mark.asyncio
async def test_catalog_api_handles_slashes_and_requires_no_model(client):
    result = await client.get("/bco/umrl", params={"q": "ASTM", "limit": 2})
    assert result.status_code == 200 and len(result.json()["entities"]) == 2
    result = await client.get("/bco/umrl/entity", params={"reference_id": "ASTM D1970/D1970M"})
    assert result.status_code == 200
    assert result.json()["entity"]["entity_id"] == "ASTM D1970/D1970M"
    assert (await client.get("/bco/umrl/entity", params={"reference_id": "unknown"})).status_code == 404
    assert (await client.get("/bco/umrl", params={"limit": 201})).status_code == 422


def test_export_is_standalone_and_does_not_overwrite(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/export_bco_umrl.py"
    revision = hashlib.sha256((DATA / "manifest.json").read_bytes()).hexdigest()
    command = [sys.executable, str(script), "--revision", revision, "--output", str(tmp_path / "entities.json")]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    data = json.loads((tmp_path / "entities.json").read_text())
    assert len(data["entities"]) == 4972 and len(data["organizations"]) == 304
    assert subprocess.run(command, capture_output=True).returncode != 0
