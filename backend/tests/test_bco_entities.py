"""Entity discovery contracts: source fidelity, bounded calls, and honest coverage."""
import asyncio
import json
from pathlib import Path
import subprocess
import sys

import pytest

from app.bco.entities import (EntityOptions, atomic_json, build_prompt, export_review_bundle,
                              extract_entities, plan_batches, plan_summary, validate_response)
from app.bco.source import parse_ufc, parse_ufgs


@pytest.fixture
def source_bytes():
    return json.dumps({"criterion": {"designation": "UFC 1-200-01", "versionId": "edition-1", "title": "Building Code"},
        "sections": [{"id": "node-1", "label": "1-1", "heading": "Roles", "sentences": [
            {"id": "s-1", "text": "Owner’s  Agent shall approve; Owner’s  Agent acts for leased facilities."},
            {"id": "s-2", "text": "The Owner’s  Agent is the designated representative."}]}]}).encode()


@pytest.fixture
def source(source_bytes):
    return parse_ufc(source_bytes)


def proposal(unit, text="Owner’s  Agent", **changes):
    return {"unit_id": unit.unit_id, "mention_exact": text, "label_proposed": "Owner's Agent",
            "entity_type": "responsibility_role", "entity_kind": "concept", "description_proposed": "A proposed role description.",
            "definition_evidence": [], "scope_evidence": [], "confidence": 0.8, **changes}


def response(batch, entities=()):
    return {"reviewed_unit_ids": batch["target_ids"], "entities": list(entities)}


class FakeProvider:
    model = "fixture-model"
    base_url = "https://model.invalid/v1"
    calls = 0

    async def structured(self, prompt, schema):
        self.calls += 1
        data = json.loads(prompt.split("\nSOURCE DATA:\n")[1])
        targets = [u for u in data["units"] if u["role"] == "target"]
        return {"reviewed_unit_ids": [u["unit_id"] for u in targets], "entities": []}


def test_plan_covers_every_unit_once_and_bounds_calls(source):
    options = EntityOptions(max_units=1, max_batches=2)
    batches = plan_batches(source, options)
    assert [i for b in batches for i in b["target_ids"]] == [u.unit_id for u in source.units]
    assert all(len(b["target_ids"]) <= 1 for b in batches)
    assert source.units[1].unit_id in batches[0]["context_ids"]
    plan = plan_summary(source, options)
    assert plan["units_selected"] == 2 and plan["batches_total"] == 3
    assert plan["maximum_application_attempts"] == 4 and plan["network_calls_made"] == 0
    prompt = build_prompt(source, batches[1])
    assert "Owner’s  Agent" in prompt and "untrusted evidence" in prompt
    assert "chapter" in prompt.lower() and "named individual" in prompt


def test_oversize_unit_fails_before_truncation(source_bytes):
    raw = json.loads(source_bytes)
    raw["sections"][0]["sentences"][0]["text"] = "x" * 501
    with pytest.raises(ValueError, match="exceeds max_characters"):
        plan_batches(parse_ufc(json.dumps(raw).encode()), EntityOptions(max_characters=500))


def test_unicode_repeated_mentions_scope_and_definition_roundtrip(source):
    batch = plan_batches(source, EntityOptions())[0]
    entity = proposal(source.units[1], scope_evidence=[{"unit_id": source.units[1].unit_id, "text_exact": "for leased facilities"}],
                      definition_evidence=[{"unit_id": source.units[2].unit_id, "text_exact": source.units[2].text}])
    rows, findings = validate_response(response(batch, [entity]), source, batch)
    assert not findings and len(rows) == 2
    assert rows[0]["candidate_id"] != rows[1]["candidate_id"]
    for row in rows:
        for span in [row["mention"], *row["scope_evidence"], *row["definition_evidence"]]:
            unit = next(u for u in source.units if u.unit_id == span["unit_id"])
            assert unit.text[span["start"]:span["end"]] == span["source_text_exact"]
        assert row["accepted_concept_id"] is None
        assert row["review_status"] == "candidate_pending_subject_matter_review"
        assert row["confidence_is_calibrated"] is False


