"""BCO's domain boundary and evidence invariants, using real local ontology rules."""
import base64
import hashlib
import json
from pathlib import Path

import pytest

from app.bco import BASE_IRI
from app.bco.evidence import annotate_evidence
from app.bco.normalization import exact_canonical
from app.bco.source import parse_ufc, parse_ufgs
from app.models.annotation import Annotation, ConceptMatch, Span
from app.models.document import DocumentInput, DocumentFormat
from app.models.job import Job, JobStatus
from app.services.folio.folio_service import FolioService
from app.services.ontology.spec import BCO_SPEC


@pytest.fixture
def ufc_bytes():
    return json.dumps({"criterion": {"designation": "UFC TEST", "versionId": "v1", "versionNumber": "2026-09-26"},
        "sections": [{"id": "node1", "heading": "Owner", "label": "1-2", "sentences": [
            {"id": "sentence1", "text": "For leased facilities, the Owner  shall obtain approval unless exempt.\nRetain this condition."}], "children": []}]}).encode()


@pytest.fixture
def bundle(ufc_bytes):
    return parse_ufc(ufc_bytes)


def job_for(bundle):
    job = Job(input=DocumentInput(content=bundle.text, format=DocumentFormat.PLAIN_TEXT, ontology="dod-bco", bco_source=bundle))
    job.result.canonical_text = exact_canonical(bundle.text, DocumentFormat.PLAIN_TEXT)
    return job


def test_ufc_round_trips_json_fields_and_edition(bundle, ufc_bytes):
    original = json.loads(ufc_bytes)
    assert bundle.source_sha256 == hashlib.sha256(ufc_bytes).hexdigest()
    assert bundle.version_id == "v1"
    for unit in bundle.units:
        value = original
        for token in unit.locator.strip("/").split("/"):
            value = value[int(token)] if isinstance(value, list) else value[token]
        assert value == unit.text == bundle.text[unit.start:unit.end]
    assert bundle.units[-1].source_sentence_id == "sentence1"
    assert "Owner  shall" in bundle.text


@pytest.mark.parametrize("profiles", [[], ["not-a-profile"]])
def test_rejects_unsupported_profiles(ufc_bytes, profiles):
    with pytest.raises(ValueError):
        parse_ufc(ufc_bytes, profiles)


def test_sec_preserves_inline_text_and_guide_note_context():
    payload = b'<SECTION><SCN>01 10 00</SCN><STL>Summary</STL><NTE><TXT>Choose <OPT>one</OPT> option.</TXT></NTE><PRT ID="1"><TXT>The Contractor shall comply.</TXT></PRT></SECTION>'
    source = parse_ufgs(payload)
    note = next(unit for unit in source.units if unit.kind == "guide_note")
    assert note.text == "Choose one option."
    assert note.locator == "/SECTION/NTE::itertext"
    assert source.text.count("Choose one option.") == 1
    assert source.coverage["guide_specification_is_not_an_adopted_project_requirement"]
    assert source.units[-1].markup_context[-2]["attributes"] == {"ID": "1"}


@pytest.mark.parametrize("payload", [b'<SECTION><SCN>01 10 00</SCN>', b'<!DOCTYPE x [<!ENTITY x SYSTEM "file:///etc/passwd">]><SECTION><SCN>&x;</SCN></SECTION>', b' ' * 9000 + b'<!DOCTYPE SECTION><SECTION><SCN>01 10 00</SCN></SECTION>'])
def test_sec_rejects_malformed_and_doctype(payload):
    from lxml.etree import XMLSyntaxError
    with pytest.raises((ValueError, XMLSyntaxError)):
        parse_ufgs(payload)


def test_chunking_preserves_every_character(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "max_chunk_chars", 256)
    monkeypatch.setattr(settings, "chunk_overlap_chars", 30)
    text = ("\tOwner’s  role\r\n\nshall  remain scoped.\n" * 50)
    canonical = exact_canonical(text, DocumentFormat.PLAIN_TEXT)
    assert canonical.full_text == text
    covered = set()
    for chunk in canonical.chunks:
        assert chunk.text == text[chunk.start_offset:chunk.end_offset]
        covered.update(range(chunk.start_offset, chunk.end_offset))
    assert covered == set(range(len(text)))


