"""Build the editorial BCO matching scaffold; this does not approve definitions."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "backend/app/bco"
BASE = "https://example.org/dod-bco/"
NS = {"rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#", "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
      "owl": "http://www.w3.org/2002/07/owl#", "skos": "http://www.w3.org/2004/02/skos/core#"}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)

GROUPS = {
    "BuiltAsset": ("Built Asset", [
        ("Facility", "Facility", ["facilities"]), ("Building", "Building", ["buildings"]),
        ("Infrastructure", "Infrastructure", []), ("Space", "Space", ["spaces"]),
        ("GovernmentOwnedFacility", "Government-owned facility", ["Government-owned facilities"]),
        ("LeasedFacility", "Leased facility", ["leased facilities"])]),
    "ResponsibilityRole": ("Responsibility Role", [
        ("Owner", "Owner", []), ("OwnersRepresentative", "Owner’s Representative", ["Owner's Representative"]),
        ("OwnersAuthorizedAgent", "Owner’s Authorized Agent", ["Owner's Authorized Agent"]),
        ("RealPropertyOwner", "Real Property Owner", []), ("ContractingOfficer", "Contracting Officer", []),
        ("Lessor", "Lessor", []), ("DesignerOfRecord", "Designer of Record", ["DoR"]),
        ("EngineerOfRecord", "Engineer of Record", ["EoR"]),
        ("StructuralEngineerOfRecord", "Structural Engineer of Record", ["SER"]),
        ("RegisteredDesignProfessional", "Registered Design Professional", []),
        ("BuildingOfficial", "Building Official", []), ("CodeOfficial", "Code Official", []),
        ("AuthorityHavingJurisdiction", "Authority Having Jurisdiction", ["AHJ"]),
        ("ComponentTechnicalRepresentative", "Component Technical Representative", ["CTR"]),
        ("EngineeringSeniorExecutivePanel", "Engineering Senior Executive Panel", ["ESEP"]),
        ("PermitHolder", "Permit Holder", [])]),
    "ComplianceConcept": ("Compliance Concept", [
        ("Requirement", "Requirement", ["requirements"]), ("Waiver", "Waiver", ["waivers"]),
        ("Exemption", "Exemption", ["exemptions"]), ("Exception", "Exception", ["exceptions"]),
        ("ApplicabilityCondition", "Applicability condition", []), ("Approval", "Approval", ["approvals"])]),
    "ConstructionLevel": ("Construction Level", [
        ("PermanentConstruction", "Permanent construction", []),
        ("TemporaryConstruction", "Temporary construction", []),
        ("NonPermanentConstruction", "Non-permanent construction", []),
        ("SemiPermanentConstruction", "Semi-permanent construction", [])]),
    "Document": ("Document", [
        ("CriterionDocument", "Unified Facilities Criteria", ["UFC"]),
        ("GuideSpecification", "Unified Facilities Guide Specifications", ["UFGS"]),
        ("BuildingCode", "Building code", []), ("EngineerRegulation", "Engineer Regulation", []),
        ("EngineerManual", "Engineer Manual", []), ("AcceptanceForm", "DD Form 1354", [])]),
    "Organization": ("Organization", [
        ("DepartmentOfDefense", "Department of Defense", ["DoD"]),
        ("USACE", "US Army Corps of Engineers", ["USACE"]),
        ("NAVFAC", "Naval Facilities Engineering Systems Command", ["NAVFAC"]),
        ("USAF", "United States Air Force", ["USAF"]),
        ("WHS", "Washington Headquarters Services", ["WHS"])]),
    "LifecycleActivity": ("Lifecycle Activity", [
        ("Design", "Design", []), ("Construction", "Construction", []),
        ("Operation", "Operation", ["operations"]), ("Maintenance", "Maintenance", []),
        ("Repair", "Repair", ["repairs"]), ("Alteration", "Alteration", ["alterations"]),
        ("Disposal", "Disposal", [])]),
    "PropertyInterest": ("Property Interest", [
        ("RealEstate", "Real estate", []), ("RealProperty", "Real property", []),
        ("Lease", "Lease", ["leases"]), ("Easement", "Easement", ["easements"])]),
    "TechnicalSystem": ("Technical System", [
        ("StructuralSystem", "Structural system", []), ("FireProtection", "Fire protection", []),
        ("MechanicalSystem", "Mechanical system", []), ("PlumbingSystem", "Plumbing system", []),
        ("ElectricalSystem", "Electrical system", [])]),
}
PROPERTIES = {"requires": ["requires", "require"], "appliesTo": ["applies to"], "modifies": ["modifies", "modify"],
              "supersedes": ["supersedes"], "reissues": ["reissues"], "cancels": ["cancels"],
              "references": ["references"], "approves": ["approves", "approve"],
              "accepts": ["accepts"], "takesPrecedenceOver": ["takes precedence over"]}


def tag(prefix, name):
    return "{" + NS[prefix] + "}" + name


def main():
    root = ET.Element(tag("rdf", "RDF"))
    ontology = ET.SubElement(root, tag("owl", "Ontology"), {tag("rdf", "about"): BASE})
    ET.SubElement(ontology, tag("rdfs", "label")).text = "DoD Building Code Ontology"
    ET.SubElement(ontology, tag("rdfs", "comment")).text = "Prototype matching scaffold for an ontology and knowledge graph. No approved definitions. The example.org namespace is provisional."
    count = 0
    for parent, (label, children) in GROUPS.items():
        for key, name, aliases in [(parent, label, [])] + children:
            cls = ET.SubElement(root, tag("owl", "Class"), {tag("rdf", "about"): BASE + key})
            ET.SubElement(cls, tag("rdfs", "label")).text = name
            ET.SubElement(cls, tag("skos", "definition")).text = "Editorial matching category only. Source-specific definitions and applicability remain pending review."
            ET.SubElement(cls, tag("rdfs", "subClassOf"), {tag("rdf", "resource"): NS["owl"] + "Thing" if key == parent else BASE + parent})
            for alias in aliases:
                ET.SubElement(cls, tag("skos", "altLabel")).text = alias
            count += 1
    for key, labels in PROPERTIES.items():
        prop = ET.SubElement(root, tag("owl", "ObjectProperty"), {tag("rdf", "about"): BASE + key})
        ET.SubElement(prop, tag("rdfs", "label")).text = labels[0]
        for label in labels[1:]:
            ET.SubElement(prop, tag("skos", "altLabel")).text = label
    ET.indent(root)
    # folio-python reads cached OWL as Unicode before passing it to lxml.
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=False) + b"\n"
    (OUT / "dod-bco.owl").write_bytes(payload)
    manifest = {"name": "DoD BCO", "pronunciation": "beeco", "expansion": "DoD Building Code Ontology",
                "descriptor": "Ontology and Knowledge Graph for the DoD built environment",
                "status": "editorial_prototype_not_an_approved_vocabulary", "base_iri": BASE,
                "class_count": count, "property_count": len(PROPERTIES), "accepted_definition_count": 0,
                "owl_sha256": hashlib.sha256(payload).hexdigest(), "source": "scripts/build_bco_seed.py"}
    (OUT / "seed-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
