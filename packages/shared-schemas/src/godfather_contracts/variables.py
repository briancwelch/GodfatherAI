"""Bounded literal references. Never evaluate code, paths, expressions or model output."""

import re

VARIABLE_RUNTIME = "task-variables-v1"
TOKEN = re.compile(r"\{\{\s*([A-Za-z][A-Za-z0-9_.-]*)\s*\}\}")
STATIC_VARIABLES = {
    "job.name",
    "job.goal",
    "workspace.id",
    "workspace.name",
    "task.key",
    "task.name",
    "agent.id",
    "agent.name",
    "agent.version",
    "model.identifier",
}


def references(text: str, custom: set[str]) -> list[str]:
    names = TOKEN.findall(text)
    remainder = TOKEN.sub("", text)
    if "{{" in remainder or "}}" in remainder:
        raise ValueError("Use a complete variable reference such as {{tasks.task1.output}}")
    for name in names:
        if name in STATIC_VARIABLES or name in {"vars." + key for key in custom}:
            continue
        if re.fullmatch(r"tasks\.[a-zA-Z][a-zA-Z0-9_-]{0,63}\.output", name):
            continue
        raise ValueError("Unknown variable; select a supported reference from the variable legend")
    return names


def output_tasks(text: str, custom: set[str]) -> list[str]:
    return list(
        dict.fromkeys(n.split(".")[1] for n in references(text, custom) if n.startswith("tasks."))
    )


def render_variables(text: str, values: dict[str, str]) -> str:
    return TOKEN.sub(lambda match: values[match[1]], text)
