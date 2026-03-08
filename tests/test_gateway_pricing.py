from __future__ import annotations

import importlib


PRICE_TIERS_JSON = (
    '[{"max_input_tokens":131072,"input_price_per_1k_tokens":0.0008,"output_price_per_1k_tokens":0.0048},'
    '{"max_input_tokens":262144,"input_price_per_1k_tokens":0.002,"output_price_per_1k_tokens":0.012},'
    '{"max_input_tokens":1048576,"input_price_per_1k_tokens":0.004,"output_price_per_1k_tokens":0.024}]'
)


def _load_gateway_main(monkeypatch):
    monkeypatch.setenv("AI_PRICE_CURRENCY", "CNY")
    monkeypatch.setenv("AI_PRICE_TIERS_JSON", PRICE_TIERS_JSON)
    monkeypatch.setenv("AI_INPUT_PRICE_PER_1K_TOKENS", "0")
    monkeypatch.setenv("AI_OUTPUT_PRICE_PER_1K_TOKENS", "0")
    module = importlib.import_module("apps.backend.gateway.app.main")
    return importlib.reload(module)


def test_estimate_usage_cost_uses_first_price_tier(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    cost = gateway_main._estimate_usage_cost({"prompt_tokens": 120000, "completion_tokens": 6000})
    assert cost["currency"] == "CNY"
    assert cost["pricing_mode"] == "tiered"
    assert cost["selected_tier"]["max_input_tokens"] == 131072
    assert cost["estimated_cost"] == 0.1248


def test_estimate_usage_cost_uses_second_price_tier(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    cost = gateway_main._estimate_usage_cost({"prompt_tokens": 200000, "completion_tokens": 10000})
    assert cost["currency"] == "CNY"
    assert cost["pricing_mode"] == "tiered"
    assert cost["selected_tier"]["max_input_tokens"] == 262144
    assert cost["estimated_cost"] == 0.52


def test_estimate_usage_cost_falls_back_to_last_tier(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    cost = gateway_main._estimate_usage_cost({"prompt_tokens": 1500000, "completion_tokens": 20000})
    assert cost["currency"] == "CNY"
    assert cost["selected_tier"]["max_input_tokens"] == 1048576
    assert cost["estimated_cost"] == 6.48