@pytest.mark.parametrize("changes", [
    {"mention_exact": "Owner's Agent"}, {"unit_id": "invented-unit"},
    {"entity_type": "bankruptcy_role"}, {"confidence": float("nan")},
    {"confidence": 1.1}, {"status": "accepted"}, {"mention_exact": "  "},
    {"scope_evidence": [{"unit_id": "invented", "text_exact": "for leased"}]},
])
def test_hallucinations_and_invalid_fields_are_visible_findings(source, changes):
    batch = plan_batches(source, EntityOptions())[0]
    rows, findings = validate_response(response(batch, [proposal(source.units[1], **changes)]), source, batch)
    assert rows == [] and findings[0]["code"] == "invalid_entity_proposal"


def test_context_is_evidence_but_not_a_target(source):
    batch = plan_batches(source, EntityOptions(max_units=1))[0]
    rows, findings = validate_response(response(batch, [proposal(source.units[1])]), source, batch)
    assert not rows and findings


def test_omitted_or_duplicated_unit_acknowledgement_fails_batch(source):
    batch = plan_batches(source, EntityOptions())[0]
    for ids in [[], batch["target_ids"] * 2]:
        with pytest.raises(ValueError, match="exactly the requested"):
            validate_response({"reviewed_unit_ids": ids, "entities": []}, source, batch)


def test_senses_do_not_merge_across_units_profiles_or_versions(source, source_bytes):
    batch = plan_batches(source, EntityOptions())[0]
    rows, _ = validate_response(response(batch, [proposal(source.units[1]), proposal(source.units[2])]), source, batch)
    assert len({r["candidate_id"] for r in rows}) == 3
    profiled = parse_ufc(source_bytes, ["usace"])
    other, _ = validate_response(response(batch, [proposal(source.units[1])]), profiled, batch)
    assert not {r["candidate_id"] for r in rows} & {r["candidate_id"] for r in other}


def test_duplicate_proposals_are_flagged(source):
    batch = plan_batches(source, EntityOptions())[0]
    item = proposal(source.units[1])
    rows, findings = validate_response(response(batch, [item, {**item, "label_proposed": "Different role"}]), source, batch)
    assert len(rows) == 2 and len(findings) == 2
    assert all(f["code"] == "duplicate_entity_proposal" for f in findings)


def test_word_fragments_are_not_new_entity_mentions():
    source = parse_ufgs(b'<SECTION><SCN>01 10 00</SCN><TXT>Fireproofing is required.</TXT></SECTION>')
    batch = plan_batches(source, EntityOptions())[0]
    rows, findings = validate_response(response(batch, [proposal(source.units[-1], "Fire")]), source, batch)
    assert not rows and findings


def test_ufgs_guide_notes_remain_distinct():
    source = parse_ufgs(b'<SECTION><SCN>01 10 00</SCN><NTE><TXT>Choose Contractor.</TXT></NTE><TXT>Contractor shall comply.</TXT></SECTION>')
    batch = plan_batches(source, EntityOptions())[0]
    unit = next(u for u in source.units if u.kind == "guide_note")
    rows, _ = validate_response(response(batch, [proposal(unit, "Contractor")]), source, batch)
    assert rows[0]["source_unit_kind"] == "guide_note"
    assert rows[0]["project_applicability"] == "not_evaluated"


@pytest.mark.asyncio
async def test_resume_validates_cache_and_model_identity(source, tmp_path):
    llm = FakeProvider()
    report = await extract_entities(source, llm, provider="fixture", cache_dir=tmp_path)
    assert report["status"] == "completed" and report["entities"] == [] and llm.calls == 1
    again = await extract_entities(source, llm, provider="fixture", cache_dir=tmp_path)
    assert llm.calls == 1 and again["batches"][0]["cache_hit"] is True
    llm.model = "other-model"
    await extract_entities(source, llm, provider="fixture", cache_dir=tmp_path)
    assert llm.calls == 2
    cache = next(tmp_path.glob("*.json"))
    value = json.loads(cache.read_text())
    value["response"]["reviewed_unit_ids"] = []
    atomic_json(cache, value)
    llm.model = value["request"]["model"]
    report = await extract_entities(source, llm, provider="fixture", cache_dir=tmp_path)
    assert llm.calls == 3 and report["batches"][0]["findings"][0]["code"] == "invalid_cache_ignored"


@pytest.mark.asyncio
async def test_batch_limit_is_partial_not_complete(source):
    llm = FakeProvider()
    report = await extract_entities(source, llm, provider="fixture", options=EntityOptions(max_units=1, max_batches=1))
    assert report["status"] == "partial" and report["coverage"]["units_not_submitted"] == 2
    assert llm.calls == 1 and report["accepted_concept_count"] == 0


