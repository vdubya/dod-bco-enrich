"""Source-preserving index for the official UFC glossary/reference compilation."""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re

import pypdf

SOURCE_URL = "https://www.wbdg.org/FFC/DOD/UFC/CORE_NON_CORE_UFC_Glossary_References.pdf"
TITLE = "CORE and NON_CORE UFC Glossary and Master Reference List"
DATA = Path(__file__).with_name("data") / "ufc-glossary"
UFC = re.compile(r"UFC\s+\d-\d{3}-\d{2}[A-Z]*", re.I)
ROLE = re.compile(r"GLOSSARY|REFERENCES|SUPPLEMENTAL\s+RESOURCES", re.I)
HEADING = re.compile(r"(?:APPENDIX\s+[A-Z]\s+)?(?P<ufc>UFC\s+\d-\d{3}-\d{2}[A-Z]*)\s+(?P<role>GLOSSARY|REFERENCES|SUPPLEMENTAL\s+RESOURCES)", re.I)


def _role(value: str) -> str:
    return "_".join(value.lower().split())


def index_pdf(payload: bytes) -> dict:
    if not payload.startswith(b"%PDF-"):
        raise ValueError("The UFC master glossary source must be a PDF")
    reader = pypdf.PdfReader(BytesIO(payload), strict=True)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 2000:
        raise ValueError("Encrypted or unsupported-length glossary PDF")
    sha = hashlib.sha256(payload).hexdigest()
    texts = [page.extract_text() or "" for page in reader.pages]
    groups, current = [], None
    for node in reader.outline:
        if isinstance(node, list):
            if current is None:
                raise ValueError("Glossary bookmarks have no parent UFC context")
            if any(isinstance(child, list) for child in node):
                raise ValueError("Nested glossary section bookmarks require adapter review")
            current["children"].extend(node)
        else:
            match = UFC.search(node.title)
            if not match:
                raise ValueError("Unrecognized top-level UFC bookmark")
            current = {"designation": " ".join(match.group().upper().split()),
                       "title_exact": node.title, "start": reader.get_destination_page_number(node) + 1,
                       "children": []}
            groups.append(current)
    if not groups or groups[0]["start"] != 1 or len({g["designation"] for g in groups}) != len(groups):
        raise ValueError("The glossary needs unique UFC bookmarks covering the document from page 1")
    if any(a["start"] >= b["start"] for a, b in zip(groups, groups[1:])):
        raise ValueError("UFC bookmarks are not ordered")
    sections, pages, findings = [], [], []
    for number, group in enumerate(groups):
        end = groups[number + 1]["start"] - 1 if number + 1 < len(groups) else len(texts)
        children = group["children"]
        starts = [reader.get_destination_page_number(child) + 1 for child in children]
        if not starts or starts[0] != group["start"] or any(a >= b for a, b in zip(starts, starts[1:])) or starts[-1] > end:
            raise ValueError("Section bookmarks must cover their UFC without overlaps or gaps")
        for ordinal, (child, start) in enumerate(zip(children, starts)):
            last = starts[ordinal + 1] - 1 if ordinal + 1 < len(starts) else end
            heading = HEADING.search(texts[start - 1][:900])
            if not heading or " ".join(heading["ufc"].upper().split()) != group["designation"]:
                raise ValueError(f"Printed section heading does not corroborate the UFC bookmark on PDF page {start}")
            role = _role(heading["role"])
            bookmark_role = ROLE.search(child.title)
            if not bookmark_role or _role(bookmark_role.group()) != role:
                findings.append({"code": "bookmark_role_differs_from_printed_heading", "pdf_page": start,
                    "bookmark_title_exact": child.title, "heading_text_exact": heading.group(),
                    "classification_basis": "printed_heading", "review_status": "source_structure_discrepancy"})
            bookmark_appendix = re.search(r"APPENDIX\s+([A-Z])", child.title, re.I)
            printed_appendix = re.search(r"APPENDIX\s+([A-Z])", heading.group(), re.I)
            if bookmark_appendix and printed_appendix and bookmark_appendix[1].upper() != printed_appendix[1].upper():
                findings.append({"code": "bookmark_appendix_differs_from_printed_heading", "pdf_page": start,
                    "bookmark_title_exact": child.title, "heading_text_exact": heading.group(),
                    "review_status": "source_structure_discrepancy"})
            section_id = "ufc-master:" + group["designation"] + ":" + role
            if any(s["section_id"] == section_id for s in sections):
                raise ValueError("Repeated section role needs a distinct scope identifier")
            sections.append({"section_id": section_id, "designation": group["designation"], "kind": role,
                "pdf_page_start": start, "pdf_page_end": last, "bookmark_title_exact": child.title,
                "heading": {"pdf_page": start, "start": heading.start(), "end": heading.end(), "text_exact": heading.group()},
                "text_sha256": hashlib.sha256("\f".join(texts[start - 1:last]).encode()).hexdigest()})
            for page_number in range(start, last + 1):
                text = texts[page_number - 1]
                pages.append({"page_id": f"ufc-master:{sha}:page:{page_number}", "pdf_page": page_number,
                    "designation": group["designation"], "section_id": section_id, "kind": role,
                    "text_exact": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "source_url": SOURCE_URL + f"#page={page_number}"})
    if [p["pdf_page"] for p in pages] != list(range(1, len(texts) + 1)):
        raise ValueError("Glossary page coverage is incomplete")
    return {"schema_version": 1, "source_id": "ufc-master-glossary-references",
        "source_family": "UFC_GLOSSARY_REFERENCES", "source_url": SOURCE_URL,
        "source_sha256": sha, "title": str((reader.metadata or {}).get("/Title") or TITLE),
        "pdf_metadata": {str(k): str(v) for k, v in (reader.metadata or {}).items()},
        "source_edition": "not_inferred_from_pdf_creation_or_modification_metadata",
        "extraction": {"method": "pypdf_text_and_publisher_bookmarks_corroborated_by_printed_headings",
            "parser_version": 1, "pypdf_version": pypdf.__version__, "ocr_performed": False,
            "text_coordinates": "decoded_pdf_page_text_not_byte_offsets",
            "semantic_entity_extraction": "not_performed", "accepted_ontology_concepts": 0},
        "summary": {"pdf_pages": len(pages), "ufc_contexts": len(groups),
            "sections_by_kind": dict(Counter(s["kind"] for s in sections)),
            "pages_without_extracted_text": [p["pdf_page"] for p in pages if not p["text_exact"].strip()],
            "structure_findings": len(findings)},
        "sections": sections, "pages": pages, "findings": findings}


