"""Literal substitution and inferred DAG ordering, with no expression execution."""

from uuid import uuid4

import pytest
from godfather_contracts.distributed import DistributedSubmission
from godfather_contracts.variables import references, render_variables
from pydantic import ValidationError


def submission() -> dict[str, object]:
    nodes = [str(uuid4()), str(uuid4())]
    agent = str(uuid4())
    return {
        "workspace_id": str(uuid4()),
        "name": "Arithmetic",
        "instruction": "Solve each task",
        "node_ids": nodes,
        "final_task": "task2",
        "tasks": [
            {
                "key": "task1",
                "name": "First",
                "agent_id": agent,
                "agent_version": 1,
                "input": {"instruction": "Add 1+1"},
                "node_ids": [nodes[0]],
            },
            {
                "key": "task2",
                "name": "Second",
                "agent_id": agent,
                "agent_version": 1,
                "input": {"instruction": "Add 2+2 then add {{tasks.task1.output}}"},
                "node_ids": [nodes[1]],
            },
        ],
    }


def test_output_reference_infers_dependency_and_static_custom_variables() -> None:
    value = submission()
    parsed = DistributedSubmission.model_validate(value)
    assert parsed.tasks[1].depends_on == ["task1"]
    assert references("{{workspace.name}} {{vars.project}}", {"project"}) == [
        "workspace.name",
        "vars.project",
    ]


@pytest.mark.parametrize(
    "reference",
    [
        "tasks.task1.output",
        "tasks.task2.output",
        "tasks.missing.output",
        "tasks.task1.secret",
        "process.env.KEY",
        "vars.missing",
        "__import__('os')",
    ],
)
def test_self_forward_missing_and_unsupported_references_fail(reference: str) -> None:
    value = submission()
    value["tasks"][0]["input"]["instruction"] = "{{" + reference + "}}"  # type: ignore[index]
    with pytest.raises(ValidationError):
        DistributedSubmission.model_validate(value)


def test_literal_substitution_does_not_expand_values_or_execute_expressions() -> None:
    assert (
        render_variables("Add {{tasks.task1.output}} to 4", {"tasks.task1.output": "2"})
        == "Add 2 to 4"
    )
    assert (
        render_variables("{{vars.project}}", {"vars.project": "{{workspace.name}}"})
        == "{{workspace.name}}"
    )
    with pytest.raises(KeyError):
        render_variables("{{tasks.task1.output}}", {})
    with pytest.raises(ValueError):
        references("unfinished {{workspace.name", set())
