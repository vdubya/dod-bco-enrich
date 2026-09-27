#!/usr/bin/env python3
"""Plan or run bounded entity discovery over UFC JSON, UFGS XML, or the UFC master glossary PDF."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.bco.entities import EntityOptions, atomic_json, export_review_bundle, extract_entities, plan_summary
from app.bco.source import parse_source


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--format", choices=["ufc_json", "ufgs_sec", "ufc_glossary_pdf"])
    parser.add_argument("--source-designation", help="For the master glossary PDF, select one UFC context")
    parser.add_argument("--source-section-kind", choices=["glossary", "references", "supplemental_resources"])
    parser.add_argument("--profile", action="append", help="Repeat for multiple review profiles; default dod-base")
    parser.add_argument("--run", action="store_true", help="Make model calls; otherwise print a no-cost plan")
    parser.add_argument("--provider", help="Existing Enrich provider, e.g. openai, anthropic, ollama")
    parser.add_argument("--model", help="Explicit model identifier; no hidden model default")
    parser.add_argument("--output", type=Path, help="New output directory for this run")
    parser.add_argument("--cache", type=Path, default=ROOT / ".bco-state/entity-cache")
    parser.add_argument("--max-batches", type=int, default=5)
    parser.add_argument("--max-units", type=int, default=24)
    parser.add_argument("--max-characters", type=int, default=12000)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args(argv)
    try:
        fmt = args.format or ({".json": "ufc_json", ".pdf": "ufc_glossary_pdf"}.get(args.source.suffix.lower(), "ufgs_sec"))
        bundle = parse_source(args.source.read_bytes(), fmt, args.profile or ["dod-base"],
                              source_designation=args.source_designation, source_section_kind=args.source_section_kind)
        options = EntityOptions(max_batches=args.max_batches, max_units=args.max_units,
                                max_characters=args.max_characters, concurrency=args.concurrency,
                                attempts=args.attempts, timeout_seconds=args.timeout)
        plan = plan_summary(bundle, options)
        if not args.run:
            print(json.dumps(plan, indent=2, ensure_ascii=False))
            return 0
        if not args.output:
            parser.error("--run requires --output with a new directory")
        if args.output.exists():
            parser.error("Output already exists. Use a new directory; completed batches resume from --cache.")
        from app.bco.entity_provider import entity_provider, close_entity_provider
        provider, llm = entity_provider(args.provider, args.model)
        async def progress(batch):
            print(json.dumps({"batch": batch["index"] + 1, "status": batch["status"],
                              "cache_hit": batch["cache_hit"], "attempts": batch["attempts"]}), file=sys.stderr, flush=True)
        async def run():
            try:
                return await extract_entities(bundle, llm, provider=provider, options=options,
                                              cache_dir=args.cache, progress=progress)
            finally:
                await close_entity_provider(llm)
        report = asyncio.run(run())
        args.output.mkdir(parents=True)
        atomic_json(args.output / "entity-report.json", report)
        export_review_bundle(report, args.output / "review-bundle")
        print(json.dumps({"status": report["status"], "run_id": report["run_id"],
                          "entities": len(report["entities"]), "accepted_concepts": 0,
                          "coverage": report["coverage"], "output": str(args.output)}, indent=2))
        return 0 if report["status"] == "completed" else 2
    except (ValueError, OSError) as exc:
        # Configuration/parsing failures occur before any API request.
        print(f"Entity extraction could not complete: {type(exc).__name__}. {str(exc)[:250]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