@pytest.mark.asyncio
async def test_calls_are_bounded_and_progress_is_recorded(source):
    class Concurrent(FakeProvider):
        active = 0
        peak = 0
        async def structured(self, *args, **kwargs):
            self.active += 1
            self.peak = max(self.peak, self.active)
            await asyncio.sleep(0.01)
            value = await super().structured(*args, **kwargs)
            self.active -= 1
            return value
    llm, progress = Concurrent(), []
    async def collect(batch):
        progress.append(batch)
    result = await extract_entities(source, llm, provider="fixture", options=EntityOptions(max_units=1, concurrency=2), progress=collect)
    assert result["status"] == "completed" and llm.peak == 2 and len(progress) == 3


@pytest.mark.asyncio
async def test_failure_not_empty_success_and_errors_never_expose_secrets(source):
    class Broken(FakeProvider):
        async def structured(self, *args, **kwargs):
            self.calls += 1
            raise RuntimeError("Authorization Bearer PRIVATE-KEY-MUST-NOT-LEAK")
    report = await extract_entities(source, Broken(), provider="fixture")
    assert report["status"] == "failed" and report["coverage"]["units_with_valid_response"] == 0
    assert report["batches"][0]["findings"][0]["error_type"] == "RuntimeError"
    assert "PRIVATE-KEY" not in json.dumps(report)


@pytest.mark.asyncio
async def test_timeout_is_a_failed_batch_with_no_unbounded_retry(source):
    class Slow(FakeProvider):
        async def structured(self, *args, **kwargs):
            self.calls += 1
            await asyncio.sleep(10)
    llm = Slow()
    result = await extract_entities(source, llm, provider="fixture", options=EntityOptions(timeout_seconds=1, attempts=1))
    assert result["status"] == "failed" and llm.calls == 1
    assert result["batches"][0]["findings"][0]["error_type"] == "TimeoutError"


@pytest.mark.asyncio
async def test_transient_retry_then_success(source, monkeypatch):
    class RateLimit(Exception):
        status_code = 429
    class Retried(FakeProvider):
        tries = 0
        async def structured(self, *args, **kwargs):
            self.tries += 1
            if self.tries == 1:
                raise RateLimit()
            return await super().structured(*args, **kwargs)
    async def no_sleep(_):
        pass
    monkeypatch.setattr("app.bco.entities.asyncio.sleep", no_sleep)
    result = await extract_entities(source, Retried(), provider="fixture")
    assert result["status"] == "completed" and result["batches"][0]["attempts"] == 2


@pytest.mark.asyncio
async def test_valid_candidates_survive_invalid_peer_and_export_is_immutable(source, tmp_path):
    class Proposing(FakeProvider):
        async def structured(self, prompt, schema):
            value = await super().structured(prompt, schema)
            value["entities"] = [proposal(source.units[1]), proposal(source.units[2], "invented role")]
            return value
    report = await extract_entities(source, Proposing(), provider="fixture")
    assert report["status"] == "partial" and len(report["entities"]) == 2
    destination = tmp_path / "collection"
    export_review_bundle(report, destination)
    candidates = json.loads((destination / "pilot-ledger.json").read_text())
    units = json.loads((destination / "source-units.json").read_text())
    for candidate in candidates:
        assert candidate["record_type"] == "llm_entity_candidate"
        for e in candidate["evidence"] + candidate["label_evidence"]:
            assert units[e["unit_id"]]["text_exact"][e["start"]:e["end"]] == e["source_text_exact"]
    with pytest.raises(FileExistsError):
        export_review_bundle(report, destination)


@pytest.mark.asyncio
async def test_bad_partial_cache_is_retried_and_cache_failure_keeps_results(source, tmp_path, monkeypatch):
    class Correctable(FakeProvider):
        valid = False
        async def structured(self, *args, **kwargs):
            value = await super().structured(*args, **kwargs)
            if not self.valid:
                value["entities"] = [proposal(source.units[1], "fabricated")]
            return value
    llm = Correctable()
    result = await extract_entities(source, llm, provider="fixture", cache_dir=tmp_path)
    assert result["status"] == "partial"
    llm.valid = True
    result = await extract_entities(source, llm, provider="fixture", cache_dir=tmp_path)
    assert result["status"] == "completed" and llm.calls == 2
    def fail_write(*args):
        raise OSError("No space")
    monkeypatch.setattr("app.bco.entities.atomic_json", fail_write)
    result = await extract_entities(source, llm, provider="fixture", cache_dir=tmp_path / "unwritable")
    assert result["status"] == "completed"
    assert result["batches"][0]["findings"][0]["code"] == "cache_write_failed"


