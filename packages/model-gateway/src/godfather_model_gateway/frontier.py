"""Native documented Responses and Messages APIs; no consumer authentication."""

from collections.abc import AsyncGenerator
from typing import Any

from godfather_contracts import ModelDeployment
from godfather_contracts.inference import InferenceInput, ToolCall
from godfather_contracts.workloads import CLOUD_IMAGE_MODELS
from pydantic import ValidationError

from godfather_model_gateway import Chunk, GatewayError, NativeModel, StructuredRequest
from godfather_model_gateway.providers import HTTPProvider


class FrontierProvider(HTTPProvider):
    def model(self, identifier: str, request: InferenceInput) -> NativeModel:
        model = next((m for m in self.config.model_catalog if m.identifier == identifier), None)
        if model is None or model.modality != "text":
            raise GatewayError("model_unavailable")
        if (
            request.parameters.max_tokens > model.max_output_tokens
            or len((request.prompt + (request.system or "")).encode())
            + request.parameters.max_tokens
            > model.context_window
            or (request.tools and not model.tools)
            or (
                (request.output_schema or isinstance(request, StructuredRequest))
                and not model.structured_output
            )
            or request.parameters.seed is not None
        ):
            raise GatewayError("invalid_request")
        return model

    async def discover(self) -> list[ModelDeployment]:
        # Only owner-declared operations are advertised. Listing an ID proves no feature parity.
        data = await self.request("GET", "models")
        try:
            identifiers = {m["id"] for m in data["data"]}
            return [
                ModelDeployment(
                    provider_id=self.config.id,
                    provider=self.config.provider,
                    connection_id=self.config.connection_id,
                    identifier=m.identifier,
                    declared_capabilities=self.config.declared_capabilities,
                    context_window=m.context_window if m.modality == "text" else None,
                    metadata_source="configured",
                    operations=["image_generation"]
                    if m.modality == "image"
                    else ["chat", "stream"]
                    + (["tools"] if m.tools else [])
                    + (["structured_output"] if m.structured_output else []),
                )
                for m in self.config.model_catalog
                if m.identifier in identifiers
                and (
                    m.modality != "image"
                    or m.identifier in CLOUD_IMAGE_MODELS.get(self.config.provider, ())
                )
            ]
        except (KeyError, TypeError, ValidationError):
            raise GatewayError("invalid_response") from None


class OpenAIProvider(FrontierProvider):
    def final(self, data: dict[str, Any], include_text: bool) -> Chunk:
        usage = data.get("usage") or {}
        calls = [
            ToolCall(id=c["call_id"], name=c["name"], arguments=c["arguments"])
            for c in data.get("output", [])
            if c.get("type") == "function_call"
        ]
        text = (
            "".join(
                p.get("text", "")
                for c in data.get("output", [])
                if c.get("type") == "message"
                for p in c.get("content", [])
                if p.get("type") == "output_text"
            )
            if include_text
            else ""
        )
        status = data.get("status")
        if status not in ("completed", "incomplete"):
            raise GatewayError("invalid_response")
        return Chunk(
            text=text,
            done=True,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            tool_calls=calls,
            cost_reconciliation_required=bool(
                (usage.get("input_tokens_details") or {}).get("cached_tokens")
            ),
            finish_reason="stop" if status == "completed" else "length",
        )

    async def infer(self, model: str, request: InferenceInput) -> AsyncGenerator[Chunk]:
        self.model(model, request)
        payload: dict[str, object] = {
            "model": model,
            "input": request.prompt,
            "store": False,
            "stream": request.stream,
            "max_output_tokens": request.parameters.max_tokens,
        }
        if request.system:
            payload["instructions"] = request.system
        if request.tools:
            payload["tools"] = [
                {"type": "function", **t.model_dump(), "strict": False} for t in request.tools
            ]
        if request.output_schema:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "result",
                    "schema": request.output_schema,
                    "strict": True,
                }
            }
        elif isinstance(request, StructuredRequest):
            payload["text"] = {"format": {"type": "json_object"}}
        finished = False
        try:
            async for data in self.documents(
                "POST", "responses", payload, "sse" if request.stream else "json"
            ):
                kind = data.get("type")
                if not request.stream:
                    yield self.final(data, True)
                    finished = True
                elif kind == "response.output_text.delta":
                    if finished:
                        raise GatewayError("invalid_response")
                    yield Chunk(text=data["delta"])
                elif kind in ("response.completed", "response.incomplete"):
                    yield self.final(data["response"], False)
                    finished = True
                elif kind in ("error", "response.failed"):
                    raise GatewayError("provider_unavailable")
            if not finished:
                raise GatewayError("invalid_response")
        except (KeyError, TypeError, ValueError, ValidationError):
            raise GatewayError("invalid_response") from None


