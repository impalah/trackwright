"""Final quality control of an episode file (TW-1611): read-only, against the delivery profiles.

One reading of the file gives everything: header (format, channels, rate, duration), BS.1770 loudness and
true peak with the short-term series, and the window levels for long pauses. Each result is one item:

- **check** (objective, pass or fail): codec, channels, sample rate, bit rate, file size, loudness and
  true peak against each target's published values (with the source), duration against the approved range;
- **warning** (worth a listen, never a failure): long pauses, silence at the start or end, level changes
  between sections, samples at full scale;
- **manual** (cannot be verified from a mixdown): tracks that must not be in it, metadata, content.

A value a platform does not publish is reported as such (``info``), never filled in. With ``report`` the
result is also written to ``Trackwright/reports/`` as JSON and Markdown (needs ``[workspace] enabled``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from trackwright.analysis import (
    Levels,
    Loudness,
    SilenceCriteria,
    decoded,
    find_silences,
    measure,
    measure_loudness,
    probe,
)
from trackwright.analysis.qc import PCM, bitrate_kbps, codec_of, level_changes, loudest_moment
from trackwright.core.analyzing import AnalyzingMixin, audio_source
from trackwright.core.models import DeliveryProfileOut, QcItemOut, QcMomentOut, QcOut
from trackwright.core.profiling import ProfilesMixin
from trackwright.core.timefmt import format_seconds, parse_seconds
from trackwright.errors import PreconditionFailedError
from trackwright.workspace import Workspace, atomic_write

FULL_SCALE_DBFS = -0.01
MAX_LISTED = 20
EDGE_LISTEN = 10.0  # seconds of the start and of the end to listen to


def _fmt(value: float | None, unit: str) -> str | None:
    return None if value is None else f"{value:g} {unit}"


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" + ("" if number == 1 else "s")


def merge_moments(moments: list[QcMomentOut], within: float = 1.0) -> list[QcMomentOut]:
    """In time order, with moments closer than ``within`` seconds joined into one (their reasons together)."""
    merged: list[QcMomentOut] = []
    for moment in sorted(moments, key=lambda m: m.at_seconds):
        if merged and moment.at_seconds - merged[-1].at_seconds < within:
            merged[-1] = merged[-1].model_copy(update={"why": f"{merged[-1].why}; {moment.why}"})
        else:
            merged.append(moment)
    return merged


def _source(profile: DeliveryProfileOut, field: str) -> str | None:
    return next((s.url for s in profile.sources if field in s.covers), None)


@dataclass(frozen=True, slots=True)
class _Clock:
    """Project time of a file time: the file's first sample is at ``origin``."""

    origin: float

    def text(self, seconds: float) -> str:
        return format_seconds(self.origin + seconds)

    def moment(self, seconds: float, why: str) -> QcMomentOut:
        return QcMomentOut(at=self.text(seconds), at_seconds=round(self.origin + seconds, 3), why=why)


@dataclass(frozen=True, slots=True)
class _Measured:
    """What one reading of the file gave."""

    codec: str | None
    channels: int
    rate: int
    kbps: float | None
    size: int
    integrated: float | None
    true_peak: float | None


