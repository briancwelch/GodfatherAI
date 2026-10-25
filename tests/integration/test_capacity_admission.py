"""Durable admission uses contributed capacity, including after checkpoint recovery."""

from uuid import UUID

import pytest
from godfather_api.models import Node
from godfather_worker.desktop import Contribution

from tests.integration.test_inference import enable as enable_inference
from tests.integration.test_inference import inference_result
from tests.integration.test_inference import submit as submit_inference
from tests.integration.test_jobs import Harness
from tests.integration.test_jobs import h as h
from tests.integration.test_workflows import create, enable, expire, first_checkpoint, get, submit
from tests.workflow_helpers import sample_definition

pytestmark = pytest.mark.integration
GIB = 1024**3


def test_profile_memory_is_reserved_across_scheduler_ticks(h: Harness) -> None:
    deployment = enable_inference(h).model_copy(update={"estimated_ram_bytes": 4 * GIB})
    with h.database.sessions.begin() as session:
        node = session.get(Node, UUID(h.workers[0]["credential_id"]))
        assert node is not None
        node.resources = (
            Contribution(cpu_cores=4, ram_gib=6)
            .resources(h.registrations[0].resources)
            .model_dump(mode="json")
        )
        node.concurrency_limit = 2
        node.runtimes = {**node.runtimes, "model_deployments": [deployment.model_dump(mode="json")]}
    first = submit_inference(h, stream=False)
    second = submit_inference(h, stream=False)
    assert h.tick() == 1
    assignment = h.poll()
    assert assignment is not None and assignment["job"]["id"] == first["id"]
    assert assignment["deployment"]["estimated_ram_bytes"] == 4 * GIB
    assert h.tick() == 0 and h.get(second["id"])["status"] == "PENDING"
    h.start(assignment)
    h.report(assignment, "complete", result=inference_result(deployment))
    assert h.tick() == 1 and h.get(second["id"])["status"] == "ASSIGNED"


@pytest.mark.parametrize("constraint", ["budget", "unknown_memory", "unshared_gpu"])
def test_incompatible_recovery_keeps_checkpoint_and_stays_queued(
    h: Harness, constraint: str
) -> None:
    enable(h)
    enable(h, 1)
    spec = sample_definition()
    spec.requirements.ram_bytes = 4 * GIB
    if constraint == "unshared_gpu":
        spec.requirements.gpu_memory_bytes = 1
    job = submit(h, create(h, spec))
    h.tick()
    original = h.poll()
    assert original is not None
    checkpoint = first_checkpoint(h, original)
    with h.database.sessions.begin() as session:
        backup = session.get(Node, UUID(h.workers[1]["credential_id"]))
        assert backup is not None
        resources = Contribution(cpu_cores=4, ram_gib=2 if constraint == "budget" else 8).resources(
            h.registrations[0].resources
        )
        if constraint == "unknown_memory":
            resources.available_ram_bytes = None
        backup.resources = resources.model_dump(mode="json")
    expire(h, original)
    assert h.get(job["id"])["status"] == "PENDING" and h.poll(1) is None
    assert len(get(h, job["id"], "/checkpoints")) == 1
    assert get(h, job["id"])["checkpoint_version"] == checkpoint["checkpoint_version"]
    h.report(original, "renew", expected=409)
