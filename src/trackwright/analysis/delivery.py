"""The delivery plan (TW-1613): from a measured master to a target loudness and ceiling, in Cubase Elements.

Built on what TW-1612 measured on a whole episode (``experiments/tw1612/``):

- the Stereo Out fader moves the integrated loudness by exactly its gain; it goes up to +6.02 dB;
- Stereo Out's insert slots 1-6 are **before** the fader and 7-8 **after** it: a ceiling must sit in 7 or 8;
- the Brickwall Limiter lets about 0.24 dB of intersample peaks through with DIC on;
- MP3 128 kbps raised the true peak by 0.78-0.82 dB (on another mix, TW-1613, it lowered it by 0.42 dB: the
  rise is a cautious margin, not a constant).

So: gain = target - measured; the delivered true peak is predicted as the master's plus the gain plus the
encoding's rise; when it would pass the ceiling, a limiter goes in a post-fader slot with its threshold that
much under the ceiling. Every margin is a measurement of one episode, not a law: the delivered file is always
measured again, and a plan that needs a lot of limiting says so, since that is a job for dynamics upstream.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

FADER_MAX_DB = 6.0206  # Cubase: volume process 1.0 (read by cubase_convert_value, TW-1613)
INTERSAMPLE_DB = 0.24  # what the Brickwall Limiter lets through with DIC on (TW-1612)
ENCODING_RISE_DB = {"mp3": 0.82, "aac": 0.82}  # MP3 128 kbps, TW-1612; AAC assumed alike, not measured
UNMEASURED_ENCODINGS = frozenset({"aac"})
HEAVY_LIMITING_DB = 6.0  # more peak reduction than this is a job for compression or leveling upstream
LIMITING_COST_NOTE = "TW-1612: 3 dB of peak reduction cost 1.2 LU of loudness"


@dataclass(frozen=True, slots=True)
class DeliveryPlan:
    target_lufs: float | None
    tolerance_lu: float | None
    ceiling_dbtp: float | None
    codec: str
    measured_lufs: float
    measured_true_peak: float
    fader_now_db: float
    gain_db: float
    """Change to the Stereo Out fader."""
    fader_db: float
    """The fader setting the plan asks for (at most FADER_MAX_DB)."""
    reachable: bool
    """The target can be reached with the fader alone (before any limiting)."""
    predicted_lufs: float
    predicted_true_peak: float
    """Of the delivered file, before any limiter: master + gain + encoding rise."""
    limiter: bool
    threshold_db: float | None
    peak_reduction_db: float | None
    warnings: list[str] = field(default_factory=list)


def plan_delivery(
    *,
    measured_lufs: float,
    measured_true_peak: float,
    fader_now_db: float,
    target_lufs: float | None,
    tolerance_lu: float | None,
    ceiling_dbtp: float | None,
    codec: str,
) -> DeliveryPlan:
    """What to do on Stereo Out to deliver ``codec`` at ``target_lufs`` under ``ceiling_dbtp``."""
    warnings: list[str] = []
    rise = ENCODING_RISE_DB.get(codec, 0.0)
    if codec in UNMEASURED_ENCODINGS:
        warnings.append(f"the true-peak rise of {codec} was not measured: the MP3 figure ({rise} dB) is used")
    gain = 0.0 if target_lufs is None else target_lufs - measured_lufs
    if target_lufs is None:
        warnings.append("the platform publishes no loudness target: the level is left as it is")
    wanted = fader_now_db + gain
    fader = min(wanted, FADER_MAX_DB)
    reachable = wanted <= FADER_MAX_DB
    if not reachable:
        warnings.append(
            f"the fader would need {wanted:+.2f} dB and goes up to {FADER_MAX_DB:+.2f}: raise the tracks' faders "
            "first, or level the voices upstream (podcast-dialogue-leveling)"
        )
    applied = fader - fader_now_db
    predicted_tp = measured_true_peak + applied + rise
    limiter = ceiling_dbtp is not None and predicted_tp > ceiling_dbtp
    threshold = reduction = None
    if limiter and ceiling_dbtp is not None:
        threshold = math.floor((ceiling_dbtp - INTERSAMPLE_DB - rise) * 10) / 10
        reduction = round(measured_true_peak + applied - threshold, 2)
        warnings.append(f"limiting lowers the loudness ({LIMITING_COST_NOTE}): expect a second round")
        if reduction > HEAVY_LIMITING_DB:
            warnings.append(
                f"{reduction:.1f} dB of peak reduction is a lot for a limiter: the peaks are far above the "
                "speech; compression or leveling upstream would sound better"
            )
    if ceiling_dbtp is None:
        warnings.append("the platform publishes no true-peak ceiling")
    return DeliveryPlan(
        target_lufs=target_lufs,
        tolerance_lu=tolerance_lu,
        ceiling_dbtp=ceiling_dbtp,
        codec=codec,
        measured_lufs=measured_lufs,
        measured_true_peak=measured_true_peak,
        fader_now_db=round(fader_now_db, 2),
        gain_db=round(applied, 2),
        fader_db=round(fader, 2),
        reachable=reachable,
        predicted_lufs=round(measured_lufs + applied, 2),
        predicted_true_peak=round(predicted_tp, 2),
        limiter=limiter,
        threshold_db=threshold,
        peak_reduction_db=reduction,
        warnings=warnings,
    )
