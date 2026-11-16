"""Voice diagnostics (TW-1623): what a voice track's export suffers from, read-only.

The voice is an export of one voice track alone; ``start`` places it in project time so the moments to
listen to are project times. The analyses are :mod:`trackwright.analysis.voice`; nothing is treated here.
"""

from __future__ import annotations

from trackwright.analysis import decoded, probe
from trackwright.analysis.voice import diagnose
from trackwright.core.analyzing import AnalyzingMixin
from trackwright.core.ducking import DuckingMixin
from trackwright.core.models import VoiceDiagnosticsOut, VoiceFindingOut
from trackwright.errors import NotFoundError


class DiagnosingMixin(DuckingMixin, AnalyzingMixin):
    def voice_diagnostics(self, file: str, *, start: float = 0.0) -> VoiceDiagnosticsOut:
        path = self._audio_path(file)
        if not path.is_file():
            raise NotFoundError(f"not a file: {path}", code="NOT_FOUND")
        speech = self.voice_activity(file)
        regions = [(r.start, r.end) for r in speech.regions]
        with decoded(path) as readable:
            self.policy.check_analysis(probe(readable).seconds)
            found = diagnose(readable, regions, speech.noise_floor_db, speech.speech_level_db)
        out = VoiceDiagnosticsOut(file=str(path), start=start, seconds=found.seconds, sample_rate=found.rate,
                                  speech_seconds=found.speech_seconds, findings=[
            VoiceFindingOut(problem=f.problem, detected=f.detected, severity=f.severity,  # type: ignore[arg-type]
                            confidence=f.confidence, measures=f.measures,
                            times=[round(start + t, 2) for t in f.times], note=f.note)
            for f in found.findings
        ])  # fmt: skip
        if not regions:
            out.notes.append("no speech found: export the voice track alone (solo it)")
        out.notes.append("starting thresholds, checked on synthetic faults and one real episode: listen to the "
                         "times before treating anything")  # fmt: skip
        return out