def test_scoped_candidate_evidence_is_not_approval(bundle, ufc_bytes):
    job = job_for(bundle)
    job.result.annotations = [Annotation(span=Span(start=0, end=5, text="Owner"), concepts=[ConceptMatch(concept_text="Owner", folio_iri=BASE_IRI + "Owner", state="confirmed")])]
    annotate_evidence(job)
    evidence = job.result.metadata["bco_evidence"]
    row = evidence["records"][0]
    assert row["source_anchored"]
    assert row["accepted_concept_id"] is None
    assert row["global_equivalence_asserted"] is False
    assert {cue["text_exact"] for cue in row["scope_cues"]} >= {"For leased", "shall", "unless"}
    assert evidence["accepted_concept_count"] == 0

    other = job_for(parse_ufc(ufc_bytes, ["usace-re"]))
    other.result.annotations = job.result.annotations
    annotate_evidence(other)
    assert row["candidate_sense_id"] != other.result.metadata["bco_evidence"]["records"][0]["candidate_sense_id"]


def test_invalid_offsets_are_findings_not_valid_evidence(bundle):
    job = job_for(bundle)
    job.result.annotations = [Annotation(span=Span(start=0, end=5, text="wrong"))]
    annotate_evidence(job)
    evidence = job.result.metadata["bco_evidence"]
    assert not evidence["records"]
    assert evidence["findings"][0]["kind"] == "invalid_source_span"
    job.result.canonical_text.full_text += "changed"
    with pytest.raises(ValueError, match="changed"):
        annotate_evidence(job)


def test_bundled_ontology_is_offline_and_has_no_legal_branches(monkeypatch, tmp_path):
    import requests
    def no_network(*args, **kwargs):
        raise AssertionError("Bundled OWL must not fetch over HTTP")
    monkeypatch.setattr(requests.sessions.Session, "request", no_network)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    service = FolioService(BCO_SPEC)
    branches = {branch["name"] for branch in service.get_all_branches()}
    assert "Built Asset" in branches and "Responsibility Role" in branches
    assert "Area of Law" not in branches
    assert len(branches) == 9
    labels = service.get_all_labels()
    assert labels["owner"].concept.iri != labels["real property owner"].concept.iri
    assert not any("bankrupt" in key or key == "chapter 2" for key in labels)


async def test_real_ruler_preserves_distinct_roles_and_ignores_chapter(bundle):
    from app.pipeline.stages.entity_ruler_stage import EntityRulerStage
    job = Job(input=DocumentInput(content="Owner. Real Property Owner. Chapter 2.", ontology="dod-bco"))
    job.result.canonical_text = exact_canonical(job.input.content, DocumentFormat.PLAIN_TEXT)
    await EntityRulerStage().execute(job)
    pairs = {(a.span.text, c.folio_iri) for a in job.result.annotations for c in a.concepts}
    assert ("Owner", BASE_IRI + "Owner") in pairs
    assert ("Real Property Owner", BASE_IRI + "RealPropertyOwner") in pairs
    assert not any("Chapter" in text for text, _ in pairs)


async def test_triple_quotes_preserve_punctuation():
    from app.pipeline.stages.triple_stage import EarlyTripleStage
    text = "UFC 1-200-01 requires a Government-owned facility."
    job = Job(input=DocumentInput(content=text, ontology="dod-bco"))
    job.result.canonical_text = exact_canonical(text, DocumentFormat.PLAIN_TEXT)
    await EarlyTripleStage().execute(job)
    assert job.result.triples
    for triple in job.result.triples:
        for component in ("subject", "predicate", "object"):
            span = getattr(triple, component + "_span")
            if span:
                assert span.text == text[span.start:span.end]


async def test_legal_metadata_and_propositions_are_excluded(bundle):
    from tests.helpers import FailingLLMProvider
    from app.pipeline.stages.metadata_stage import MetadataStage
    from app.pipeline.stages.proposition_stage import EarlyPropositionStage
    job = job_for(bundle)
    await MetadataStage(FailingLLMProvider()).execute(job)
    await EarlyPropositionStage().execute(job)
    assert job.result.metadata["document_type"] == "UFC"
    assert "excluded" in job.result.metadata["bco_proposition_status"]
    assert not job.result.propositions