class AnthropicProvider(FrontierProvider):
    async def infer(self, model: str, request: InferenceInput) -> AsyncGenerator[Chunk]:
        self.model(model, request)
        payload: dict[str, object] = {
            "model": model,
            "messages": [{"role": "user", "content": request.prompt}],
            "max_tokens": request.parameters.max_tokens,
            "stream": request.stream,
        }
        if request.system:
            payload["system"] = request.system
        if request.tools:
            payload["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in request.tools
            ]
        if request.output_schema:
            payload["output_config"] = {
                "format": {"type": "json_schema", "schema": request.output_schema}
            }
        elif isinstance(request, StructuredRequest):
            # Unlike JSON mode, Messages requires an explicit supported schema.
            raise GatewayError("invalid_request")
        import json

        counts: dict[str, Any] = {}
        calls: dict[int, dict[str, str]] = {}
        reason = None
        finished = False
        try:
            async for data in self.documents(
                "POST", "messages", payload, "sse" if request.stream else "json"
            ):
                kind = data.get("type")
                if not request.stream:
                    counts = data.get("usage", {})
                    blocks = data["content"]
                    reason = data["stop_reason"]
                    for i, block in enumerate(blocks):
                        if block["type"] == "text":
                            yield Chunk(text=block["text"])
                        elif block["type"] == "tool_use":
                            calls[i] = {
                                "id": block["id"],
                                "name": block["name"],
                                "arguments": json.dumps(block["input"]),
                            }
                    finished = True
                elif kind == "message_start":
                    counts = data["message"].get("usage", {})
                elif kind == "content_block_start" and data["content_block"]["type"] == "tool_use":
                    block = data["content_block"]
                    calls[data["index"]] = {
                        "id": block["id"],
                        "name": block["name"],
                        "arguments": "",
                    }
                elif kind == "content_block_delta":
                    delta = data["delta"]
                    if delta["type"] == "text_delta":
                        yield Chunk(text=delta["text"])
                    elif delta["type"] == "input_json_delta":
                        call = calls[data["index"]]
                        call["arguments"] += delta["partial_json"]
                        if len(call["arguments"]) > 32768:
                            raise GatewayError("output_limit")
                elif kind == "message_delta":
                    counts.update(data.get("usage", {}))
                    reason = data["delta"].get("stop_reason")
                elif kind == "message_stop":
                    finished = True
                elif kind == "error":
                    error = data.get("error", {}).get("type")
                    raise GatewayError(
                        "rate_limited" if error == "rate_limit_error" else "provider_unavailable"
                    )
            if not finished or reason is None:
                raise GatewayError("invalid_response")
            # Cache units are explicit provider usage, not estimates from output text.
            input_count = counts.get("input_tokens")
            if input_count is not None:
                input_count += counts.get("cache_read_input_tokens", 0) + counts.get(
                    "cache_creation_input_tokens", 0
                )
            yield Chunk(
                done=True,
                input_tokens=input_count,
                output_tokens=counts.get("output_tokens"),
                tool_calls=[ToolCall.model_validate(c) for c in calls.values()],
                cost_reconciliation_required=bool(
                    counts.get("cache_read_input_tokens")
                    or counts.get("cache_creation_input_tokens")
                ),
                finish_reason="length"
                if reason == "max_tokens"
                else "stop"
                if reason == "end_turn"
                else "other",
            )
        except (KeyError, TypeError, ValueError, ValidationError):
            raise GatewayError("invalid_response") from None
