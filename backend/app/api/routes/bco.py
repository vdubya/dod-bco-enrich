"""Source-preserving entry point for the DoD BCO fork."""
import base64
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.routes.enrich import EnrichRequest, create_enrichment, get_enrichment
from app.bco.source import parse_source
from app.config import settings

router = APIRouter(prefix="/bco", tags=["DoD BCO"])


@router.get("/evidence/{job_id}")
async def download_evidence(job_id: UUID):
    job = await get_enrichment(job_id)
    evidence = job.result.metadata.get("bco_evidence")
    if job.ontology != "dod-bco" or evidence is None:
        raise HTTPException(404, "No completed BCO evidence ledger for this job")
    return JSONResponse(evidence, headers={
        "Content-Disposition": f'attachment; filename="dod-bco-evidence-{job_id}.json"'})


class BCOSourceRequest(BaseModel):
    content_base64: str
    source_format: Literal["ufc_json", "ufgs_sec"]
    filename: str | None = None
    profile_ids: list[str] = Field(default_factory=lambda: ["dod-base"])
    llm_provider: str | None = None
    llm_model: str | None = None
    api_key: str | None = None
    use_llm: bool = True


def decode_source(req: BCOSourceRequest):
    if len(req.content_base64) > settings.max_upload_size * 4 // 3 + 4:
        raise HTTPException(413, "Source is larger than the configured upload limit")
    try:
        payload = base64.b64decode(req.content_base64, validate=True)
        bundle = parse_source(payload, req.source_format, req.profile_ids)
    except Exception as exc:
        # Syntax/structure errors are explicit. Never silently repair a master.
        raise HTTPException(422, f"Source could not be parsed: {type(exc).__name__}") from exc
    return bundle


@router.post("/parse")
async def preview_source(req: BCOSourceRequest):
    return decode_source(req)


@router.post("/enrich", status_code=202)
async def enrich_source(req: BCOSourceRequest):
    bundle = decode_source(req)
    return await create_enrichment(EnrichRequest(
        content=bundle.text, format="plain_text", ontology="dod-bco", filename=req.filename,
        bco_source=bundle, llm_provider=req.llm_provider, llm_model=req.llm_model, api_key=req.api_key, use_llm=req.use_llm))
