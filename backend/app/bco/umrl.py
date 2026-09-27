"""Expose the existing Criteria Atlas UMRL inventory as BCO named entities.

This is an adapter for already processed catalog and viewer artifacts. It does
not re-extract MASTER.REF, rerun the Criteria Atlas resolver, or approve concepts.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import unicodedata

DATA = Path(__file__).with_name("data") / "umrl"
ARTIFACTS = ("manifest.json", "umrl-viewer.json", "prior-analyses.json")


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def legacy_graph_id(reference_id: str) -> str:
    """Retain criteria_graph.utils.slug_id for interoperability, never as a key."""
    return re.sub(r"[^A-Z0-9]+", "-", " ".join(reference_id.split()).upper()).strip("-") or "UNKNOWN"


def normalize_reference(value: str) -> str:
    """Same normalization as the existing criteria_graph.umrl_pass resolver."""
    value = unicodedata.normalize("NFKD", value).upper().replace("&", " AND ")
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"(?<=[A-Z])(?=\d)|(?<=\d)(?=[A-Z])", " ", value)
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", value).split())


class UMRLCatalog:
    def __init__(self, viewer: dict, analyses: list[dict], provenance: dict):
        self.provenance = deepcopy(provenance)
        self.revision_id = hashlib.sha256(json_bytes(provenance)).hexdigest()
        self.records, self.organizations = {}, {}
        self.normalized = defaultdict(list)
        self.graph_ids = defaultdict(list)
        matches = defaultdict(list)
        seen_matches = set()
        for document in analyses:
            analysis = document["analysis"]
            if analysis["match_count"] != len(analysis["matches"]):
                raise ValueError("Existing UMRL analysis has inconsistent match counts")
            for match in analysis["matches"]:
                if match["match_id"] in seen_matches:
                    raise ValueError("Duplicate existing UMRL match ID")
                seen_matches.add(match["match_id"])
                matches[match["reference_id"]].append({
                    "designation": document["designation"],
                    "document_version_id": document.get("document_version_id"),
                    "analysis_source": document["source_file"], **deepcopy(match)})
        for record in viewer["records"]:
            rid = record["reference_id"]
            if not rid or rid in self.records:
                raise ValueError("UMRL viewer reference IDs must be nonempty and unique")
            if record["usage_count"] != len(record["usages"]):
                raise ValueError("Existing UMRL viewer has inconsistent usage counts")
            # The viewer's RID is the primary identity. Punctuation-stripped graph
            # slugs are nonunique (PL-109-58 and PL 109-58) and stay secondary.
            organization_id = "umrl-organization:" + record["organization"]
            self.organizations.setdefault(organization_id, {
                "entity_id": organization_id, "entity_type": "organization",
                "entity_kind": "named_individual", "name_exact": record["organization"],
                "acronyms_observed": [], "record_status": "source_catalog_record"})
            acronyms = self.organizations[organization_id]["acronyms_observed"]
            for acronym in record["organization_acronyms"]:
                if acronym not in acronyms:
                    acronyms.append(acronym)
            edition = re.match(r"^((?:\([^)]*\)\s*)+)", record["reference_title"])
            self.records[rid] = {
                **deepcopy(record), "entity_id": rid,
                "entity_type": "reference_publication", "entity_kind": "named_individual",
                "organization_id": organization_id, "legacy_graph_id": legacy_graph_id(rid),
                "catalog_entry_id": provenance["snapshot_id"] + ":" + rid,
                "listed_edition_statement": edition.group(1).rstrip() if edition else None,
                "edition_interpretation": "catalog_wording_only",
                "prior_matches": matches.pop(rid, []),
                "record_status": "source_catalog_record", "accepted_concept_id": None,
                "project_applicability": "not_evaluated", "standard_full_text_available": False,
            }
            self.normalized[normalize_reference(rid)].append(rid)
            self.graph_ids[legacy_graph_id(rid)].append(rid)
        if matches:
            raise ValueError("Existing matches reference records missing from the viewer catalog")
        self.collisions = {key: ids for key, ids in self.graph_ids.items() if len(ids) > 1}
        for record in self.records.values():
            record["legacy_graph_id_is_ambiguous"] = record["legacy_graph_id"] in self.collisions
            if any(match["reference_title"] != record["reference_title"] or match["organization"] != record["organization"]
                   for match in record["prior_matches"]):
                raise ValueError("Saved UMRL matches disagree with catalog publication metadata")
            # Check the join without altering the original viewer usage objects.
            original = sorted((m["designation"], m["axiom_id"], m["source_anchor"],
                m["match_basis"], m["review_status"], m["source_text_exact"], m["matched_value"], m["confidence"])
                for m in record["prior_matches"])
            displayed = sorted((m["designation"], m["axiom_id"], m["source_anchor"],
                m["match_basis"], m["review_status"], m["source_text_exact"], m["matched_value"], m["confidence"])
                for m in record["usages"])
            if original != displayed:
                raise ValueError("UMRL viewer usages and saved analyses disagree")
        self.summary = {
            "publications": len(self.records), "organizations": len(self.organizations),
            "processed_documents": len(analyses), "prior_matches": len(seen_matches),
            "used_publications": sum(bool(r["usages"]) for r in self.records.values()),
            "legacy_graph_id_collisions": len(self.collisions),
            "accepted_ontology_concepts": 0, "new_extraction_calls": 0,
        }
        for field, actual in [("record_count", len(self.records)),
                              ("organization_count", len(self.organizations)),
                              ("processed_document_count", len(analyses)),
                              ("match_count", len(seen_matches)),
                              ("used_record_count", self.summary["used_publications"])]:
            if viewer[field] != actual:
                raise ValueError(f"UMRL viewer {field} disagrees with imported evidence")

    def search(self, query: str = "", offset: int = 0, limit: int = 50) -> dict:
        if offset < 0 or not 1 <= limit <= 200:
            raise ValueError("UMRL pagination requires offset >= 0 and 1 <= limit <= 200")
        words = query.casefold().split()
        records = [r for r in self.records.values() if all(word in
            (r["reference_id"] + " " + r["reference_title"] + " " + r["organization"]).casefold()
            for word in words)]
        page = records[offset:offset + limit]
        organizations = {r["organization_id"] for r in page}
        return deepcopy({"source": self.provenance, "revision_id": self.revision_id, "summary": self.summary,
            "total_matches": len(records), "offset": offset, "limit": limit,
            "entities": page, "organizations": [self.organizations[k] for k in sorted(organizations)],
            "catalog_membership_establishes_project_adoption": False})

    def get(self, reference_id: str) -> dict | None:
        return deepcopy(self.records.get(reference_id))

    def resolve_candidate(self, text: str) -> dict:
        """Resolve a complete already-extracted mention; do not mine source text.

        Exact viewer IDs are identified. Normalized wording supplies candidates
        only, so punctuation collisions never silently merge publications.
        """
        exact = text in self.records
        ids = [text] if exact else self.normalized.get(normalize_reference(text), [])
        return {"entity_id": text if exact else None, "candidate_entity_ids": list(ids),
            "match_basis": "existing_reference_id" if exact else "normalized_designator_candidate" if ids else "not_in_catalog",
            "resolution_status": "publication_identified" if exact else "needs_review" if ids else "unresolved",
            "cited_edition": None, "edition_resolution": "not_inferred_from_catalog",
            "project_applicability": "not_evaluated"}

    def link_candidates(self, entities: list[dict]) -> dict:
        used = set()
        for entity in entities:
            if entity["entity_type"] != "document":
                continue
            link = self.resolve_candidate(entity["mention"]["source_text_exact"])
            entity["umrl_reference"] = link
            used.update(link["candidate_entity_ids"])
        organizations = {self.records[rid]["organization_id"] for rid in used}
        return deepcopy({"source": self.provenance, "revision_id": self.revision_id, "catalog_summary": self.summary,
            "entities": [self.records[rid] for rid in sorted(used)],
            "organizations": [self.organizations[k] for k in sorted(organizations)],
            "coverage": "Complete extracted publication mentions matched to existing RIDs only; the Criteria Atlas resolver remains separate.",
            "catalog_membership_establishes_project_adoption": False})


def catalog_from_artifacts(payloads: dict[str, bytes]) -> UMRLCatalog:
    if set(payloads) != set(ARTIFACTS):
        raise ValueError("UMRL snapshot must contain exactly the declared artifacts")
    manifest = json.loads(payloads["manifest.json"])
    values = {}
    for name in ARTIFACTS[1:]:
        payload = payloads[name]
        if hashlib.sha256(payload).hexdigest() != manifest["artifacts"][name]["sha256"]:
            raise ValueError("Bundled UMRL artifact does not match its pinned manifest")
        values[name] = json.loads(payload)
    catalog = UMRLCatalog(values["umrl-viewer.json"], values["prior-analyses.json"], manifest)
    catalog.revision_id = hashlib.sha256(payloads["manifest.json"]).hexdigest()
    return catalog


def read_artifacts(directory: Path) -> dict[str, bytes]:
    return {name: (directory / name).read_bytes() for name in ARTIFACTS}


def checked_revision(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Invalid UMRL revision identifier")
    return value


def snapshot_location(directory: Path, revision: str | None = None) -> tuple[Path, str]:
    """Read the active pointer once; old flat-layout snapshots remain readable."""
    pointer = directory / "current.json"
    if revision is None and pointer.exists():
        revision = json.loads(pointer.read_text())["revision_id"]
    if revision is not None:
        checked_revision(revision)
        candidate = directory / "snapshots" / revision
        if candidate.is_dir():
            return candidate, revision
        # The initial checked-in snapshot may not have needed migration yet.
        baseline = directory / "manifest.json"
        if baseline.exists() and hashlib.sha256(baseline.read_bytes()).hexdigest() == revision:
            return directory, revision
        raise FileNotFoundError("UMRL revision is not available")
    return directory, hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest()


def _load_snapshot(location: Path, revision: str) -> UMRLCatalog:
    catalog = catalog_from_artifacts(read_artifacts(location))
    if catalog.revision_id != revision:
        raise ValueError("UMRL snapshot manifest does not match the selected revision")
    return catalog


def load_umrl(directory: Path = DATA, revision: str | None = None) -> UMRLCatalog:
    return _load_snapshot(*snapshot_location(directory, revision))


@lru_cache(maxsize=4)
def _cached_snapshot(location: Path, revision: str) -> UMRLCatalog:
    return _load_snapshot(location, revision)


def default_umrl(revision: str | None = None) -> UMRLCatalog:
    # A new atomic pointer selects a new cache entry. An in-flight job can keep
    # using its original object while the next request sees the imported release.
    return _cached_snapshot(*snapshot_location(DATA, revision))


def umrl_history(directory: Path = DATA) -> dict:
    # Keep one pointer for this response even if another import finishes now.
    pointer_path = directory / "current.json"
    pointer = json.loads(pointer_path.read_bytes()) if pointer_path.exists() else None
    if pointer:
        current = checked_revision(pointer["revision_id"])
        snapshot_location(directory, current)
    else:
        current = hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest()
    locations = list((directory / "snapshots").glob("*/manifest.json"))
    if (directory / "manifest.json").exists():
        locations.append(directory / "manifest.json")
    revisions = {}
    for path in locations:
        payload = path.read_bytes()
        revision = hashlib.sha256(payload).hexdigest()
        if path.parent != directory and path.parent.name != revision:
            raise ValueError("Historical UMRL manifest has changed")
        manifest = json.loads(payload)
        revisions[revision] = {"revision_id": revision, "active": revision == current,
            "snapshot_id": manifest["snapshot_id"],
            "release_date": manifest["upstream_source_provenance"].get("release_date"),
            "import_mode": manifest.get("import_mode", "catalog_and_existing_evidence")}
    report = None
    if pointer:
        report_id = checked_revision(pointer["change_report_id"])
        payload = (directory / "changes" / (report_id + ".json")).read_bytes()
        if hashlib.sha256(payload).hexdigest() != report_id:
            raise ValueError("UMRL change report has changed")
        report = json.loads(payload)
    return {"current_revision_id": current,
            "revisions": sorted(revisions.values(), key=lambda r: (r["release_date"] or "", r["revision_id"]), reverse=True),
            "last_change_report": report}
