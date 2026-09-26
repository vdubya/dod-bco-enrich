"""Validate annotation coordinates and attach source-specific candidate senses."""
from __future__ import annotations

import hashlib
import re

from app.bco import VERSION
from app.bco.source import SourceBundle

CUE = re.compile(r"\b(?:must not|shall not|must|shall|may|except|unless|excludes?|for government-owned|for leased|for geotechnical|typically|indefinitely)\b|\b\d+\s+(?:days?|months?|years?)\b", re.I)


def annotate_evidence(job):
    if job.ontology != "dod-bco":
        return
    if job.result.canonical_text is None:
        raise ValueError("BCO cannot complete without canonical source text")
    text = job.result.canonical_text.full_text
    bundle = job.input.bco_source if job.input else None
    if bundle is not None and text != bundle.text:
        raise ValueError("BCO canonical text changed; source coordinates are invalid")
    rows, findings = [], []
    objects = [("concept", a, a.span) for a in job.result.annotations]
    objects += [("individual", a, a.span) for a in job.result.individuals]
    objects += [("property", a, a.span) for a in job.result.properties]
    for triple in job.result.triples:
        for component in ("subject", "predicate", "object"):
            span = getattr(triple, component + "_span", None)
            if span is not None:
                objects.append(("triple_" + component, triple, span))
            else:
                findings.append({"record_id": triple.id, "kind": "triple_component_without_span", "component": component, "review_required": True})
    for kind, record, span in objects:
        valid = 0 <= span.start < span.end <= len(text) and text[span.start:span.end] == span.text
        if not valid:
            findings.append({"record_id": record.id, "kind": "invalid_source_span", "review_required": True})
            continue
        fragments, context_units = [], []
        if bundle:
            matched = [u for u in bundle.units if u.start < span.end and span.start < u.end]
            containers = {u.container_id for u in matched}
            context_units = [u for u in bundle.units if u.container_id in containers]
            for u in matched:
                a, b = max(span.start, u.start), min(span.end, u.end)
                fragments.append({"unit_id": u.unit_id, "locator": u.locator, "locator_kind": u.locator_kind,
                                  "start_in_unit": a - u.start, "end_in_unit": b - u.start, "text_exact": text[a:b]})
        identities = [c.folio_iri for c in getattr(record, "concepts", []) if c.folio_iri]
        identities += [c.folio_iri for c in getattr(record, "class_links", []) if c.folio_iri]
        if getattr(record, "folio_iri", None):
            identities.append(record.folio_iri)
        identity = [bundle.source_sha256 if bundle else hashlib.sha256(text.encode()).hexdigest(),
                    sorted(set(bundle.profile_ids)) if bundle else [], span.start, span.end, identities, kind]
        rows.append({"record_id": record.id, "kind": kind, "span_valid": True, "text_exact": span.text,
                     "candidate_sense_id": "bco-sense-" + hashlib.sha256(repr(identity).encode()).hexdigest()[:24],
                     "source_fragments": fragments, "context_unit_ids": [u.unit_id for u in context_units],
                     "scope_cues": [{"unit_id": u.unit_id, "start": m.start(), "end": m.end(), "text_exact": m.group()}
                                    for u in context_units for m in CUE.finditer(u.text)],
                     "source_anchored": bool(fragments), "accepted_concept_id": None,
                     "review_status": "candidate_pending_subject_matter_review",
                     "global_equivalence_asserted": False, "project_applicability": "not_evaluated"})
    job.result.metadata["bco_evidence"] = {"version": VERSION, "records": rows, "findings": findings,
        "source": bundle.model_dump(exclude={"text", "units"}) if bundle else None,
        "source_units": [u.model_dump() for u in bundle.units] if bundle else [],
        "upstream_confirmed_means": "machine_match_only", "accepted_concept_count": 0,
        "validation_status": "span_findings_require_review" if findings else "recorded_spans_valid",
        "triples_are": "syntactic_candidates_not_approved_normative_assertions",
        "triple_span_policy": "verbatim_covering_quote; normalized_components_remain_separate",
        "semantic_precision_or_recall_measured": False}
