"""Resolve the existing Enrich provider without silently disabling extraction."""
from __future__ import annotations

import logging
import os

from app.config import settings
from app.models.llm_models import LLMProviderType
from app.services.llm.registry import REQUIRES_API_KEY, get_provider

logger = logging.getLogger(__name__)


def entity_provider(provider: str | None = None, model: str | None = None, api_key: str | None = None):
    name = (provider or settings.llm_provider).replace("-", "_")
    if name == "lm_studio":
        name = "lmstudio"
    try:
        kind = LLMProviderType(name)
    except ValueError as exc:
        raise ValueError("Choose an enabled LLM provider for entity extraction.") from exc
    selected_model = model or settings.llm_model
    if not selected_model or not selected_model.strip():
        raise ValueError("Set an explicit model with --model or FOLIO_ENRICH_LLM_MODEL.")
    from app.api.routes.settings import _get_api_key_for_provider
    key = _get_api_key_for_provider(kind, api_key)
    # Standard SDK environment variables are also accepted for local CLI runs.
    if not key and not settings.require_user_api_key:
        key = os.environ.get({"google": "GOOGLE_API_KEY"}.get(name, name.upper() + "_API_KEY"))
    if REQUIRES_API_KEY.get(kind, True) and not key:
        raise ValueError(f"Configure {name}'s API key locally before running extraction. No model call was made.")
    if name == "openai":
        from app.bco.openai_entities import OpenAIEntityProvider
        return name, OpenAIEntityProvider(api_key=key, model=selected_model, base_url="https://api.openai.com/v1")
    return name, get_provider(kind, api_key=key, model=selected_model)


async def close_entity_provider(llm):
    """Release the client without losing a completed report to a cleanup error."""
    try:
        if hasattr(llm, "aclose"):
            await llm.aclose()
        elif getattr(llm, "_client", None) is not None:
            await llm._client.close()
    except Exception as exc:
        # Provider exception messages may contain credentials or request data.
        logger.warning("Entity provider cleanup failed (%s).", type(exc).__name__)