class _Target:
    """The checks of one delivery profile: one item per value the platform publishes."""

    def __init__(self, name: str, profile: DeliveryProfileOut) -> None:
        self.name, self.profile = name, profile
        self.items: list[QcItemOut] = []

    def check(self, item_id: str, title: str, *, ok: bool, measured: str | None, expected: str, field: str) -> None:
        self.items.append(
            QcItemOut(id=item_id, kind="check", status="pass" if ok else "fail", title=title, target=self.name,
                      measured=measured, expected=expected, source=_source(self.profile, field))
        )  # fmt: skip

    def info(self, item_id: str, title: str, measured: str | None, expected: str, field: str | None = None) -> None:
        self.items.append(
            QcItemOut(id=item_id, kind="check", status="info", title=title, target=self.name, measured=measured,
                      expected=expected, source=_source(self.profile, field) if field else None)
        )  # fmt: skip

    def format_checks(self, m: _Measured) -> None:
        p = self.profile
        if p.codecs:
            self.check("codec", "codec", ok=m.codec in p.codecs, measured=m.codec,
                       expected=" or ".join(p.codecs), field="codecs")  # fmt: skip
        layout = {1: "mono", 2: "stereo"}.get(m.channels)
        if p.channels:
            self.check("channels", "channels", ok=layout in p.channels, measured=layout or str(m.channels),
                       expected=" or ".join(p.channels), field="channels")  # fmt: skip
        if p.sample_rates:
            self.check("sample_rate", "sample rate", ok=m.rate in p.sample_rates, measured=f"{m.rate} Hz",
                       expected=" or ".join(f"{r} Hz" for r in p.sample_rates), field="sample_rates")  # fmt: skip
        if p.max_file_mb is not None:
            megabytes = round(m.size / 1e6, 1)
            self.check("file_size", "file size", ok=megabytes <= p.max_file_mb, measured=f"{megabytes:g} MB",
                       expected=f"<= {p.max_file_mb:g} MB", field="max_file_mb")  # fmt: skip
        self.bitrate_checks(m.kbps)

    def bitrate_checks(self, kbps: float | None) -> None:
        p = self.profile
        if kbps is None:
            return
        if p.min_bitrate_kbps is not None:
            self.check("min_bitrate", "bit rate (minimum)", ok=kbps >= p.min_bitrate_kbps * 0.98,
                       measured=f"{kbps:g} kbps", expected=f">= {p.min_bitrate_kbps} kbps",
                       field="min_bitrate_kbps")  # fmt: skip
        if p.max_bitrate_kbps is not None:
            self.check("max_bitrate", "bit rate (maximum)", ok=kbps <= p.max_bitrate_kbps * 1.02,
                       measured=f"{kbps:g} kbps", expected=f"<= {p.max_bitrate_kbps} kbps",
                       field="max_bitrate_kbps")  # fmt: skip
        if p.bitrate_kbps is not None and kbps < p.bitrate_kbps * 0.98:
            self.items.append(
                QcItemOut(id="bitrate", kind="warning", status="warn", title="bit rate under the recommended",
                          target=self.name, measured=f"{kbps:g} kbps", expected=f"{p.bitrate_kbps} kbps",
                          source=_source(p, "bitrate_kbps"))
            )  # fmt: skip

    def level_checks(self, m: _Measured) -> None:
        p = self.profile
        measured = _fmt(m.integrated, "LUFS") or "silence"
        if p.loudness_lufs is None:
            self.info("loudness", "integrated loudness", measured, "not published by the platform")
        elif p.loudness_tolerance_lu is None:
            self.info("loudness", "integrated loudness", measured,
                      f"{p.loudness_lufs:g} LUFS (no tolerance published)", "loudness_lufs")  # fmt: skip
        else:
            ok = m.integrated is not None and abs(m.integrated - p.loudness_lufs) <= p.loudness_tolerance_lu
            self.check("loudness", "integrated loudness", ok=ok, measured=measured,
                       expected=f"{p.loudness_lufs:g} ± {p.loudness_tolerance_lu:g} LUFS",
                       field="loudness_lufs")  # fmt: skip
        if p.true_peak_dbtp is None:
            self.info("true_peak", "true peak", _fmt(m.true_peak, "dBTP"), "not published by the platform")
        else:
            ok = m.true_peak is not None and m.true_peak <= p.true_peak_dbtp
            self.check("true_peak", "true peak", ok=ok, measured=_fmt(m.true_peak, "dBTP"),
                       expected=f"<= {p.true_peak_dbtp:g} dBTP", field="true_peak_dbtp")  # fmt: skip


def _warnings(
    levels: Levels, loud: Loudness, clock: _Clock, *, long_pause: float, jump_lu: float
) -> tuple[list[QcItemOut], list[QcMomentOut]]:
    """Long pauses, silence at the edges, level changes between sections and full-scale samples."""
    items: list[QcItemOut] = []
    moments: list[QcMomentOut] = []
    seconds = levels.seconds
    silences = find_silences(levels, SilenceCriteria(min_seconds=long_pause, padding_seconds=0.0))
    leading = [s for s in silences if s.digital and s.start <= levels.window]
    trailing = [s for s in silences if s.digital and s.end >= seconds - levels.window]
    for edge, title in ((leading, "silence at the start"), (trailing, "silence at the end")):
        items += [
            QcItemOut(id="edge_silence", kind="warning", status="warn", title=title,
                      measured=_fmt(round(s.seconds, 2), "s"), at=[clock.text(s.start)])
            for s in edge
        ]  # fmt: skip
    pauses = [s for s in silences if s not in leading and s not in trailing]
    if pauses:
        longest = sorted(pauses, key=lambda s: s.seconds, reverse=True)
        items.append(QcItemOut(id="long_pauses", kind="warning", status="warn",
                               title=f"{_count(len(pauses), 'pause')} of {long_pause:g} s or more",
                               measured=f"longest {longest[0].seconds:.1f} s",
                               at=[clock.text(s.start) for s in pauses[:MAX_LISTED]]))  # fmt: skip
        moments += [clock.moment(s.start, f"pause of {s.seconds:.1f} s") for s in longest[:5]]
    changes = level_changes(loud.short_term, loud.integrated_lufs, jump_lu=jump_lu)[:MAX_LISTED]
    if changes:
        title = f"{_count(len(changes), 'level change')} of {jump_lu:g} LU or more between 10 s sections"
        items.append(QcItemOut(id="level_changes", kind="warning", status="warn", title=title,
                               measured=", ".join(f"{c.change_lu:+.1f} LU" for c in changes),
                               at=[clock.text(c.at) for c in changes]))  # fmt: skip
        moments += [clock.moment(c.at, f"level change {c.change_lu:+.1f} LU") for c in changes]
    if loud.sample_peak_dbfs >= FULL_SCALE_DBFS:
        items.append(QcItemOut(id="full_scale", kind="warning", status="warn",
                               title="samples at full scale (possible clipping)",
                               measured=_fmt(loud.sample_peak_dbfs, "dBFS")))  # fmt: skip
    return items, moments