@pytest.mark.asyncio
async def test_provider_and_model_are_required(source):
    with pytest.raises(ValueError, match="explicitly configured"):
        await extract_entities(source, None, provider="openai")


def test_provider_key_policy_and_model_requirement(monkeypatch):
    from app.bco.entity_provider import entity_provider
    from app.config import settings
    monkeypatch.setattr(settings, "llm_model", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "require_user_api_key", True)
    monkeypatch.setenv("OPENAI_API_KEY", "not-for-a-public-request")
    with pytest.raises(ValueError, match="explicit model"):
        entity_provider("openai")
    with pytest.raises(ValueError, match="API key locally"):
        entity_provider("openai", "test-model")


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["completed", "incomplete", "refusal"])
async def test_openai_sdk_uses_strict_schema_no_storage_and_surfaces_failures(source, outcome):
    openai = pytest.importorskip("openai")
    httpx = pytest.importorskip("httpx2")
    from app.bco.openai_entities import OpenAIEntityProvider
    requests = []
    batch = plan_batches(source, EntityOptions())[0]
    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.url.path == "/v1/responses"
        assert body["store"] is False and body["text"]["format"]["strict"] is True
        assert body["text"]["format"]["schema"]["additionalProperties"] is False
        part = {"type": "refusal", "refusal": "Fixture refusal"} if outcome == "refusal" else {"type": "output_text", "text": json.dumps(response(batch)), "annotations": []}
        return httpx.Response(200, json={"id": "resp_fixture", "object": "response", "created_at": 1,
            "model": "fixture-model", "status": "incomplete" if outcome == "incomplete" else "completed",
            "output": [{"id": "msg_fixture", "type": "message", "role": "assistant", "status": "completed", "content": [part]}]})
    llm = OpenAIEntityProvider(api_key="test-only", model="fixture-model", base_url="https://model.invalid/v1")
    llm._client = openai.AsyncOpenAI(api_key="test-only", base_url=llm.base_url, max_retries=0,
                                    http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    report = await extract_entities(source, llm, provider="openai")
    assert len(requests) == 1
    assert report["status"] == ("completed" if outcome == "completed" else "failed")
    from app.bco.entity_provider import close_entity_provider
    await close_entity_provider(llm)
    assert llm._client.is_closed()


def test_cli_plan_needs_no_api_key(source_bytes, tmp_path):
    root = Path(__file__).resolve().parents[2]
    path = tmp_path / "source.json"
    path.write_bytes(source_bytes)
    result = subprocess.run([sys.executable, str(root / "scripts/extract_bco_entities.py"), str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["network_calls_made"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_close", [False, True])
async def test_entity_api_plan_and_job_use_same_engine(client, monkeypatch, job_store, source_bytes, caplog, fail_close):
    import base64
    from app.api.routes import enrich
    from app.bco import entity_provider as provider_module
    monkeypatch.setattr(enrich, "_job_store", job_store)
    class ClosingProvider(FakeProvider):
        close_calls = 0

        async def aclose(self):
            self.close_calls += 1
            if fail_close:
                raise OSError("fixture-secret-must-not-be-logged")
    fake = ClosingProvider()
    monkeypatch.setattr(provider_module, "entity_provider", lambda *a: ("fixture", fake))
    payload = {"content_base64": base64.b64encode(source_bytes).decode(), "source_format": "ufc_json", "llm_model": "fixture-model"}
    plan = await client.post("/bco/entities/plan", json=payload)
    assert plan.status_code == 200 and fake.calls == 0
    started = await client.post("/bco/entities", json=payload)
    assert started.status_code == 202, started.text
    for _ in range(100):
        result = await client.get(started.json()["status_url"])
        if result.json()["status"] in {"failed", "completed"}:
            break
        await asyncio.sleep(0.01)
    assert result.json()["status"] == "completed"
    report = await client.get(started.json()["entities_url"])
    assert report.status_code == 200 and report.json()["accepted_concept_count"] == 0
    assert fake.close_calls == 1
    assert "fixture-secret-must-not-be-logged" not in caplog.text
    rejected = await client.post("/bco/entities", json={**payload, "use_llm": False})
    assert rejected.status_code == 422
