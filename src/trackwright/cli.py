"""Command line entry point: ``trackwright <command>``.

Commands print JSON on stdout (so they can be scripted) and log to stderr. ``serve`` is the
exception: stdout belongs to the MCP stdio protocol, so it prints nothing itself.
Heavy modules are imported inside each handler to keep ``--help`` fast.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from loguru import logger

from trackwright import __version__
from trackwright.config import Settings, load_settings
from trackwright.errors import TrackwrightError
from trackwright.logs import configure_logging

Handler = Callable[[argparse.Namespace, Settings], int]


def emit(payload: Any) -> None:
    """Print a JSON document on stdout."""
    sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")


def cmd_version(_args: argparse.Namespace, _settings: Settings) -> int:
    emit({"trackwright": __version__})
    return 0


def cmd_config(_args: argparse.Namespace, settings: Settings) -> int:
    data = settings.model_dump(mode="json")
    data["bridge"]["socket_path"] = str(settings.bridge.socket_path)
    emit(data)
    return 0


def cmd_bridge(_args: argparse.Namespace, settings: Settings) -> int:
    from trackwright.bridge import run_bridge  # noqa: PLC0415

    run_bridge(settings.bridge)
    return 0


def cmd_bridge_status(_args: argparse.Namespace, settings: Settings) -> int:
    from trackwright.bridge import BridgeClient  # noqa: PLC0415

    emit(BridgeClient(settings.bridge.socket_path).call("bridge.status", timeout=settings.bridge.request_timeout))
    return 0


def cmd_ping(args: argparse.Namespace, settings: Settings) -> int:
    from trackwright.bridge import BridgeClient  # noqa: PLC0415

    client = BridgeClient(settings.bridge.socket_path)
    timeout = settings.bridge.request_timeout
    hello = client.call("hello", timeout=timeout)
    pong = client.request("ping", {"echo": args.echo}, timeout=timeout)
    emit({"ok": bool(pong.get("ok")), "hello": hello, "ping": pong})
    return 0 if pong.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trackwright", description="Trackwright: MCP server for Cubase.")
    parser.add_argument("--config", type=Path, help="configuration file (default: $TRACKWRIGHT_CONFIG or ~/.config)")
    parser.add_argument("--log-level", help="override the configured log level")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    sub.add_parser("version", help="print the version").set_defaults(handler=cmd_version)
    sub.add_parser("config", help="print the effective configuration").set_defaults(handler=cmd_config)
    sub.add_parser("bridge", help="run the bridge daemon (keep it running)").set_defaults(handler=cmd_bridge)
    sub.add_parser("bridge-status", help="show the bridge status").set_defaults(handler=cmd_bridge_status)
    ping = sub.add_parser("ping", help="check the round trip Python -> Cubase -> Python")
    ping.add_argument("--echo", default="hola-ñ-✓", help="text echoed back by the script")
    ping.set_defaults(handler=cmd_ping)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.config)
    except TrackwrightError as exc:
        configure_logging("INFO")
        logger.error("{}", exc)
        emit({"ok": False, "error": exc.to_dict()})
        return 2
    configure_logging(args.log_level or settings.logging.level, settings.logging.file)
    handler: Handler = args.handler
    try:
        return handler(args, settings)
    except TrackwrightError as exc:
        logger.error("{}", exc)
        emit({"ok": False, "error": exc.to_dict()})
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