MANUAL = (
    ("excluded_tracks", "tracks that must not be in the file (a guide track, a muted take) cannot be seen in a "
                        "mixdown: check the mute and solo of every track, or run podcast-session-audit"),
    ("metadata", "tags, artwork and chapters are not checked"),
    ("content", "content (ads, bleeps, the right version of the intro) is not checked: listen"),
)  # fmt: skip


class QualityMixin(ProfilesMixin, AnalyzingMixin):
    def final_qc(
        self,
        file: str,
        *,
        start: str = "0",
        expected_seconds: float | None = None,
        targets: list[str] | None = None,
        long_pause_seconds: float = 3.0,
        jump_lu: float = 6.0,
        report: bool = False,
    ) -> QcOut:
        self.policy.check_analysis()
        if report:
            self.policy.check_workspace()
        path = Path(file).expanduser()
        if not path.is_absolute():
            raise PreconditionFailedError("file must be an absolute path", code="BAD_REQUEST", details={"file": file})
        origin = parse_seconds(start)
        if origin is None:
            raise PreconditionFailedError("start looks like '2.5', '1:30' or '0:01:30.000'", code="BAD_TIME")
        if long_pause_seconds <= 0 or jump_lu <= 0:
            raise PreconditionFailedError("long_pause_seconds and jump_lu must be positive", code="BAD_REQUEST")
        profiles = self._qc_targets(targets)
        with decoded(path) as readable:
            info = probe(readable)
            self.policy.check_analysis(info.seconds)
            loud = measure_loudness(readable)
            levels = measure(readable)
        cache, folder = self._analysis_cache(path)
        source = audio_source(cache.identify(path), origin, info.seconds, folder)
        codec = codec_of(path)
        size = path.stat().st_size
        measured = _Measured(codec=codec, channels=info.channels, rate=info.rate,
                             kbps=bitrate_kbps(size, info.seconds, codec), size=size,
                             integrated=loud.integrated_lufs, true_peak=loud.true_peak_dbtp)  # fmt: skip
        clock = _Clock(origin)
        items = self._duration_check(info.seconds, expected_seconds, codec)
        for name, profile in profiles.items():
            target = _Target(name, profile)
            target.format_checks(measured)
            target.level_checks(measured)
            items += target.items
        warnings, moments = _warnings(levels, loud, clock, long_pause=long_pause_seconds, jump_lu=jump_lu)
        items += warnings
        items += [QcItemOut(id=item_id, kind="manual", status="info", title=title) for item_id, title in MANUAL]
        moments.insert(0, clock.moment(0.0, "the start"))
        moments.append(clock.moment(max(0.0, info.seconds - EDGE_LISTEN), "the end"))
        loudest = loudest_moment(loud.short_term)
        if loudest is not None:
            moments.append(clock.moment(loudest, "the loudest 3 s"))
        moments = merge_moments(moments)
        failed = sum(1 for i in items if i.status == "fail")
        out = QcOut(
            file=str(path), format=info.format, subtype=info.subtype, codec=codec, sample_rate=info.rate,
            channels=info.channels, seconds=round(info.seconds, 4), bitrate_kbps=measured.kbps,
            integrated_lufs=loud.integrated_lufs, loudness_range_lu=loud.loudness_range_lu,
            true_peak_dbtp=loud.true_peak_dbtp, sample_peak_dbfs=loud.sample_peak_dbfs, targets=list(profiles),
            verdict="fail" if failed else "pass", failed=failed,
            warnings=sum(1 for i in items if i.status == "warn"), items=items, moments=moments, source=source,
        )  # fmt: skip
        if not profiles:
            out.notes.append("no delivery targets: give 'targets' or set delivery.targets in a profile")
        if source.project_saved_after:
            out.notes.append("the project was saved after this file was written: export again if it changed")
        if report:
            out.report = self._write_report(path, out)
        return out

    @staticmethod
    def _duration_check(seconds: float, expected: float | None, codec: str | None) -> list[QcItemOut]:
        if expected is None:
            return []
        tolerance = 0.01 if codec in PCM else 0.1  # MP3/AAC add encoder padding (TW-1601: +75 ms)
        ok = abs(seconds - expected) <= tolerance
        return [QcItemOut(id="duration", kind="check", status="pass" if ok else "fail",
                          title="duration of the approved range", measured=_fmt(round(seconds, 3), "s"),
                          expected=f"{expected:g} s ± {tolerance:g}")]  # fmt: skip

    def _qc_targets(self, targets: list[str] | None) -> dict[str, DeliveryProfileOut]:
        if targets is None:
            return {d.name: d for d in self.profile("resolve").delivery}
        available = {d.name: d for d in self.profile("delivery").delivery}
        unknown = [t for t in targets if t not in available]
        if unknown:
            raise PreconditionFailedError(
                f"unknown delivery profiles: {unknown}", code="BAD_REQUEST", details={"known": sorted(available)}
            )
        return {t: available[t] for t in targets}

    def _write_report(self, path: Path, out: QcOut) -> list[str]:
        folder, why = self.project_folder()
        if folder is None:
            raise PreconditionFailedError(
                f"cannot write the report: {why}", code="NO_PROJECT_FOLDER", details={"reason": why}
            )
        space = Workspace(folder)
        reports = space.path / "reports"
        if not reports.is_dir():
            raise PreconditionFailedError(
                "the workspace has no reports/ folder: create it with cubase_workspace (action 'init')",
                code="NO_WORKSPACE",
                details={"path": str(reports)},
            )
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        base = reports / f"qc-{path.stem}-{stamp}"
        json_path, md_path = base.with_suffix(".json"), base.with_suffix(".md")
        out.report = [str(json_path), str(md_path)]
        atomic_write(json_path, (out.model_dump_json(indent=2) + "\n").encode("utf-8"))
        atomic_write(md_path, report_markdown(out).encode("utf-8"))
        return out.report


