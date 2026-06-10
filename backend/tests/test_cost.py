"""Tests for the cost model."""

from __future__ import annotations

from app.schemas.elevenlabs import ChargingModel, MetadataModel
from app.services.cost import compute_cost


def test_uses_explicit_charges_when_present():
    meta = MetadataModel(
        call_duration_secs=60,
        cost=120,
        charging=ChargingModel(
            call_charge=0.08,
            llm_charge=0.04,
            llm_usage={"cat": {"input_tokens": 1000, "output_tokens": 200}},
        ),
    )
    cost = compute_cost(meta)
    assert cost.call_usd == 0.08
    assert cost.llm_usd == 0.04
    assert cost.total_usd == 0.12
    assert cost.input_tokens == 1000
    assert cost.output_tokens == 200
    assert cost.credits == 120


def test_estimates_call_cost_from_duration_when_absent():
    meta = MetadataModel(call_duration_secs=120)  # 2 minutes
    cost = compute_cost(meta)
    # default rate is $0.08/min -> $0.16
    assert round(cost.call_usd, 4) == 0.16
    assert cost.llm_usd == 0.0


def test_estimates_llm_cost_from_tokens_when_no_explicit_charge():
    meta = MetadataModel(
        call_duration_secs=60,
        charging=ChargingModel(
            llm_usage={"cat": {"input_tokens": 2000, "output_tokens": 1000}}
        ),
    )
    cost = compute_cost(meta)
    # 2000/1000*0.0005 + 1000/1000*0.0015 = 0.001 + 0.0015 = 0.0025
    assert round(cost.llm_usd, 5) == 0.0025


def test_token_summing_is_recursive():
    meta = MetadataModel(
        call_duration_secs=10,
        charging=ChargingModel(
            llm_usage={
                "model_a": {"input_tokens": 100, "output_tokens": 10},
                "model_b": {"input_tokens": 50, "output_tokens": 5},
            }
        ),
    )
    cost = compute_cost(meta)
    assert cost.input_tokens == 150
    assert cost.output_tokens == 15
