from __future__ import annotations

from typing import Any

from .gateway_config import PriceTier


def resolve_price_tier(prompt_tokens: int, *, llm_price_tiers: list[PriceTier]) -> PriceTier | None:
    if not llm_price_tiers:
        return None
    for tier in llm_price_tiers:
        if tier.max_input_tokens is None or prompt_tokens <= tier.max_input_tokens:
            return tier
    return llm_price_tiers[-1]


def estimate_usage_cost(
    usage: dict[str, Any],
    *,
    llm_price_tiers: list[PriceTier],
    llm_input_price_per_1k_tokens: float,
    llm_output_price_per_1k_tokens: float,
    llm_price_currency: str,
) -> dict[str, Any]:
    prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    selected_tier = resolve_price_tier(prompt_tokens, llm_price_tiers=llm_price_tiers)
    if selected_tier is not None:
        input_price = selected_tier.input_price_per_1k_tokens
        output_price = selected_tier.output_price_per_1k_tokens
        pricing_mode = "tiered"
    else:
        input_price = llm_input_price_per_1k_tokens
        output_price = llm_output_price_per_1k_tokens
        pricing_mode = "flat"
    total_cost = ((prompt_tokens / 1000.0) * input_price) + ((completion_tokens / 1000.0) * output_price)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "estimated_cost": round(total_cost, 6),
        "currency": llm_price_currency,
        "pricing_mode": pricing_mode,
        "input_price_per_1k_tokens": input_price,
        "output_price_per_1k_tokens": output_price,
        "selected_tier": selected_tier.as_dict() if selected_tier is not None else None,
    }


def usage_with_meta(
    usage: dict[str, Any],
    *,
    trace_id: str,
    retrieval: dict[str, Any],
    latency: dict[str, Any],
    cost: dict[str, Any],
) -> dict[str, Any]:
    payload = dict(usage or {})
    payload["_meta"] = {"trace_id": trace_id, "retrieval": retrieval, "latency": latency, "cost": cost}
    return payload
