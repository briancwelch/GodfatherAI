"""Deterministic data, document safety, provider boundaries and owner opt-in."""

import asyncio
import base64
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from godfather_api.workloads import template
from godfather_contracts.agents import AgentDefinition, WorkflowInput, WorkflowStep
from godfather_contracts.workloads import Dataset, WorkloadOutput
from godfather_model_gateway import GatewayError
from godfather_model_gateway.images import Automatic1111, ImageProviderConfig
from godfather_worker import data_program
from godfather_worker.workloads import WorkloadConfig, isolated
from PIL import Image
from pydantic import ValidationError


def source(
    raw: bytes = (
        b"date,region,revenue\n2026-01-01,West,10\n2026-01-05,East,20\n2026-02-01,West,45\n"
    ),
    filename: str = "sales.csv",
) -> dict[str, str]:
    return Dataset(filename=filename, content_base64=base64.b64encode(raw).decode()).model_dump()


def analysis() -> dict[str, Any]:
    return data_program.analyze(
        {
            "dataset": source(),
            "analysis": {"group_by": "region", "date_column": "date", "value_column": "revenue"},
        }
    )


def test_calculations_groups_trends_and_missing_values() -> None:
    value = WorkloadOutput.model_validate(analysis())
    result = value.analysis
    assert result["row_count"] == 3
    assert result["metrics"] == {
        "revenue": {
            "count": 3,
            "missing": 0,
            "sum": 75,
            "mean": 25,
            "median": 20,
            "min": 10,
            "max": 45,
            "sample_stddev": pytest.approx(18.027756377),
            "anomaly_count": 0,
            "anomaly_rows": [],
        }
    }
    assert result["groups"] == [
        {"label": "East", "count": 1, "value": 20},
        {"label": "West", "count": 2, "value": 55},
    ]
    periods = result["periods"]
    assert isinstance(periods, list)
    assert periods[1]["change"] == 15 and periods[1]["change_percent"] == 50
    missing = data_program.analyze({"dataset": source(b"x,y\n1,a\n,b\n3,c\n"), "analysis": {}})
    assert missing["analysis"]["metrics"]["x"]["missing"] == 1
    anomaly = data_program.analyze({"dataset": source(("x\n" + "1\n" * 20 + "100\n").encode())})
    assert anomaly["analysis"]["metrics"]["x"]["anomaly_rows"] == [21]


@pytest.mark.parametrize(
    "raw", [b"x,x\n1,2", b"x\n1,2", b"[]", b'[{"x": {}}]', b'[{"x":1},{"y":2}]']
)
def test_invalid_datasets_are_rejected(raw: bytes) -> None:
    filename = "input.json" if raw.startswith(b"[") else "input.csv"
    with pytest.raises(ValueError):
        data_program.analyze({"dataset": source(raw, filename)})


def test_upload_boundaries_and_explicit_runtime_permissions() -> None:
    for name in ("../data.csv", "data.exe", "data.csv/secret"):
        with pytest.raises(ValidationError):
            Dataset(filename=name, content_base64="eA==")
    with pytest.raises(ValidationError):
        Dataset(filename="data.csv", content_base64=base64.b64encode(b"x" * (1024**2 + 1)).decode())
    for kind in ("analytics", "report", "image"):
        spec = template(kind)
        assert spec.requirements.model_selection is None
        broken = spec.model_dump()
        broken["permissions"] = []
        with pytest.raises(ValidationError):
            AgentDefinition.model_validate(broken)
    with pytest.raises(ValidationError):
        AgentDefinition.model_validate({**template("image").model_dump(), "retry": {"limit": 1}})
    with pytest.raises(ValidationError):
        WorkflowStep(id="report", kind="report", output_schema="workload")
    assert "dataset" not in WorkflowInput(instruction="old worker input").model_dump()


@pytest.mark.parametrize("format_", ["html", "markdown", "csv", "xlsx"])
def test_reports_preserve_metrics_source_and_safe_files(format_: str) -> None:
    prior = analysis()
    prior["analysis"]["source"] = "<script>alert(1)</script>"
    prior["analysis"]["metrics"]["=EVIL()"] = prior["analysis"]["metrics"].pop("revenue")
    output = WorkloadOutput.model_validate(
        data_program.report({"context": prior, "report_format": format_})
    )
    assert output.analysis == prior["analysis"]
    raw = base64.b64decode(output.files[0].content_base64)
    if format_ == "html":
        assert b"<script>" not in raw and b"&lt;script&gt;" in raw and b"<svg" in raw
    if format_ in ("csv", "xlsx"):
        if format_ == "xlsx":
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                raw = archive.read("xl/worksheets/sheet1.xml")
                assert b"<f>" not in raw
        assert b"'=" in raw or b"&#x27;=" in raw
    assert output.files[1].filename == "analysis.json"
    broken = output.files[0].model_dump()
    broken["checksum"] = "0" * 64
    from godfather_contracts.workloads import Download

    with pytest.raises(ValidationError):
        Download.model_validate(broken)


def test_xlsx_values_and_xml_expansion_boundary() -> None:
    raw = data_program.workbook([["value"], ["12"], ["18"]])
    value = data_program.analyze({"dataset": source(raw, "source.xlsx")})
    assert value["analysis"]["metrics"]["value"]["sum"] == 30
    with pytest.raises(ValueError):
        data_program.xml(b'<!DOCTYPE x [<!ENTITY x "boom">]><x>&x;</x>')
    with pytest.raises(ValueError):
        data_program.analyze(
            {
                "dataset": source(
                    json.dumps({"columns": ["x"], "rows": [[1, 2]]}).encode(), "query.json"
                )
            }
        )


def test_image_adapter_is_local_bounded_and_does_not_retry() -> None:
    for url in (
        "https://api.openai.com",
        "http://example.com",
        "http://127.0.0.1@evil.test",
        "http://127.0.0.1:7860/path",
    ):
        with pytest.raises(ValidationError):
            ImageProviderConfig(url=url, models=["local"])
    image = io.BytesIO()
    Image.new("RGB", (256, 256)).save(image, format="PNG")
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.method == "GET":
            return httpx.Response(200, json=[{"model_name": "local"}])
        body = json.loads(request.content)
        assert body["override_settings"]["sd_model_checkpoint"] == "local"
        assert body["save_images"] is False
        return httpx.Response(200, json={"images": [base64.b64encode(image.getvalue()).decode()]})

    from godfather_contracts.workloads import ImageSettings

    provider = Automatic1111(ImageProviderConfig(models=["local"]), httpx.MockTransport(respond))
    assert asyncio.run(
        provider.generate("prompt", ImageSettings(model="local", width=256, height=256))
    ) == [image.getvalue()]
    assert calls.count("/sdapi/v1/txt2img") == 1
    broken = Automatic1111(
        ImageProviderConfig(models=["local"]), httpx.MockTransport(lambda _: httpx.Response(503))
    )
    with pytest.raises(GatewayError):
        asyncio.run(broken.generate("prompt", ImageSettings(model="local")))


def test_real_networkless_worker_container(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import os

    image = os.environ.get("GODFATHER_CODING_TEST_IMAGE")
    if not image:
        pytest.skip("requires an explicitly selected, existing Python sandbox image")
    config = WorkloadConfig(image=image)
    result = asyncio.run(isolated(config, {"kind": "analytics", "dataset": source()}, 30))
    assert result.kind == "analytics" and result.analysis["row_count"] == 3
    report = asyncio.run(
        isolated(
            config, {"kind": "report", "context": result.model_dump(), "report_format": "html"}, 30
        )
    )
    assert report.kind == "report" and report.files[0].filename.endswith(".html")
