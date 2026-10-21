"""Fixed, standard-library-only analytics/report program, run inside the worker sandbox.

There is no eval, generated code, user SQL, network client, or filesystem lookup
derived from data. stdin/stdout are the complete data boundary.
"""

import base64
import csv
import hashlib
import html
import io
import json
import math
import statistics
import sys
import zipfile
from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree as ET


def numeric(value: object) -> float | None:
    if value is None or isinstance(value, bool) or str(value).strip() == "":
        return None
    try:
        number = float(str(value))
    except ValueError:
        return None
    return number if math.isfinite(number) and abs(number) <= 1e100 else None


def xml(raw: bytes) -> ET.Element:
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("XML declarations are not supported")
    return ET.fromstring(raw)


def excel(raw: bytes) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if len(infos) > 200 or sum(i.file_size for i in infos) > 8 * 1024 * 1024:
            raise ValueError("Workbook expansion limit exceeded")
        if any("vba" in i.filename.lower() or "externallink" in i.filename.lower() for i in infos):
            raise ValueError("Macros and external workbook links are not supported")
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(n.itertext()) for n in xml(archive.read("xl/sharedStrings.xml"))]
        sheet = xml(archive.read("xl/worksheets/sheet1.xml"))
        result = []
        ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        for row in sheet.findall("x:sheetData/x:row", ns):
            cells = [""] * 64
            last = 0
            for cell in row:
                if cell.find("x:f", ns) is not None:
                    raise ValueError("Formula cells require an exported values-only dataset")
                letters = "".join(c for c in cell.attrib.get("r", "") if c.isalpha())
                index = 0
                for c in letters:
                    index = index * 26 + ord(c.upper()) - 64
                if not 1 <= index <= 64:
                    raise ValueError("Workbook column limit is 64")
                value = cell.findtext("x:v", default="", namespaces=ns)
                if cell.attrib.get("t") == "s":
                    value = strings[int(value)]
                elif cell.attrib.get("t") == "inlineStr":
                    value = "".join(cell.findtext("x:is/x:t", default="", namespaces=ns))
                cells[index - 1] = value
                last = max(last, index)
            result.append(cells[:last])
            if len(result) > 10001:
                raise ValueError("Dataset row limit is 10000")
        width = len(result[0]) if result else 0
        return [r + [""] * (width - len(r)) for r in result]


def dataset(data: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], str]:
    raw = base64.b64decode(data["content_base64"], validate=True)
    if not 0 < len(raw) <= 1024 * 1024:
        raise ValueError("Dataset must fit 1 MiB")
    filename = data["filename"]
    if filename.endswith(".json"):
        rows = json.loads(raw)
        # Structured SQL results may be exported as {columns, rows}; no SQL runs here.
        if isinstance(rows, dict) and set(rows) == {"columns", "rows"}:
            columns = rows["columns"]
            if not isinstance(columns, list) or len(set(columns)) != len(columns):
                raise ValueError("Invalid SQL result columns")
            if not isinstance(rows["rows"], list) or any(
                not isinstance(r, list) or len(r) != len(columns) for r in rows["rows"]
            ):
                raise ValueError("Invalid SQL result rows")
            rows = [dict(zip(columns, row, strict=True)) for row in rows["rows"]]
        if not isinstance(rows, list) or not rows or any(not isinstance(r, dict) for r in rows):
            raise ValueError("JSON must be an array of flat records or structured SQL results")
        columns = list(rows[0])
        if any(set(r) != set(columns) for r in rows):
            raise ValueError("All records must use the same columns")
    else:
        grid = (
            excel(raw)
            if filename.endswith(".xlsx")
            else list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
        )
        if len(grid) < 2:
            raise ValueError("Dataset needs a header and data rows")
        columns = grid[0]
        if any(len(row) != len(columns) for row in grid[1:]):
            raise ValueError("Dataset rows must match the header")
        rows = [dict(zip(columns, row, strict=True)) for row in grid[1:]]
    if not 1 <= len(columns) <= 64 or len(columns) != len(set(columns)):
        raise ValueError("Use 1-64 unique columns")
    if not 1 <= len(rows) <= 10000:
        raise ValueError("Use 1-10000 rows")
    if any(not isinstance(c, str) or not c.strip() or len(c) > 120 for c in columns):
        raise ValueError("Column names must be 1-120 characters")
    if any(isinstance(v, (dict, list)) or len(str(v)) > 4096 for r in rows for v in r.values()):
        raise ValueError("Use bounded scalar cells")
    return columns, rows, hashlib.sha256(raw).hexdigest()


