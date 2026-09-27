"""OpenAI entity calls use strict Structured Outputs and disable SDK retries.

The extraction runner owns the retry budget. Python still validates citations;
schema-conforming output alone does not establish source fidelity.
"""
import json

from app.services.llm.openai_compat import OpenAICompatProvider


class EntityModelRefusal(ValueError):
    pass


class EntityModelIncomplete(ValueError):
    pass


class OpenAIEntityProvider(OpenAICompatProvider):
    entity_parameters = {"api": "responses", "structured_outputs": "strict_json_schema",
                         "store": False, "max_output_tokens": 12000, "sdk_max_retries": 0}

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url, max_retries=0)
        return self._client

    async def structured(self, prompt, schema, **kwargs):
        response = await self._get_client().responses.create(
            model=self.model, input=prompt, store=False, max_output_tokens=12000,
            text={"format": {"type": "json_schema", "name": "bco_entities", "schema": schema, "strict": True}})
        if any(part.type == "refusal" for item in response.output if item.type == "message" for part in item.content):
            raise EntityModelRefusal("The model declined this extraction request.")
        if response.status != "completed" or not response.output_text:
            raise EntityModelIncomplete("The model did not return a complete entity response.")
        return json.loads(response.output_text)

    async def aclose(self):
        if self._client is not None:
            await self._client.close()
