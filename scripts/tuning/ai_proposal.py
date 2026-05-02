import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    target_keys: Dict[str, Any]
    rationale: str
    confidence: float
    rollback_guard: Dict[str, Any]


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def propose_hold_override_relaxation(
    *,
    current_hold_cfg: Dict[str, Any],
    baseline_counts: Dict[str, Any],
    baseline_quality: Optional[Dict[str, Any]] = None,
    proposal_id: str = "hold_override_relax_001",
) -> Proposal:
    """
    Very small-scope proposal generator:
      - If hold_by_ai_decision dominates and recent opened samples are not worse,
        propose tiny relaxation of hold_avoidance_override thresholds.
      - Keep bounded values to avoid safety regressions.
    """
    hold_reason_ratio = float(baseline_counts.get("hold_ratio", 0.0) or 0.0)
    open_ratio = float(baseline_counts.get("open_ratio", 0.0) or 0.0)

    cur_min_abs_sent = float(current_hold_cfg.get("hold_avoidance_override_min_abs_sentiment", 0.06) or 0.06)
    cur_mi_quality = float(current_hold_cfg.get("hold_avoidance_override_min_mi_quality_score", 0.62) or 0.62)
    cur_require_align = bool(current_hold_cfg.get("hold_avoidance_override_require_mi_trend_alignment", True))

    # Conservative tiny deltas.
    # Bounds chosen so it doesn't become "cheap to override".
    min_abs_lo, min_abs_hi = 0.03, 0.08
    mi_q_lo, mi_q_hi = 0.45, 0.70

    # Default: only loosen a bit when hold dominates.
    tighten_guard_ok = False
    if baseline_quality and baseline_quality.get("avg_score_h") is not None:
        # If opened quality is acceptable (>=0), allow relaxation.
        tighten_guard_ok = float(baseline_quality.get("avg_score_h") or 0.0) >= 0.0
    else:
        # If quality is missing, still allow very small relax when hold ratio is high.
        tighten_guard_ok = hold_reason_ratio >= 0.6

    proposed_min_abs = cur_min_abs_sent
    proposed_mi_quality = cur_mi_quality
    proposed_require_align = cur_require_align

    # If hold is too dominant OR open ratio is tiny, relax.
    if hold_reason_ratio >= 0.6 or (hold_reason_ratio >= 0.45 and open_ratio <= 0.15):
        if tighten_guard_ok:
            proposed_min_abs = _clamp(cur_min_abs_sent - 0.005, min_abs_lo, min_abs_hi)
            proposed_mi_quality = _clamp(cur_mi_quality - 0.04, mi_q_lo, mi_q_hi)
            # Trend alignment requirement can reduce overrides in sideways markets.
            proposed_require_align = False

    # If nothing changes, still return an "empty change" proposal with low confidence.
    changed = (
        abs(proposed_min_abs - cur_min_abs_sent) > 1e-9
        or abs(proposed_mi_quality - cur_mi_quality) > 1e-9
        or proposed_require_align != cur_require_align
    )

    if not changed:
        rationale = (
            "hold_avoidance_override already appears balanced for the current window; "
            "no bounded relaxation is suggested to avoid safety regression."
        )
        conf = 0.35
        rollback_guard = {
            "min_open_count_delta": -1,  # allow no-op
            "max_guard_deterioration": 0.0,
        }
    else:
        rationale = (
            f"baseline shows hold_by_ai_decision_ratio={hold_reason_ratio:.2f} and open_ratio={open_ratio:.2f}. "
            f"To reduce HOLD suppression without disabling risk logic, apply tiny bounds relaxation: "
            f"min_abs_sentiment {cur_min_abs_sent:.3f}->{proposed_min_abs:.3f}, "
            f"min_mi_quality_score {cur_mi_quality:.3f}->{proposed_mi_quality:.3f}, "
            f"require_mi_trend_alignment {cur_require_align}->{proposed_require_align}. "
            f"Opened quality check (avg_score_h={baseline_quality.get('avg_score_h') if baseline_quality else None}) "
            f"gates whether we loosen."
        )
        conf = 0.72 if tighten_guard_ok else 0.55
        rollback_guard = {
            # These are placeholders; actual validation thresholds live in tuning_channel.
            "min_open_count_delta": 1,
            "min_open_score_delta": -0.01,
            "max_bad_guard_delta": 0,
        }

    return Proposal(
        proposal_id=proposal_id,
        target_keys={
            "hold_avoidance_override_min_abs_sentiment": proposed_min_abs,
            "hold_avoidance_override_min_mi_quality_score": proposed_mi_quality,
            "hold_avoidance_override_require_mi_trend_alignment": proposed_require_align,
        },
        rationale=rationale,
        confidence=conf,
        rollback_guard=rollback_guard,
    )

