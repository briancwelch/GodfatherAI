"""Owner-approved local Ollama model downloads through the existing job protocol."""

from typing import Any, Literal
from uuid import UUID

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer

from godfather_contracts import Contract, Label

INSTALL_RUNTIME = "model.install.v1"
SETUP_RUNTIME = "ollama.setup.v1"
PROVIDER_RUNTIME_PREFIX = "ollama-pull."
# Download catalog only, never presented as installed inventory. Official tag pages:
# https://ollama.com/library/qwen3:0.6b / qwen3:8b / llama3.2:3b
MODEL_CATALOG = [
    {
        "identifier": "qwen3:0.6b",
        "name": "Qwen 3 · 0.6B",
        "url": "https://ollama.com/library/qwen3:0.6b",
    },
    {"identifier": "qwen3:8b", "name": "Qwen 3 · 8B", "url": "https://ollama.com/library/qwen3:8b"},
    {
        "identifier": "llama3.2:3b",
        "name": "Llama 3.2 · 3B",
        "url": "https://ollama.com/library/llama3.2:3b",
    },
]


class ModelInstallInput(Contract):
    node_id: UUID
    provider_id: Label
    install_runtime: bool = False
    identifier: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}:[a-z0-9][a-z0-9._-]{0,63}$")

    @model_serializer(mode="wrap")
    def compatible_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        values: dict[str, Any] = handler(self)
        if not self.install_runtime:
            values.pop("install_runtime", None)
        return values


class ModelInstallRequest(ModelInstallInput):
    workspace_id: UUID
    confirm_download: Literal[True]


class ModelInstallResult(Contract):
    identifier: str
    provider_id: Label
    installed: Literal[True] = True
