"""Source-preserving entry point for the DoD BCO fork."""
import base64
import asyncio
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.routes.enrich import EnrichRequest, create_enrichment, get_enrichment
from app.bco.source import parse_source
from app.config import settings
from app.bco.entities import EntityOptions, extract_entities, plan_summary
from app.bco.umrl import default_umrl

router = APIRouter(prefix="/bco", tags=["DoD BCO"])
_entity_tasks: set[asyncio.Task] = set()


@router.get("/umrl")
def search_umrl(q: str = Query(default="", max_length=300),
                offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=200)):
    return default_umrl().search(q, offset, limit)


@router.get("/umrl/entity")
def get_umrl_entity(reference_id: str = Query(min_length=1, max_length=300)):
    record = default_umrl().get(reference_id)
    if record is None:
        raise HTTPException(404, "Reference ID is absent from the pinned UMRL inventory")
    return {"source": default_umrl().provenance, "entity": record,
            "organization": default_umrl().organizations[record["organization_id"]],
            "catalog_membership_establishes_project_adoption": False}


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


class BCOEntityRequest(BCOSourceRequest):
    options: EntityOptions = Field(default_factory=EntityOptions)


@router.post("/entities/plan")
async def entity_plan(req: BCOEntityRequest):
    try:
        return plan_summary(decode_source(req), req.options)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/entities", status_code=202)
async def create_entity_extraction(req: BCOEntityRequest):
    from app.api.routes.enrich import _job_store
    from app.bco.entity_provider import entity_provider, close_entity_provider
    from app.models.document import DocumentInput
    from app.models.job import Job, JobStatus
    if not req.use_llm:
        raise HTTPException(422, "Entity discovery requires use_llm=true; use /bco/entities/plan for a no-call plan.")
    if await _job_store.count_active() >= settings.max_concurrent_jobs:
        raise HTTPException(429, "Too many active extraction jobs. Try again when one completes.")
    bundle = decode_source(req)
    try:
        plan_summary(bundle, req.options)
        provider, llm = entity_provider(req.llm_provider, req.llm_model, req.api_key)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    job = Job(input=DocumentInput(content=bundle.text, format="plain_text", ontology="dod-bco", bco_source=bundle),
              status=JobStatus.IDENTIFYING)
    job.result.ontology_id, job.result.ontology_name = "dod-bco", "DoD BCO"
    job.result.base_iri = "https://example.org/dod-bco/"
    job.result.metadata["bco_entity_progress"] = []
    await _job_store.save(job)
    async def run():
        async def progress(batch):
            job.result.metadata["bco_entity_progress"].append(batch)
            job.updated_at = datetime.now(timezone.utc)
            await _job_store.save(job)
        try:
            report = await extract_entities(bundle, llm, provider=provider, options=req.options,
                cache_dir=_job_store.base_dir.parent / "entity-cache", progress=progress)
            job.result.metadata["bco_entities"] = report
            job.status = JobStatus.COMPLETED if report["status"] == "completed" else JobStatus.FAILED
            if report["status"] != "completed":
                job.error = "Entity run is incomplete. Inspect coverage and batch findings; validated candidates are retained."
        except Exception as exc:
            job.status, job.error = JobStatus.FAILED, f"Entity extraction failed ({type(exc).__name__})."
        finally:
            await close_entity_provider(llm)
        job.updated_at = datetime.now(timezone.utc)
        await _job_store.save(job)
    task = asyncio.create_task(run())
    _entity_tasks.add(task)
    task.add_done_callback(_entity_tasks.discard)
    return {"job_id": str(job.id), "status": job.status.value,
            "status_url": f"/enrich/{job.id}", "entities_url": f"/bco/entities/{job.id}"}


@router.get("/entities/{job_id}")
async def download_entities(job_id: UUID):
    job = await get_enrichment(job_id)
    report = job.result.metadata.get("bco_entities")
    if job.ontology != "dod-bco" or report is None:
        raise HTTPException(404, "No entity extraction report is available for this job yet")
    return JSONResponse(report, headers={"Content-Disposition": f'attachment; filename="dod-bco-entities-{job_id}.json"'})
