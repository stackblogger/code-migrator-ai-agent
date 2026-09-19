"""Logging setup. Every module does `log = logging.getLogger(__name__)`.

Logs go to stderr, so the summaries printed on stdout stay clean.
Level comes from `--verbose` / `--quiet` or the `MIGRATOR_LOG_LEVEL` env var.
Set `MIGRATOR_LOG_FORMAT=json` to get one JSON object per line (useful for log tools).
"""

import json
import logging
import os
import sys

TEXT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def setup_logging(level: str | None = None) -> None:
    level = (level or os.environ.get("MIGRATOR_LOG_LEVEL", "INFO")).upper()
    handler = logging.StreamHandler(sys.stderr)
    if os.environ.get("MIGRATOR_LOG_FORMAT", "text").lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(TEXT_FORMAT, "%H:%M:%S"))

    logger = logging.getLogger("migrator")
    logger.handlers = [handler]
    logger.setLevel(level)
