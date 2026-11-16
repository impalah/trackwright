"""Music beds, read-only (TW-1617): tempo, loop candidates and the ending of a music file.

The analysis is :mod:`trackwright.analysis.music`; this is its tool, with the file's identity and the cache
of TW-1608. A bed of a given length is rendered by ``cubase_render`` (process ``bed``).
"""

from __future__ import annotations

from pathlib import Path

import soundfile as sf

from trackwright.analysis import decoded, probe
from trackwright.analysis.music import analyze
from trackwright.core.analyzing import AnalyzingMixin
from trackwright.core.models import EndingOut, LoopOut, MusicAnalysisOut

MAX_LOOPS = 20


class MusicMixin(AnalyzingMixin):
    def music_analysis(self, file: str, *, top: int = 5) -> MusicAnalysisOut:
        """Tempo, loop candidates and the ending of a music file (a bed, a song)."""
        self.policy.check_analysis()
        path = self._audio_path(file)
        top = max(1, min(top, MAX_LOOPS))
        return self._cached(
            "music", path, 0.0, parameters={"top": top}, model=MusicAnalysisOut,
            compute=lambda: self._music(path, top), items=None, offset=0, limit=1,
        )  # fmt: skip

    def _music(self, path: Path, top: int) -> MusicAnalysisOut:
        with decoded(path) as readable:
            info = probe(readable)
            self.policy.check_analysis(info.seconds)
            data, rate = sf.read(str(readable), dtype="float64", always_2d=True)
        result = analyze(data, rate, top=top)
        tempo = result.tempo
        notes = []
        if not tempo.beats:
            notes.append("no clear beat: loop lengths are whole seconds, not bars; check them by ear")
        if not result.loops:
            notes.append("no loop candidate with a good seam: the user can mark a region to repeat")
        if result.ending is None:
            notes.append("no ending found (the music never falls below its typical level)")
        ending = result.ending
        return MusicAnalysisOut(
            file=str(path), sample_rate=info.rate, channels=info.channels, seconds=round(info.seconds, 4),
            bpm=tempo.bpm, tempo_confidence=tempo.confidence, beats=len(tempo.beats),
            first_beat=tempo.beats[0] if tempo.beats else None,
            loops=[LoopOut(start=lp.start, end=lp.end, seconds=round(lp.seconds, 4), bars=lp.bars, score=lp.score,
                           crossfade=lp.crossfade) for lp in result.loops],
            ending=EndingOut(start=ending.start, tail=ending.tail, end=ending.end) if ending else None,
            notes=notes,
        )  # fmt: skip
