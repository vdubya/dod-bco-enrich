"""Publication designators are mentions; editions and target resolution stay open."""
import re

from app.models.annotation import Individual, IndividualClassLink, Span
from app.bco import BASE_IRI

PUBLICATION = re.compile(r"\b(?:UFC\s+\d-\d{3}-\d{2}(?:N)?|UFGS\s+\d{2}\s+\d{2}\s+\d{2}(?:\.\d{2}(?:\s+\d{2})?)?|(?:ER|EM)\s+\d{3,4}-\d-\d+|MIL-STD-\d+[A-Z]?)\b", re.I)
CLASSES = {"UFC": ("CriterionDocument", "Unified Facilities Criteria"),
           "UFGS": ("GuideSpecification", "Unified Facilities Guide Specifications"),
           "ER": ("EngineerRegulation", "Engineer Regulation"),
           "EM": ("EngineerManual", "Engineer Manual")}


def entity_runner():
    from app.services.individual.entity_extractors import (
        EntityExtractorRunner, MonetaryAmountExtractor, DateExtractor,
        DurationExtractor, PercentageExtractor, AddressExtractor,
        SpaCyPersonExtractor, SpaCyOrgExtractor, SpaCyLocationExtractor,
    )
    # Conditional phrases and definitions belong to assertion evidence, not the
    # named-instance layer. Court and intellectual-property heuristics are also
    # outside this facilities starter profile.
    return EntityExtractorRunner([MonetaryAmountExtractor(), DateExtractor(),
        DurationExtractor(), PercentageExtractor(), AddressExtractor(),
        SpaCyPersonExtractor(), SpaCyOrgExtractor(), SpaCyLocationExtractor()])


def publication_mentions(text):
    result = []
    for match in PUBLICATION.finditer(text):
        key, label = CLASSES.get(match.group().split()[0].upper(), ("Document", "Document"))
        result.append(Individual(name=match.group(), mention_text=match.group(),
            span=Span(start=match.start(), end=match.end(), text=match.group()),
            source="regex", confidence=0.9, class_links=[IndividualClassLink(
                folio_iri=BASE_IRI + key, folio_label=label, branch="Document", confidence=0.9)]))
    return result
