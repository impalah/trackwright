from __future__ import annotations

import io
import logging
import sys
from pathlib import Path

import pytest
from loguru import logger

from trackwright.logs import configure_logging


def test_standard_logging_is_forwarded_to_loguru() -> None:
    buffer = io.StringIO()
    configure_logging("DEBUG", stream=buffer)
    logging.getLogger("mcp.server").warning("from a dependency %s", 42)
    assert "from a dependency 42" in buffer.getvalue()
    assert "WARNING" in buffer.getvalue()


def test_custom_standard_level_number_is_forwarded() -> None:
    buffer = io.StringIO()
    configure_logging("TRACE", stream=buffer)
    logging.getLogger("dep").log(5, "very verbose")
    assert "very verbose" in buffer.getvalue()


def test_nothing_is_written_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("DEBUG")
    logger.info("hello from trackwright")
    logging.getLogger("anyio").error("dependency error")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "hello from trackwright" in captured.err


def test_stdout_is_refused() -> None:
    with pytest.raises(ValueError, match="stdout"):
        configure_logging("INFO", stream=sys.stdout)


def test_log_file(tmp_path: Path) -> None:
    target = tmp_path / "logs" / "trackwright.log"
    configure_logging("INFO", target, stream=io.StringIO())
    logger.info("persisted")
    logger.complete()
    assert "persisted" in target.read_text(encoding="utf-8")
    configure_logging("INFO", stream=io.StringIO())  # release the file sink