def source_bundle(index: dict, payload: bytes, profile_ids=None, *, designation=None, section_kind=None):
    from app.bco.source import _assemble
    if hashlib.sha256(payload).hexdigest() != index["source_sha256"]:
        raise ValueError("Glossary index does not match the original PDF")
    if designation and designation not in {s["designation"] for s in index["sections"]}:
        raise ValueError("Requested UFC is absent from the glossary snapshot")
    if section_kind and section_kind not in {"glossary", "references", "supplemental_resources"}:
        raise ValueError("Unknown glossary section kind")
    selected = [p for p in index["pages"] if (not designation or p["designation"] == designation)
                and (not section_kind or p["kind"] == section_kind)]
    sections = {s["section_id"]: s for s in index["sections"]}
    rows = [{"locator": f"pdf:page:{p['pdf_page']}:text", "locator_kind": "pdf_page_text",
        "text": p["text_exact"], "kind": p["kind"] + "_page", "container_id": p["section_id"],
        "section_path": [p["designation"], p["kind"], sections[p["section_id"]]["heading"]["text_exact"]],
        "source_node_id": p["page_id"]} for p in selected]
    return _assemble(rows, payload, source_family="UFC_GLOSSARY_REFERENCES",
        designation=designation or "UFC Master Glossary and References", title=index["title"],
        version_id="sha256:" + index["source_sha256"], source_uri=SOURCE_URL,
        profile_ids=profile_ids if profile_ids is not None else ["dod-base"],
        coverage={"mined": ["decoded_pdf_page_text"], "source_summary": index["summary"],
            "selected_designation": designation, "selected_section_kind": section_kind,
            "selected_pdf_pages": [p["pdf_page"] for p in selected],
            "findings": [f for f in index["findings"] if f["pdf_page"] in {p["pdf_page"] for p in selected}],
            "same_label_across_ufcs_establishes_equivalence": False,
            "source_edition": index["source_edition"], "pdf_text_layout_review_required": True,
            "semantic_completeness": "not_measured", "extraction": index["extraction"]})


def read_snapshot(folder: Path, revision: str):
    """Validate on disk, including when an importer revisits an old snapshot."""
    manifest = json.loads((folder / "manifest.json").read_bytes())
    payloads = {name: (folder / name).read_bytes() for name in ("source.pdf", "page-index.json")}
    if manifest["source_sha256"] != revision or hashlib.sha256(payloads["source.pdf"]).hexdigest() != revision:
        raise ValueError("Glossary PDF snapshot hash mismatch")
    for name, payload in payloads.items():
        if hashlib.sha256(payload).hexdigest() != manifest["artifacts"][name]["sha256"]:
            raise ValueError("Glossary artifact differs from its manifest")
    index = json.loads(payloads["page-index.json"])
    if index["source_sha256"] != revision:
        raise ValueError("Glossary index identifies a different PDF")
    return manifest, index


@lru_cache(maxsize=2)
def _load_snapshot(directory: Path, revision: str):
    return read_snapshot(directory / "snapshots" / revision, revision)


def load_glossary(revision: str | None = None):
    revision = revision or json.loads((DATA / "current.json").read_bytes())["source_sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", revision):
        raise ValueError("Invalid glossary snapshot ID")
    return _load_snapshot(DATA, revision)
