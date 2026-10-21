"""Owner-configured isolated data workloads and explicit local image execution."""

import asyncio
import io
import json
import tempfile
from pathlib import Path

from godfather_agent_runtime import WorkflowError
from godfather_contracts import Contract
from godfather_contracts.agents import WorkflowInput, WorkflowStep
from godfather_contracts.workloads import WorkloadOutput
from godfather_model_gateway import GatewayError
from godfather_model_gateway.images import Automatic1111, ImageProviderConfig
from PIL import Image
from pydantic import Field, model_validator

from godfather_worker import data_program
from godfather_worker.coding import command, local_engine


class WorkloadConfig(Contract):
    image: str | None = Field(
        default=None, pattern=r"^(sha256:[a-f0-9]{64}|[^\s]+@sha256:[a-f0-9]{64})$"
    )
    images: ImageProviderConfig | None = None

    @model_validator(mode="after")
    def available_work(self) -> "WorkloadConfig":
        if self.image is None and self.images is None:
            raise ValueError("Configure a preinstalled Python sandbox image or local image backend")
        return self


async def inventory(config: WorkloadConfig) -> list[str]:
    runtimes = []
    if config.image:
        with tempfile.TemporaryDirectory(prefix="godfather-data-probe-") as temporary:
            root = Path(temporary)
            endpoint = await local_engine(root)
            code, _ = await command(
                [
                    "docker",
                    "--host",
                    endpoint,
                    "run",
                    "--rm",
                    "--pull=never",
                    "--network=none",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges:true",
                    "--memory=512m",
                    "--cpus=1",
                    "--pids-limit=32",
                    "--user=65534:65534",
                    "--entrypoint=python",
                    config.image,
                    "-c",
                    "import sys,csv,statistics,zipfile,xml.etree.ElementTree; "
                    "assert sys.version_info >= (3,12)",
                ],
                root,
                timeout=15,
            )
            if code:
                raise ValueError(
                    "Configured local image must contain Python 3.12+ standard library"
                )
        runtimes.append("data-workloads-v1")
    if config.images:
        try:
            models = await Automatic1111(config.images).models()
        except GatewayError:
            models = []
        if models:
            runtimes.extend(["local-images-v1", *("image-model:" + m for m in models)])
    return runtimes


async def isolated(
    config: WorkloadConfig, payload: dict[str, object], timeout: int
) -> WorkloadOutput:
    if config.image is None:
        raise WorkflowError("tool_permission")
    from uuid import uuid4

    with tempfile.TemporaryDirectory(prefix="godfather-data-") as temporary:
        root = Path(temporary)
        root.chmod(0o755)
        if "," in str(root):
            raise WorkflowError("tool_permission")
        program = root / "program.py"
        program.write_bytes(Path(__file__).with_name("data_program.py").read_bytes())
        request = root / "request.json"
        request.write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
        program.chmod(0o644)
        request.chmod(0o644)
        endpoint = await local_engine(root)
        name = "godfather-data-" + uuid4().hex
        try:
            code, output = await command(
                [
                    "docker",
                    "--host",
                    endpoint,
                    "run",
                    "--name",
                    name,
                    "--rm",
                    "--pull=never",
                    "--network=none",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges:true",
                    "--pids-limit=32",
                    "--memory=512m",
                    "--memory-swap=512m",
                    "--cpus=1",
                    "--user=65534:65534",
                    "--mount",
                    f"type=bind,source={root},target=/input,readonly",
                    "--tmpfs=/tmp:rw,size=16m,mode=1777",
                    "--env=PYTHONDONTWRITEBYTECODE=1",
                    "--entrypoint=python",
                    config.image,
                    "/input/program.py",
                    "/input/request.json",
                ],
                root,
                limit=8 * 1024 * 1024,
                timeout=timeout,
            )
            if code:
                raise WorkflowError("workflow_validation")
            try:
                return WorkloadOutput.model_validate_json(output)
            except ValueError:
                raise WorkflowError("workflow_validation") from None
        finally:
            await asyncio.shield(
                command(
                    ["docker", "--host", endpoint, "rm", "--force", name],
                    root,
                    limit=4096,
                    timeout=15,
                )
            )


async def execute(
    config: WorkloadConfig, payload: WorkflowInput, step: WorkflowStep, context: object
) -> WorkloadOutput:
    if step.kind != "image":
        return await isolated(
            config,
            {**payload.model_dump(mode="json"), "kind": step.kind, "context": context},
            step.timeout_seconds,
        )
    if config.images is None or payload.image is None:
        raise WorkflowError("model_unavailable")
    images = await Automatic1111(config.images).generate(payload.instruction, payload.image)
    files = []
    for i, raw in enumerate(images, 1):
        # Re-encode a bounded decoded bitmap; backend metadata/paths never become deliverables.
        try:
            with Image.open(io.BytesIO(raw)) as picture:
                if picture.size != (payload.image.width, payload.image.height):
                    raise ValueError("Unexpected dimensions")
                output = io.BytesIO()
                picture.convert("RGB").save(output, format="PNG")
        except (ValueError, OSError):
            raise WorkflowError("workflow_validation") from None
        files.append(data_program.download(f"image-{i}.png", "image/png", output.getvalue()))
    return WorkloadOutput(
        kind="image",
        title="Generated images",
        summary=(
            f"Generated {len(files)} images with {payload.image.model} "
            "on the explicitly selected local backend."
        ),
        analysis={"prompt": payload.instruction, "settings": payload.image.model_dump(mode="json")},
        files=files,
        limitations=[
            (
                "Cancellation stops accepting results; the local backend may fini"
                "sh an already submitted generation. No automatic replay or paid "
                "fallback."
            )
        ],
    )
