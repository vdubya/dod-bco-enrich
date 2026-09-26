"""Lossless text envelopes for UFC JSON and strict SpecsIntact SEC XML.

Text coordinates refer to decoded source fields, not serialized byte offsets.
The SHA-256 identifies the original bytes; synthetic separators have no evidence.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

PROFILE_IDS = frozenset(p["profile_id"] for p in json.loads(
    Path(__file__).with_name("profiles.json").read_text())["profiles"])


class SourceUnit(BaseModel):
    unit_id: str
    locator: str
    locator_kind: str
    text: str
    start: int
    end: int
    kind: str
    container_id: str
    section_path: list[str] = Field(default_factory=list)
    source_node_id: str | None = None
    source_sentence_id: str | None = None
    markup_context: list[dict] = Field(default_factory=list)


class SourceBundle(BaseModel):
    source_family: Literal["UFC", "UFGS"]
    designation: str
    title: str = ""
    version_id: str
    version_label: str = ""
    source_sha256: str
    source_uri: str | None = None
    profile_ids: list[str] = Field(default_factory=lambda: ["dod-base"])
    units: list[SourceUnit]
    text: str
    coverage: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_evidence(self):
        if not self.profile_ids or set(self.profile_ids) - PROFILE_IDS:
            raise ValueError("Unknown or empty BCO profile selection")
        ids = set()
        previous_end = 0
        for unit in self.units:
            if unit.unit_id in ids or not (previous_end <= unit.start < unit.end <= len(self.text)):
                raise ValueError("Invalid or overlapping source unit")
            if self.text[unit.start:unit.end] != unit.text:
                raise ValueError("Source unit does not round-trip to canonical text")
            ids.add(unit.unit_id)
            previous_end = unit.end
        if not self.units:
            raise ValueError("No source text found")
        return self


def _assemble(rows: list[dict], payload: bytes, **metadata) -> SourceBundle:
    sha = hashlib.sha256(payload).hexdigest()
    text = ""
    units = []
    for row in rows:
        if not row["text"].strip():
            continue
        if units:
            text += "\n\n"
        start = len(text)
        text += row["text"]
        key = sha + "\0" + row["locator"]
        units.append(SourceUnit(**row, unit_id="bco-unit-" + hashlib.sha256(key.encode()).hexdigest()[:24],
                                start=start, end=len(text)))
    return SourceBundle(**metadata, source_sha256=sha, text=text, units=units)


def parse_ufc(payload: bytes, profile_ids: list[str] | None = None) -> SourceBundle:
    data = json.loads(payload)
    criterion = data["criterion"]
    rows = []
    exclusions = defaultdict(int)

    def walk(nodes, prefix, ancestors):
        for index, node in enumerate(nodes):
            path = f"{prefix}/{index}"
            heading = node.get("heading") or ""
            label = node.get("label") or ""
            trail = ancestors + ([f"{label} {heading}".strip()] if heading or label else [])
            common = {"container_id": path, "section_path": trail, "source_node_id": node.get("id"), "locator_kind": "json_pointer"}
            if heading:
                rows.append(dict(common, locator=path + "/heading", text=heading, kind="heading"))
            for si, sentence in enumerate(node.get("sentences") or []):
                if isinstance(sentence.get("text"), str):
                    rows.append(dict(common, locator=f"{path}/sentences/{si}/text", text=sentence["text"],
                                     kind="sentence", source_sentence_id=sentence.get("id")))
            exclusions["commentary_records_not_mined"] += len(node.get("commentary") or [])
            exclusions["media_nodes_not_mined"] += bool(node.get("mediaAsset"))
            if node.get("content") and not node.get("sentences"):
                exclusions["content_fields_not_mined"] += 1
            walk(node.get("children") or [], path + "/children", trail)

    walk(data["sections"], "/sections", [])
    version = criterion["versionId"]
    return _assemble(rows, payload, source_family="UFC", designation=criterion["designation"],
                     title=criterion.get("title", ""), version_id=version,
                     version_label=str(criterion.get("versionNumber") or ""),
                     source_uri=f"https://digital.wbdg.org/versions/{version}", profile_ids=profile_ids if profile_ids is not None else ["dod-base"],
                     coverage={"mined": ["headings", "sentence_fields"], "exclusions": dict(exclusions), "semantic_completeness": "not_measured"})


def parse_ufgs(payload: bytes, profile_ids: list[str] | None = None) -> SourceBundle:
    from lxml import etree

    if b"<!doctype" in payload[:8192].replace(b"\x00", b"").lower():
        raise ValueError("SEC files with a DTD require a separately reviewed adapter")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, recover=False)
    root = etree.fromstring(payload, parser)
    tree = root.getroottree()
    if tree.docinfo.doctype:
        raise ValueError("SEC files with a DTD require a separately reviewed adapter")
    rows = []
    # Capture outer text blocks once; inline tags remain represented in exact
    # element text and the original-byte hash. Guide notes remain guide notes.
    blocks = {"TXT", "TTL", "STL", "SCN", "DTE", "PRA", "NTE", "NOTE"}

    def local(el):
        return etree.QName(el).localname.upper() if isinstance(el.tag, str) else ""

    def append(el, field, text, context):
        if not text or not text.strip():
            return
        tags = {x["tag"] for x in context}
        kind = "guide_note" if tags & {"NTE", "NOTE"} else ("heading" if local(el) in {"TTL", "STL", "SCN"} else "text")
        rows.append({"locator": tree.getpath(el) + "::" + field, "locator_kind": "xpath_text",
                     "text": text, "kind": kind, "container_id": tree.getpath(el.getparent() if el.getparent() is not None else el),
                     "section_path": [x["tag"] for x in context], "markup_context": context})

    def walk(el, ancestors):
        if not isinstance(el.tag, str):
            return
        context = ancestors + [{"tag": local(el), "attributes": dict(el.attrib)}]
        if local(el) in blocks:
            append(el, "itertext", "".join(el.itertext()), context)
            return
        append(el, "text", el.text, context)
        for child in el:
            walk(child, context)
            append(child, "tail", child.tail, context)

    walk(root, [])

    def first(tag):
        return next(("".join(el.itertext()).strip() for el in root.iter() if local(el) == tag), "")

    designation = first("SCN").removeprefix("SECTION").strip()
    if not designation:
        raise ValueError("SEC source lacks a section designation")
    return _assemble(rows, payload, source_family="UFGS", designation="UFGS " + designation,
                     title=first("STL"), version_id="sha256:" + hashlib.sha256(payload).hexdigest(),
                     version_label=first("DTE"), profile_ids=profile_ids if profile_ids is not None else ["dod-base"],
                     coverage={"mined": ["decoded_XML_text_blocks"], "project_tailoring": "not_evaluated",
                               "guide_specification_is_not_an_adopted_project_requirement": True})


def parse_source(payload: bytes, source_format: str, profile_ids: list[str] | None = None) -> SourceBundle:
    if source_format == "ufc_json":
        return parse_ufc(payload, profile_ids)
    if source_format == "ufgs_sec":
        return parse_ufgs(payload, profile_ids)
    raise ValueError("Unsupported BCO source format")
