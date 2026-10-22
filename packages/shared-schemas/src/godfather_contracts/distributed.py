"""Bounded dependency graphs over existing portable, fenced workflow jobs."""

from typing import Annotated
from uuid import UUID

from pydantic import Field, model_validator

from godfather_contracts import Contract
from godfather_contracts.agents import WorkflowInput

DISTRIBUTED_RUNTIME = "distributed-context-v1"
TaskKey = Annotated[str, Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")]


class DistributedTaskSpec(Contract):
    key: TaskKey
    name: str = Field(min_length=1, max_length=200)
    agent_id: UUID
    agent_version: int = Field(ge=1)
    input: WorkflowInput
    node_ids: list[UUID] = Field(min_length=1, max_length=64)
    depends_on: list[TaskKey] = Field(default_factory=list, max_length=16)
    paid_consent: bool = False


class DistributedSubmission(Contract):
    workspace_id: UUID
    name: str = Field(min_length=1, max_length=200)
    instruction: str = Field(min_length=1, max_length=2000)
    node_ids: list[UUID] = Field(min_length=2, max_length=64)
    tasks: list[DistributedTaskSpec] = Field(min_length=2, max_length=16)
    final_task: TaskKey
    priority: int = Field(default=0, ge=-100, le=100)

    @model_validator(mode="after")
    def graph(self) -> "DistributedSubmission":
        selected = set(self.node_ids)
        if len(selected) != len(self.node_ids):
            raise ValueError("Select distinct participating nodes")
        seen: dict[str, set[str]] = {}
        used: set[UUID] = set()
        for task in self.tasks:
            nodes = set(task.node_ids)
            dependencies = set(task.depends_on)
            if task.key in seen or not dependencies <= seen.keys():
                raise ValueError("Task keys must be unique and dependencies must precede the task")
            if len(nodes) != len(task.node_ids) or not nodes <= selected:
                raise ValueError("Each task must use distinct nodes from the selected participants")
            if len(dependencies) != len(task.depends_on) or task.input.dependency_outputs:
                raise ValueError("Dependency outputs are assigned only by the coordinator")
            if len(self.instruction + "\nTask:\n" + task.input.instruction) > 4096:
                raise ValueError("Combined goal and task instruction must fit 4096 characters")
            ancestors = set(dependencies)
            for predecessor in dependencies:
                ancestors.update(seen[predecessor])
            seen[task.key] = ancestors
            used.update(nodes)
        if used != selected:
            raise ValueError("Every selected participant must be eligible for at least one task")
        if self.final_task not in seen or seen[self.final_task] != seen.keys() - {self.final_task}:
            raise ValueError(
                "The final task must depend on every other task, directly or indirectly"
            )
        if len(self.model_dump_json().encode("utf-8")) > 131072:
            raise ValueError("Distributed submissions must fit 128 KiB")
        return self
