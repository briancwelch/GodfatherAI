"""Allowlisted JSON log fields; never serialize headers, URLs, SQL or exceptions."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "correlation_id": correlation_id.get(),
        }
        for key in ("method", "route", "status_code", "duration_ms", "error_type"):
            if hasattr(record, key):
                fields[key] = getattr(record, key)
        return json.dumps(fields, ensure_ascii=True)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("godfather")
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
    for name in ("uvicorn", "uvicorn.error"):
        server_logger = logging.getLogger(name)
        server_logger.handlers = [handler]
        server_logger.setLevel(level)
        server_logger.propagate = False
    # Driver and server log messages may contain raw URLs or exception details.
    # Our request middleware supplies the structured access/error records instead.
    for name in ("sqlalchemy.engine", "sqlalchemy.pool", "uvicorn.access"):
        logging.getLogger(name).disabled = True
    sql_logger = logging.getLogger("sqlalchemy")
    sql_logger.handlers = [logging.NullHandler()]
    sql_logger.propagate = False
    sql_logger.setLevel(logging.CRITICAL + 1)
