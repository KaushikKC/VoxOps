"""Tests for the cost model (ElevenLabs credits -> USD)."""

from __future__ import annotations

from app.schemas.elevenlabs import ChargingModel, MetadataModel
from app.services.cost import _USD_PER_CREDIT, compute_cost


def test_converts_credit_charges_to_usd():
    # Mirrors a real ElevenLabs payload: charges are in credits, llm_price in USD.
    meta = MetadataModel(
        call_duration_secs=204,
        cost=1381,
        charging=ChargingModel(
            call_charge=1135,
            llm_charge=246,
            llm_price=0.0246501,
            llm_usage={"cat": {"input_tokens": 1000, "output_tokens": 200}},
        ),
    )
    cost = compute_cost(meta)
    assert abs(cost.call_usd - 1135 * _USD_PER_CREDIT) < 1e-4  # ~0.1135
    assert abs(cost.llm_usd - 0.0246501) < 1e-4  # the real USD price wins over credits
    assert abs(cost.total_usd - (1135 * _USD_PER_CREDIT + 0.0246501)) < 1e-4
    assert cost.credits == 1381
    assert cost.input_tokens == 1000
    assert cost.output_tokens == 200
    # Sanity: a 3.4-minute call is cents, not hundreds of dollars.
    assert cost.total_usd < 1.0


def test_llm_credits_used_when_no_explicit_price():
    meta = MetadataModel(
        call_duration_secs=60,
        cost=600,
        charging=ChargingModel(call_charge=500, llm_charge=100),
    )
    cost = compute_cost(meta)
    assert round(cost.call_usd, 4) == round(500 * _USD_PER_CREDIT, 4)  # 0.05
    assert round(cost.llm_usd, 4) == round(100 * _USD_PER_CREDIT, 4)  # 0.01


def test_total_credits_used_when_no_breakdown():
    meta = MetadataModel(call_duration_secs=60, cost=1000)  # no charging object
    cost = compute_cost(meta)
    assert round(cost.total_usd, 4) == round(1000 * _USD_PER_CREDIT, 4)  # 0.1
    assert cost.credits == 1000


def test_duration_estimate_when_nothing_available():
    meta = MetadataModel(call_duration_secs=120)  # no cost, no charging
    cost = compute_cost(meta)
    # default rate is $0.08/min -> 2 min -> $0.16
    assert round(cost.call_usd, 4) == 0.16


def test_token_summing_is_recursive():
    meta = MetadataModel(
        call_duration_secs=10,
        cost=50,
        charging=ChargingModel(
            call_charge=40,
            llm_charge=10,
            llm_usage={
                "model_a": {"input_tokens": 100, "output_tokens": 10},
                "model_b": {"input_tokens": 50, "output_tokens": 5},
            },
        ),
    )
    cost = compute_cost(meta)
    assert cost.input_tokens == 150
    assert cost.output_tokens == 15
