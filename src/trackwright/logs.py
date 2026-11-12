"""Logging with loguru.

Rules:
- Logs go to **stderr** (and optionally a file), never to stdout: with the stdio transport,
  stdout carries the MCP protocol.
- Libraries that use the standard ``logging`` module (``mcp``, ``anyio``...) are redirected
  into loguru through :class:`InterceptHandler`, so there is a single log stream.
"""

from __future__ import annotations

import inspect
import logging
import sys
from pathlib import Path
from typing import TextIO

from loguru import logger

LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}"


class InterceptHandler(logging.Handler):
    """Forward records from the standard ``logging`` module to loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame = inspect.currentframe()
        depth = 0
        # Skip the frames of the logging module itself so loguru reports the real caller.
        while frame is not None and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging(level: str = "INFO", file: Path | None = None, *, stream: TextIO | None = None) -> None:
    """(Re)configure loguru. ``stream`` defaults to ``sys.stderr``; it must never be stdout."""
    target = stream if stream is not None else sys.stderr
    if target is sys.stdout:
        raise ValueError("logging to stdout is forbidden: stdout carries the MCP stdio protocol")
    logger.remove()
    logger.add(target, level=level.upper(), format=LOG_FORMAT, backtrace=False, diagnose=False)
    if file is not None:
        file.parent.mkdir(parents=True, exist_ok=True)
        logger.add(file, level=level.upper(), format=LOG_FORMAT, rotation="10 MB", retention=5, encoding="utf-8")
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