def report_markdown(out: QcOut) -> str:
    """A human-readable report of a final QC (English; the skill translates it in the conversation)."""
    lines = [
        f"# Final QC: {Path(out.file).name}",
        "",
        f"- **Verdict:** {out.verdict} ({out.failed} failed, {out.warnings} warnings)",
        f"- **File:** `{out.file}`" + (f" (SHA-256 `{out.source.sha256[:16]}…`)" if out.source else ""),
        f"- **Format:** {out.format} {out.subtype}, {out.codec or '?'}, {out.sample_rate} Hz, {out.channels} ch, "
        f"{out.seconds:g} s" + (f", {out.bitrate_kbps:g} kbps" if out.bitrate_kbps else ""),
        f"- **Loudness:** {out.integrated_lufs} LUFS integrated, LRA {out.loudness_range_lu} LU, true peak "
        f"{out.true_peak_dbtp} dBTP",
        f"- **Targets:** {', '.join(out.targets) or 'none'}",
        "",
    ]
    for kind, heading in (("check", "Checks"), ("warning", "Warnings"), ("manual", "To check by hand")):
        rows = [i for i in out.items if i.kind == kind]
        if not rows:
            continue
        lines += [
            f"## {heading}",
            "",
            "| Status | Item | Target | Measured | Expected | At |",
            "|---|---|---|---|---|---|",
        ]
        for i in rows:
            where = ", ".join(i.at[:5]) + (" …" if len(i.at) > 5 else "")
            expected = f"[{i.expected}]({i.source})" if i.source and i.expected else (i.expected or "")
            cells = (i.status, i.title, i.target or "", i.measured or "", expected, where)
            lines.append("| " + " | ".join(c.replace("|", "/") for c in cells) + " |")
        lines.append("")
    lines += ["## Listen at", ""] + [f"- {m.at}: {m.why}" for m in out.moments] + [""]
    if out.notes:
        lines += ["## Notes", ""] + [f"- {n}" for n in out.notes]
    return "\n".join(lines).rstrip() + "\n"
