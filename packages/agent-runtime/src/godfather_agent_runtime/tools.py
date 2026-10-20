"""Trusted, deterministic read-only tool registry. No dynamic imports or code eval."""

import asyncio
from typing import Any

from godfather_contracts import Contract, ToolReference
from godfather_contracts.agents import AgentDefinition, Plan, PlanSummary
from pydantic import Field


class ToolError(Exception):
    pass


class ToolDefinition(Contract):
    reference: ToolReference
    permissions: list[str]
    timeout_seconds: int = Field(ge=1, le=60)
    side_effect: str = "read_only"
    retry_safety: str = "idempotent"
    environments: list[str] = ["windows", "macos", "linux"]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


PLAN_DESCRIBE = ToolDefinition(
    reference=ToolReference(name="plan.describe", version=1),
    permissions=["plan.read"],
    timeout_seconds=5,
    input_schema=Plan.model_json_schema(),
    output_schema=PlanSummary.model_json_schema(),
)
REGISTRY = {(PLAN_DESCRIBE.reference.name, PLAN_DESCRIBE.reference.version): PLAN_DESCRIBE}


def definition(reference: ToolReference) -> ToolDefinition:
    tool = REGISTRY.get((reference.name, reference.version))
    if tool is None:
        raise ToolError("Unsupported tool or version")
    return tool


def validate_agent(agent: AgentDefinition) -> None:
    for reference in agent.allowed_tools:
        tool = definition(reference)
        if not set(tool.permissions) <= set(agent.permissions):
            raise ToolError("Agent lacks required tool permissions")
        if tool.side_effect != "read_only" or tool.retry_safety != "idempotent":
            raise ToolError("Phase 06 supports only read-only idempotent tools")
    for permission in agent.permissions:
        if permission not in {p for t in REGISTRY.values() for p in t.permissions} | {
            "coding.workspace"
        }:
            raise ToolError("Unsupported execution permission")


def authorize(
    reference: ToolReference,
    agent: AgentDefinition,
    worker_tools: list[ToolReference],
    worker_permissions: list[str],
    os: str,
) -> ToolDefinition:
    tool = definition(reference)
    if (
        reference not in agent.allowed_tools
        or reference not in worker_tools
        or not set(tool.permissions) <= set(agent.permissions)
        or not set(tool.permissions) <= set(worker_permissions)
        or os not in tool.environments
    ):
        raise ToolError("Tool execution was not granted by both agent and node owner")
    return tool


def describe(plan: Plan) -> PlanSummary:
    return PlanSummary(title=plan.title, item_count=len(plan.items), outline="\n".join(plan.items))


async def execute_tool(
    reference: ToolReference,
    value: object,
    agent: AgentDefinition,
    worker_tools: list[ToolReference],
    worker_permissions: list[str],
    os: str,
) -> PlanSummary:
    tool = authorize(reference, agent, worker_tools, worker_permissions, os)
    async with asyncio.timeout(tool.timeout_seconds):
        result = describe(Plan.model_validate(value))
        return PlanSummary.model_validate(result.model_dump())
