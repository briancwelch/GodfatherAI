"""Data-only local demonstration definition; no agent identity or node binding."""

from uuid import uuid4

from godfather_contracts.agents import AgentDefinition


def demonstration_definition(
    model: str = "fixture", name: str = "Read-only plan demonstration"
) -> AgentDefinition:
    return AgentDefinition.model_validate(
        {
            "name": name,
            "description": "Three predefined steps; no autonomous tool selection.",
            "requirements": {"model_selection": {"identifier": model, "stream": False}},
            "allowed_tools": [{"name": "plan.describe", "version": 1}],
            "permissions": ["plan.read"],
            "timeout_seconds": 600,
            "retry": {"limit": 1, "backoff_seconds": 0},
            "workflow": {
                "id": str(uuid4()),
                "version": 1,
                "steps": [
                    {
                        "id": "plan",
                        "kind": "model",
                        "instruction": "Generate a short structured plan for the user instruction.",
                        "output_schema": "plan",
                        "timeout_seconds": 180,
                        "parameters": {"max_tokens": 1024},
                    },
                    {
                        "id": "describe",
                        "kind": "tool",
                        "tool": {"name": "plan.describe", "version": 1},
                        "input_step": "plan",
                        "output_schema": "plan_summary",
                        "timeout_seconds": 5,
                    },
                    {
                        "id": "summary",
                        "kind": "model",
                        "instruction": "Summarize the validated plan in one short sentence.",
                        "input_step": "describe",
                        "output_schema": "text",
                        "timeout_seconds": 180,
                        "parameters": {"max_tokens": 512},
                    },
                ],
            },
        }
    )
