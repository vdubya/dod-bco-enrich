#!/usr/bin/env python3
"""Submit an original UFC JSON/SEC source and save the completed evidence ledger."""
import argparse
import base64
import json
from pathlib import Path
import time

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--format", choices=["ufc_json", "ufgs_sec"])
    parser.add_argument("--profile", default="dod-base")
    parser.add_argument("--server", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--with-llm", action="store_true", help="Use the server's explicitly configured provider; default is symbolic only")
    args = parser.parse_args()
    fmt = args.format or ("ufc_json" if args.source.suffix.lower() == ".json" else "ufgs_sec")
    payload = {"content_base64": base64.b64encode(args.source.read_bytes()).decode(),
               "source_format": fmt, "filename": args.source.name, "profile_ids": [args.profile], "use_llm": args.with_llm}
    with httpx.Client(base_url=args.server, timeout=60) as client:
        response = client.post("/bco/enrich", json=payload)
        response.raise_for_status()
        job_id = response.json()["job_id"]
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            response = client.get("/enrich/" + job_id)
            response.raise_for_status()
            job = response.json()
            if job["status"] in {"completed", "failed"}:
                break
            time.sleep(0.5)
        else:
            raise TimeoutError(f"Job {job_id} is still running; check /enrich/{job_id}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(job, indent=2, ensure_ascii=False) + "\n")
    if job["status"] != "completed":
        raise RuntimeError(job.get("error", "Job failed"))
    evidence = job["result"]["metadata"]["bco_evidence"]
    print(json.dumps({"job_id": job_id, "source": evidence["source"]["designation"],
        "evidence_records": len(evidence["records"]), "span_findings": len(evidence["findings"]),
        "accepted_concepts": evidence["accepted_concept_count"],
        "review_url": args.server + "/?ontology=dod-bco&job=" + job_id, "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
