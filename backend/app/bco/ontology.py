"""Load pinned bundled RDF/XML through folio-python's verified local cache."""
import hashlib
import json
from pathlib import Path


def load_bundled_ontology(spec):
    from folio import FOLIO
    from app.services.ontology.ingestion import _reject_doctype, _validate_xml, assert_label_coverage

    root = Path(__file__).parent
    path = root / spec.coords.bundled_file
    if path.resolve().parent != root.resolve():
        raise ValueError("Bundled ontology path must be within the BCO package")
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    manifest = json.loads((root / "seed-manifest.json").read_text())
    if sha != manifest["owl_sha256"]:
        raise ValueError("Bundled BCO ontology differs from its manifest")
    _reject_doctype(data)
    _validate_xml(data)
    assert_label_coverage(data, spec.min_label_coverage or 100.0, spec.id)
    # folio-python supports github/http but no file constructor. Mirror upstream's
    # verified cache path, with a content-addressed reserved URL and no HTTP call.
    url = f"https://example.invalid/dod-bco/{sha}.owl"
    cache = Path.home() / ".folio/cache/http" / (hashlib.blake2b(url.encode()).hexdigest() + ".owl")
    cache.parent.mkdir(parents=True, exist_ok=True)
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=cache.parent, prefix="bco-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(tmp, cache)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    if not FOLIO.load_cache(source_type="http", http_url=url):
        raise ValueError("folio-python could not read the verified bundled cache")
    return FOLIO(source_type="http", http_url=url, use_cache=True)
