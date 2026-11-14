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
from trackwright.config import Settings, config_path, load_settings
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


def cmd_bridge_stop(_args: argparse.Namespace, settings: Settings, *, wait: float = 5.0) -> int:
    """Stop the running bridge (SIGTERM to the pid it reports). Its MIDI ports disappear with it."""
    import os  # noqa: PLC0415
    import signal  # noqa: PLC0415
    import time  # noqa: PLC0415

    from trackwright.bridge import BridgeClient  # noqa: PLC0415
    from trackwright.errors import BridgeUnavailableError  # noqa: PLC0415

    try:
        status = BridgeClient(settings.bridge.socket_path).call(
            "bridge.status", timeout=settings.bridge.request_timeout
        )
    except BridgeUnavailableError:
        emit({"stopped": False, "reason": "the bridge is not running"})
        return 0
    pid = int(status["pid"])
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + wait
    while settings.bridge.socket_path.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    stopped = not settings.bridge.socket_path.exists()
    emit({"stopped": stopped, "pid": pid})
    return 0 if stopped else 1


def cmd_ping(args: argparse.Namespace, settings: Settings) -> int:
    from trackwright.bridge import BridgeClient  # noqa: PLC0415

    client = BridgeClient(settings.bridge.socket_path)
    timeout = settings.bridge.request_timeout
    hello = client.call("hello", timeout=timeout)
    pong = client.request("ping", {"echo": args.echo}, timeout=timeout)
    emit({"ok": bool(pong.get("ok")), "hello": hello, "ping": pong})
    return 0 if pong.get("ok") else 1


def cmd_script(args: argparse.Namespace, settings: Settings) -> int:
    from trackwright.cubase import SCRIPT_PATH, install_script, script_status  # noqa: PLC0415

    install_dir = args.dir or settings.script.install_dir
    source = args.file.resolve() if args.file else SCRIPT_PATH
    if args.action == "status":
        emit(script_status(install_dir, source).to_dict())
        return 0
    status, written = install_script(install_dir, apply=args.apply, source=source)
    payload = {**status.to_dict(), "written": written, "dry_run": not args.apply}
    if not args.apply and status.state != "up_to_date":
        payload["next_step"] = "re-run with --apply to copy the script, then restart Cubase"
    elif written:
        payload["next_step"] = "restart Cubase (it does not reload changed scripts by itself)"
    emit(payload)
    return 0


def make_service(settings: Settings, *, simulate: bool) -> Any:
    """The Cubase service backed by the bridge, or by the simulator with ``simulate``."""
    from trackwright.core.policy import WritePolicy  # noqa: PLC0415
    from trackwright.core.service import CubaseService  # noqa: PLC0415

    policy = WritePolicy.from_config(settings.writes)
    if simulate:
        from trackwright.fake import FakeCubase, FakeExports, FakeLauncher  # noqa: PLC0415

        cubase = FakeCubase()
        return CubaseService(cubase, policy, launcher=FakeLauncher(cubase), exports=FakeExports())  # type: ignore[arg-type]
    from trackwright.bridge import BridgeClient  # noqa: PLC0415
    from trackwright.hostport import BridgeHost  # noqa: PLC0415
    from trackwright.launcher import BridgeLauncher, CubaseLauncher  # noqa: PLC0415

    bridge_launcher = BridgeLauncher(settings.bridge, config_path=settings.source)
    host = BridgeHost(
        BridgeClient(settings.bridge.socket_path),
        read_timeout=settings.bridge.request_timeout,
        write_timeout=settings.bridge.write_timeout,
        ensure_bridge=bridge_launcher.ensure if settings.bridge.autostart else None,
    )
    return CubaseService(host, policy, launcher=CubaseLauncher(settings.cubase))


def cmd_serve(args: argparse.Namespace, settings: Settings) -> int:
    from trackwright.server import build_server  # noqa: PLC0415

    server = build_server(make_service(settings, simulate=args.simulate))
    logger.info("MCP server '{}' on stdio (simulate={})", server.name, args.simulate)
    server.run(transport="stdio")
    return 0


def cmd_doctor(_args: argparse.Namespace, settings: Settings) -> int:
    """Check every link of the chain and say what to do next."""
    from trackwright.doctor import run_doctor  # noqa: PLC0415

    report = run_doctor(settings)
    emit(report)
    return 0 if report["ok"] else 1


def cmd_setup(args: argparse.Namespace, settings: Settings) -> int:
    """Guided installation (TW-1301): every step is shown and confirmed before it is applied."""
    from trackwright.installer import ConsolePrompter, Setup  # noqa: PLC0415

    config_file, _explicit = config_path(args.config)
    result = Setup(
        settings, config_file, ConsolePrompter(), assume_yes=args.yes, writes=args.writes, save=args.save
    ).run()
    emit(result)
    return 0 if result["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trackwright", description="Trackwright: MCP server for Cubase.")
    parser.add_argument("--config", type=Path, help="configuration file (default: $TRACKWRIGHT_CONFIG or ~/.config)")
    parser.add_argument(
        "--log-level",
        type=str.upper,
        choices=["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"],
        help="override the configured log level",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    sub.add_parser("version", help="print the version").set_defaults(handler=cmd_version)
    sub.add_parser("config", help="print the effective configuration").set_defaults(handler=cmd_config)
    sub.add_parser("bridge", help="run the bridge daemon (keep it running)").set_defaults(handler=cmd_bridge)
    sub.add_parser("bridge-status", help="show the bridge status").set_defaults(handler=cmd_bridge_status)
    sub.add_parser("bridge-stop", help="stop the running bridge").set_defaults(handler=cmd_bridge_stop)
    serve = sub.add_parser("serve", help="run the MCP server on stdio (started by the MCP client)")
    serve.add_argument("--simulate", action="store_true", help="answer from the built-in Cubase simulator")
    serve.set_defaults(handler=cmd_serve)
    sub.add_parser("doctor", help="diagnose the whole chain and suggest fixes").set_defaults(handler=cmd_doctor)
    setup = sub.add_parser("setup", help="guided installation: Cubase script, configuration, Claude Code, doctor")
    setup.add_argument(
        "--yes",
        action="append",
        default=[],
        choices=["script", "config", "claude"],
        metavar="STEP",
        help="apply STEP (script, config or claude) without asking; repeat it for several steps",
    )
    setup.add_argument(
        "--writes", action=argparse.BooleanOptionalAction, help="new configuration: allow writes (default: ask; no)"
    )
    setup.add_argument(
        "--save", action=argparse.BooleanOptionalAction, help="new configuration: allow saving (default: ask; no)"
    )
    setup.set_defaults(handler=cmd_setup)
    script = sub.add_parser("script", help="install or check the Cubase MIDI Remote script")
    script.add_argument("action", choices=["status", "install"])
    script.add_argument("--dir", type=Path, help="override [script] install_dir")
    script.add_argument("--apply", action="store_true", help="really copy the file (default: dry run)")
    script.add_argument("--file", type=Path, help="install this script instead of the packaged one (experiments)")
    script.set_defaults(handler=cmd_script)
    ping = sub.add_parser("ping", help="check the round trip Python -> Cubase -> Python")
    ping.add_argument("--echo", default="hola-ñ-✓", help="text echoed back by the script")
    ping.set_defaults(handler=cmd_ping)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.config, missing_ok=args.command == "setup")
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