def analyze(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload["dataset"]
    columns, rows, checksum = dataset(source)
    settings = payload.get("analysis") or {}
    for key in ("group_by", "date_column", "value_column"):
        if settings.get(key) and settings[key] not in columns:
            raise ValueError(f"Unknown {key} column")
    metrics: dict[str, Any] = {}
    for column in columns:
        present = [r[column] for r in rows if r[column] is not None and str(r[column]).strip()]
        parsed_values = [numeric(v) for v in present]
        if not present or any(v is None for v in parsed_values):
            continue
        numbers = [v for v in parsed_values if v is not None]
        mean = statistics.mean(numbers)
        deviation = statistics.stdev(numbers) if len(numbers) > 1 else 0.0
        anomalies = [
            i + 1
            for i, r in enumerate(rows)
            if (v := numeric(r[column])) is not None and deviation and abs(v - mean) > 3 * deviation
        ]
        metrics[column] = {
            "count": len(numbers),
            "missing": len(rows) - len(numbers),
            "sum": math.fsum(numbers),
            "mean": mean,
            "median": statistics.median(numbers),
            "min": min(numbers),
            "max": max(numbers),
            "sample_stddev": deviation,
            "anomaly_count": len(anomalies),
            "anomaly_rows": anomalies[:100],
        }
    value_column = settings.get("value_column")
    if value_column and value_column not in metrics:
        raise ValueError("Value column must contain finite numbers or missing cells")
    groups: list[dict[str, Any]] = []
    periods: list[dict[str, Any]] = []
    for key, target in (("group_by", groups), ("date_column", periods)):
        grouping_column = settings.get(key)
        if not grouping_column:
            continue
        buckets: dict[str, list[float]] = {}
        for row in rows:
            label = str(row[grouping_column]) if row[grouping_column] is not None else "(missing)"
            if key == "date_column":
                try:
                    label = datetime.fromisoformat(label.replace("Z", "+00:00")).strftime("%Y-%m")
                except ValueError:
                    raise ValueError("Date column must use ISO dates/timestamps") from None
            if label not in buckets and len(buckets) >= 100:
                raise ValueError("Grouping/period limit is 100")
            values = buckets.setdefault(label, [])
            if value_column:
                v = numeric(row[value_column])
                if v is not None:
                    values.append(v)
            else:
                values.append(1.0)
        previous: float | None = None
        for label, values in sorted(buckets.items()):
            total = math.fsum(values)
            item: dict[str, Any] = {"label": label, "count": len(values), "value": total}
            if key == "date_column":
                item["change"] = total - previous if previous is not None else None
                item["change_percent"] = (
                    (total - previous) / abs(previous) * 100 if previous else None
                )
            target.append(item)
            previous = total
    limitations = [
        ("Deterministic calculations only; the request is context, not executable instructions."),
        (
            "Numeric inference requires all nonmissing values in a column to "
            "be finite numbers; missing values are excluded."
        ),
        (
            "Anomalies use absolute z-score > 3 with sample standard deviatio"
            "n; this is a heuristic, not a causal finding."
        ),
        (
            "Dates are explicit ISO values grouped by calendar month; absent "
            "months are not filled, and changes compare observed periods."
        ),
    ]
    summary = (
        f"Analyzed {len(rows)} rows and {len(columns)} columns "
        f"from {source['filename']}. {len(metrics)} numeric columns."
    )
    for name, stats in metrics.items():
        summary += (
            f"\n{name}: sum {stats['sum']:.6g}; mean {stats['mean']:.6g}; "
            f"missing {stats['missing']}; anomaly candidates {stats['anomaly_count']}."
        )
    analysis = {
        "schema_version": 1,
        "source": source["filename"],
        "source_checksum": checksum,
        "created_at": datetime.now(UTC).isoformat(),
        "row_count": len(rows),
        "columns": columns,
        "metrics": metrics,
        "groups": groups,
        "periods": periods,
        "group_by": settings.get("group_by"),
        "value_column": value_column,
        "date_column": settings.get("date_column"),
    }
    return {
        "format_version": 1,
        "kind": "analytics",
        "title": "Dataset analysis",
        "summary": summary,
        "analysis": analysis,
        "files": [],
        "limitations": limitations,
    }


def safe_cell(value: object) -> str:
    text = str(value) if value is not None else ""
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text


def workbook(grid: list[list[object]]) -> bytes:
    # Inline strings only: no formulas, external links, macros or hidden executable content.
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    )
    for i, row in enumerate(grid, 1):
        sheet += f'<row r="{i}">'
        for j, value in enumerate(row):
            letters, n = "", j + 1
            while n:
                n, remainder = divmod(n - 1, 26)
                letters = chr(65 + remainder) + letters
            sheet += (
                f'<c r="{letters}{i}" t="inlineStr"><is><t>'
                f"{html.escape(safe_cell(value))}</t></is></c>"
            )
        sheet += "</row>"
    sheet += "</sheetData></worksheet>"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            (
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/con'
                'tent-types"><Default Extension="rels" ContentType="application/v'
                'nd.openxmlformats-package.relationships+xml"/><Default Extension'
                '="xml" ContentType="application/xml"/><Override PartName="/xl/wo'
                'rkbook.xml" ContentType="application/vnd.openxmlformats-officedo'
                'cument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/wo'
                'rksheets/sheet1.xml" ContentType="application/vnd.openxmlformats'
                '-officedocument.spreadsheetml.worksheet+xml"/></Types>'
            ),
        )
        archive.writestr(
            "_rels/.rels",
            (
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
                '2006/relationships"><Relationship Id="rId1" Type="http://schemas'
                ".openxmlformats.org/officeDocument/2006/relationships/officeDocu"
                'ment" Target="xl/workbook.xml"/></Relationships>'
            ),
        )
        archive.writestr(
            "xl/workbook.xml",
            (
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml'
                '/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDoc'
                'ument/2006/relationships"><sheets><sheet name="Analysis" sheetId'
                '="1" r:id="rId1"/></sheets></workbook>'
            ),
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            (
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
                '2006/relationships"><Relationship Id="rId1" Type="http://schemas'
                '.openxmlformats.org/officeDocument/2006/relationships/worksheet"'
                ' Target="worksheets/sheet1.xml"/></Relationships>'
            ),
        )
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return output.getvalue()


