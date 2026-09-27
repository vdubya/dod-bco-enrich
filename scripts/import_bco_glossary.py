#!/usr/bin/env python3
"""Import or refresh the official UFC glossary/reference PDF with immutable snapshots."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import httpx
from pypdf.errors import PdfReadError

from app.bco.glossary import DATA
from app.bco.glossary_import import download_official, import_pdf


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--refresh", action="store_true", help="Download the fixed official WBDG URL")
    source.add_argument("--pdf", type=Path, help="Import local source bytes; remote origin remains unverified")
    parser.add_argument("--output", type=Path, default=DATA, help="BCO glossary snapshot store")
    parser.add_argument("--dry-run", action="store_true", help="Compare without changing the snapshot store")
    args = parser.parse_args(argv)
    try:
        if args.refresh:
            payload, acquisition = download_official()
        else:
            payload = args.pdf.read_bytes()
            acquisition = {"method": "local_file", "filename": args.pdf.name,
                "imported_at": datetime.now(timezone.utc).isoformat(), "remote_origin_verified": False}
        report = import_pdf(payload, args.output, acquisition=acquisition, dry_run=args.dry_run)
    except (OSError, ValueError, KeyError, TypeError, PdfReadError, httpx.HTTPError) as exc:
        parser.exit(1, f"UFC glossary import failed: {exc}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