async def test_conditions_are_not_named_individuals():
    from app.bco.individuals import entity_runner
    records = await entity_runner().extract("Submit approval in the event of a change, unless exempt.")
    assert not any(r.mention_text == "in the event" for r in records)


async def test_source_api_symbolic_mode_completes_with_evidence(client, monkeypatch, job_store, ufc_bytes):
    import asyncio
    from app.api.routes import enrich
    from app.config import settings
    monkeypatch.setattr(enrich, "_job_store", job_store)
    monkeypatch.setattr(settings, "embedding_disabled", True)
    def forbidden(*args, **kwargs):
        raise AssertionError("use_llm=false must not resolve any LLM provider")
    monkeypatch.setattr(enrich, "_get_llm_for_request", forbidden)
    payload = {"content_base64": base64.b64encode(ufc_bytes).decode(), "source_format": "ufc_json", "use_llm": False}
    response = await client.post("/bco/enrich", json=payload)
    assert response.status_code == 202, response.text
    for _ in range(100):
        response = await client.get("/enrich/" + response.json()["job_id"]) if "job_id" in response.json() else await client.get("/enrich/" + response.json()["id"])
        result = response.json()
        if result["status"] in {"completed", "failed"}:
            break
        await asyncio.sleep(0.05)
    assert result["status"] == "completed", result.get("error")
    assert result["result"]["ontology_id"] == "dod-bco"
    assert result["result"]["metadata"]["bco_execution"]["llm_configured"] is False
    evidence = result["result"]["metadata"]["bco_evidence"]
    assert evidence["records"]
    assert evidence["source"]["source_family"] == "UFC"
    assert evidence["accepted_concept_count"] == 0
    response = await client.get("/bco/evidence/" + result["id"])
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.json() == evidence


async def test_api_rejects_inconsistent_source_content(client, bundle):
    response = await client.post("/enrich", json={"content": "changed", "format": "plain_text", "ontology": "dod-bco", "bco_source": bundle.model_dump()})
    assert response.status_code == 422


def test_bco_prompt_is_domain_specific():
    from app.services.llm.prompts.concept_identification import build_concept_identification_prompt
    prompt = build_concept_identification_prompt("Owner shall approve.", ontology_id="dod-bco")
    assert "DoD BCO" in prompt and "Responsibility Role" in prompt
    assert "legal concept annotator" not in prompt
    assert "Area of Law" not in prompt


async def test_optional_llm_stages_receive_bco_prompts(bundle):
    from tests.helpers import FakeLLMProvider
    from app.pipeline.stages.document_type_stage import DocumentTypeStage
    from app.services.concept.branch_judge import BranchJudge
    from app.services.individual.llm_individual_identifier import LLMIndividualIdentifier
    from app.services.property.llm_property_identifier import LLMPropertyIdentifier
    from app.services.llm.prompts.contextual_rerank import build_contextual_rerank_prompt
    class RecordingLLM(FakeLLMProvider):
        prompts = []
        async def structured(self, prompt, schema, **kwargs):
            self.prompts.append(prompt)
            return {"individuals": [], "properties": [], "branch": "", "confidence": 0, "self_identified_type": ""}
    llm = RecordingLLM()
    job = job_for(bundle)
    await DocumentTypeStage(llm).execute(job)
    await BranchJudge(llm).judge("Owner", bundle.text, ["Responsibility Role"], ontology_id="dod-bco")
    chunk = job.result.canonical_text.chunks[0]
    await LLMIndividualIdentifier(llm, ontology_id="dod-bco").identify_individuals(chunk, [], [])
    await LLMPropertyIdentifier(llm, ontology_id="dod-bco").identify_properties(chunk, [], [])
    llm.prompts.append(build_contextual_rerank_prompt(bundle.text, [], ontology_id="dod-bco"))
    assert len(llm.prompts) == 5
    assert all("DoD BCO" in p and "global synonym" in p for p in llm.prompts)
    assert all("legal concept relevance evaluator" not in p for p in llm.prompts)