def download(filename: str, media_type: str, raw: bytes) -> dict[str, str]:
    return {
        "filename": filename,
        "media_type": media_type,
        "content_base64": base64.b64encode(raw).decode(),
        "checksum": hashlib.sha256(raw).hexdigest(),
    }


def report(payload: dict[str, Any]) -> dict[str, Any]:
    prior = payload["context"]
    if prior.get("kind") != "analytics" or prior.get("format_version") != 1:
        raise ValueError("Report requires a version 1 analysis")
    analysis = prior["analysis"]
    title = "Analysis report"
    summary = (
        f"# {title}\n\nCreated: {analysis['created_at']}\n\n## Executive summary\n\n"
        f"{prior['summary']}\n\n## Source and methodology\n\nSource: {analysis['source']}\n\n"
        f"SHA-256: {analysis['source_checksum']}\n\n"
        "Statistics use the finite numeric source values. Aggregations sum the selected "
        "value column or count records. No model interpretation was used.\n\n"
        "## Limitations\n\n" + "\n".join("- " + s for s in prior["limitations"])
    )
    grid: list[list[object]] = [
        [
            "Column",
            "Count",
            "Missing",
            "Sum",
            "Mean",
            "Median",
            "Min",
            "Max",
            "Sample stddev",
            "Anomaly candidates",
        ]
    ]
    for key, value in analysis["metrics"].items():
        grid.append(
            [
                key,
                *(
                    value[k]
                    for k in (
                        "count",
                        "missing",
                        "sum",
                        "mean",
                        "median",
                        "min",
                        "max",
                        "sample_stddev",
                        "anomaly_count",
                    )
                ),
            ]
        )
    for kind in ("groups", "periods"):
        if analysis[kind]:
            grid.append([kind, "count", "value", "change", "change_percent"])
            grid.extend(
                [
                    [r["label"], r["count"], r["value"], r.get("change"), r.get("change_percent")]
                    for r in analysis[kind]
                ]
            )
    grid.extend(
        [
            [],
            ["Source", analysis["source"]],
            ["Source SHA-256", analysis["source_checksum"]],
            ["Analysis created (UTC)", analysis["created_at"]],
            ["Summary", prior["summary"]],
            *[["Methodology / limitation", limitation] for limitation in prior["limitations"]],
        ]
    )
    table = (
        "<table><tbody>"
        + "".join(
            "<tr>" + "".join("<td>" + html.escape(safe_cell(c)) + "</td>" for c in row) + "</tr>"
            for row in grid
        )
        + "</tbody></table>"
    )
    chart = ""
    points = analysis["periods"] or analysis["groups"]
    maximum = max((abs(p["value"]) for p in points), default=1) or 1
    if points:
        chart = (
            '<h2>Observed values</h2><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 '
            + str(30 * len(points))
            + '">'
        )
        for i, point in enumerate(points):
            label = html.escape(str(point["label"])[:20])
            chart += (
                f'<text x="0" y="{i * 30 + 20}">{label}</text>'
                f'<rect x="210" y="{i * 30}" height="20" '
                f'width="{abs(point["value"]) / maximum * 300}" fill="#087F8C"/>'
                f'<text x="520" y="{i * 30 + 20}">{point["value"]:.6g}</text>'
            )
        chart += "</svg>"
    format_ = payload.get("report_format") or "html"
    if format_ == "html":
        body = (
            (
                '<!doctype html><html lang="en"><meta charset="utf-8"><meta http-'
                'equiv="Content-Security-Policy" content="default-src \'none\'; sty'
                "le-src 'unsafe-inline'\"><title>Analysis report</title><style>bod"
                "y{font:16px system-ui;max-width:1100px;margin:40px auto}td{paddi"
                "ng:6px;border:1px solid #ccc}pre{white-space:pre-wrap}</style><b"
                "ody><pre>"
            )
            + html.escape(summary)
            + "</pre>"
            + table
            + chart
            + "</body></html>"
        )
        file = download("analysis-report.html", "text/html", body.encode())
    elif format_ == "markdown":
        body = (
            summary
            + "\n\n## Supporting metrics\n\n"
            + "\n".join(
                " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in row)
                for row in grid
            )
        )
        file = download("analysis-report.md", "text/markdown", body.encode())
    elif format_ == "csv":
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerows([[safe_cell(c) for c in r] for r in grid])
        file = download("analysis-report.csv", "text/csv", stream.getvalue().encode("utf-8-sig"))
    elif format_ == "xlsx":
        file = download(
            "analysis-report.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            workbook(grid),
        )
    else:
        raise ValueError("Unsupported report format")
    return {
        **prior,
        "kind": "report",
        "title": title,
        "summary": summary,
        "files": [
            file,
            download(
                "analysis.json", "application/json", json.dumps(analysis, allow_nan=False).encode()
            ),
        ],
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    return analyze(payload) if payload["kind"] == "analytics" else report(payload)


if __name__ == "__main__":
    try:
        if len(sys.argv) == 2 and sys.argv[1] == "/input/request.json":
            with open("/input/request.json", "rb") as stream:
                raw_input = stream.read(2 * 1024 * 1024 + 1)
        else:
            raw_input = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
        document = json.loads(raw_input)
        print(json.dumps(run(document), allow_nan=False))
    except (ValueError, KeyError, TypeError, OverflowError, zipfile.BadZipFile, ET.ParseError):
        # Detailed data values never enter worker logs.
        print(
            json.dumps(
                {
                    "error": (
                        "Dataset/report validation failed; use flat CSV/JSON or a values-"
                        "only first Excel sheet within documented limits."
                    )
                }
            )
        )
        sys.exit(2)
