"""Cost model.

ElevenLabs meters usage in **credits**, not per-call dollars (that's why a call
shows a credit cost in the API but no dollar amount on the free tier). The
``charging`` object reports:

* ``call_charge`` / ``llm_charge`` — the call and LLM cost **in credits**,
* ``llm_price`` — the LLM cost already expressed in **USD** (when available),
* ``cost`` (on metadata) — the total credits for the call.

We convert credits to an estimated USD using a representative per-credit rate
(``_USD_PER_CREDIT``), derived from observed ElevenLabs data
(``llm_price / llm_charge`` ≈ $0.0001/credit). The dollar figure is therefore an
estimate of what the consumed credits cost on a paid plan — the number an
operator reasons about — while the raw credit total is retained for fidelity.
When no charge breakdown is present we fall back to a duration/token estimate.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings
from app.schemas.elevenlabs import MetadataModel

settings = get_settings()

# Representative USD value of one ElevenLabs credit (plan-dependent). Derived from
# observed data: charging.llm_price / charging.llm_charge ≈ 0.0001 USD/credit.
_USD_PER_CREDIT = 0.0001

# Fallback unit economics (USD) used only when no charge/credit data is present.
_LLM_USD_PER_1K_INPUT = 0.0005
_LLM_USD_PER_1K_OUTPUT = 0.0015


@dataclass
class CostBreakdown:
    total_usd: float
    call_usd: float
    llm_usd: float
    tts_usd: float
    asr_usd: float
    input_tokens: int
    output_tokens: int
    credits: int | None


def _sum_tokens(obj: object, key_substrings: tuple[str, ...]) -> int:
    """Recursively sum integer leaves whose key contains one of the substrings."""
    total = 0
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, int | float) and any(s in key.lower() for s in key_substrings):
                total += int(value)
            else:
                total += _sum_tokens(value, key_substrings)
    elif isinstance(obj, list):
        for item in obj:
            total += _sum_tokens(item, key_substrings)
    return total


def compute_cost(metadata: MetadataModel) -> CostBreakdown:
    """Derive a USD cost breakdown from conversation metadata (credits → USD)."""
    duration_minutes = max(metadata.call_duration_secs, 0) / 60.0
    charging = metadata.charging
    total_credits = metadata.cost

    input_tokens = 0
    output_tokens = 0
    call_usd = 0.0
    llm_usd = 0.0
    tts_usd = 0.0
    asr_usd = 0.0

    if charging is not None:
        if charging.llm_usage:
            input_tokens = _sum_tokens(charging.llm_usage, ("input", "prompt"))
            output_tokens = _sum_tokens(charging.llm_usage, ("output", "completion"))
        # ElevenLabs charge fields are denominated in CREDITS.
        if charging.call_charge is not None:
            call_usd = float(charging.call_charge) * _USD_PER_CREDIT
        # For the LLM portion, the real USD price is most accurate when present;
        # otherwise convert its credit charge.
        if charging.llm_price is not None:
            llm_usd = float(charging.llm_price)
        elif charging.llm_charge is not None:
            llm_usd = float(charging.llm_charge) * _USD_PER_CREDIT

    # Fallback when no usable charge breakdown was provided.
    if call_usd == 0.0 and llm_usd == 0.0:
        if total_credits:
            call_usd = float(total_credits) * _USD_PER_CREDIT
        else:
            call_usd = duration_minutes * settings.cost_per_call_minute_usd
            llm_usd = (
                input_tokens / 1000.0 * _LLM_USD_PER_1K_INPUT
                + output_tokens / 1000.0 * _LLM_USD_PER_1K_OUTPUT
            )

    total_usd = round(call_usd + llm_usd + tts_usd + asr_usd, 6)

    return CostBreakdown(
        total_usd=total_usd,
        call_usd=round(call_usd, 6),
        llm_usd=round(llm_usd, 6),
        tts_usd=round(tts_usd, 6),
        asr_usd=round(asr_usd, 6),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        credits=total_credits,
    )
