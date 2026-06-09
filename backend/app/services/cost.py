"""Cost model.

ElevenLabs bills a conversation as the sum of:

* **call minutes** — a per-minute Agents charge (≈ $0.08/min, plan-dependent),
* **LLM tokens** — invoiced separately on top of the per-minute charge,
* **TTS** — characters / audio seconds synthesized,
* **ASR** — speech-to-text input seconds.

The ``charging`` object in the webhook carries the authoritative numbers. When a
field is present we use it; otherwise we estimate from call duration and token
counts so a cost is always available (useful for the offline simulator).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings
from app.schemas.elevenlabs import MetadataModel

settings = get_settings()

# Fallback unit economics (USD) used only when the payload omits explicit charges.
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
            if isinstance(value, (int, float)) and any(s in key.lower() for s in key_substrings):
                total += int(value)
            else:
                total += _sum_tokens(value, key_substrings)
    elif isinstance(obj, list):
        for item in obj:
            total += _sum_tokens(item, key_substrings)
    return total


def compute_cost(metadata: MetadataModel) -> CostBreakdown:
    """Derive a USD cost breakdown from conversation metadata."""
    duration_minutes = max(metadata.call_duration_secs, 0) / 60.0
    charging = metadata.charging

    input_tokens = 0
    output_tokens = 0
    llm_usd = 0.0
    tts_usd = 0.0
    asr_usd = 0.0

    if charging is not None:
        if charging.llm_usage:
            input_tokens = _sum_tokens(charging.llm_usage, ("input", "prompt"))
            output_tokens = _sum_tokens(charging.llm_usage, ("output", "completion"))
        # Explicit LLM charge wins; otherwise estimate from tokens.
        if charging.llm_charge is not None:
            llm_usd = float(charging.llm_charge)
        else:
            llm_usd = (
                input_tokens / 1000.0 * _LLM_USD_PER_1K_INPUT
                + output_tokens / 1000.0 * _LLM_USD_PER_1K_OUTPUT
            )

    # Call charge: prefer explicit, else duration * configured per-minute rate.
    if charging is not None and charging.call_charge is not None:
        call_usd = float(charging.call_charge)
    else:
        call_usd = duration_minutes * settings.cost_per_call_minute_usd

    total_usd = round(call_usd + llm_usd + tts_usd + asr_usd, 6)

    return CostBreakdown(
        total_usd=total_usd,
        call_usd=round(call_usd, 6),
        llm_usd=round(llm_usd, 6),
        tts_usd=round(tts_usd, 6),
        asr_usd=round(asr_usd, 6),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        credits=metadata.cost,
    )
