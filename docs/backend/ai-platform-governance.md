# AI Platform Governance

## Overview

This repository now supports four backend extension points for AI application engineering:

- Prompt registry with versioned prompt keys
- Model routing by execution profile
- External cross-encoder rerank with heuristic fallback
- Layout-aware visual retrieval through region-level indexing

These capabilities are designed to be incremental. When no extra configuration is provided, the system keeps the previous local behavior.

## Prompt Registry

Prompt definitions are centralized in `packages/python/shared/prompt_registry.py`.

Built-in prompt entries:

- `chat_grounded_answer`
- `chat_common_knowledge`
- `kb_grounded_answer`

Optional override sources:

- `PROMPT_REGISTRY_JSON`
- `PROMPT_REGISTRY_PATH`

Example:

```json
{
  "chat_grounded_answer": {
    "version": "2026-04-01",
    "route_key": "grounded_premium"
  }
}
```

## Model Routing

Model routing is configured through:

- `LLM_MODEL_ROUTING_JSON`
- `AI_MODEL_ROUTING_JSON`

Supported per-route fields:

- `provider`
- `base_url`
- `api_key`
- `model`
- `temperature`
- `max_tokens`
- `timeout_seconds`
- `extra_body`

Recommended route keys:

- `grounded`
- `common_knowledge`
- `agent`

Example:

```json
{
  "grounded": {
    "model": "gpt-4.1-mini",
    "temperature": 0.2,
    "max_tokens": 1200
  },
  "agent": {
    "model": "gpt-4.1",
    "temperature": 0.1,
    "max_tokens": 800
  }
}
```

## Cross-Encoder Rerank

Default behavior is still heuristic rerank. To enable external cross-encoder rerank:

- `RERANK_PROVIDER=external-cross-encoder`
- `RERANK_API_BASE_URL=https://your-rerank-host`
- `RERANK_API_KEY=...`
- `RERANK_MODEL=...`

Optional:

- `RERANK_TIMEOUT_SECONDS`
- `RERANK_TOP_N`
- `RERANK_EXTRA_BODY_JSON`

Expected HTTP contract:

`POST {RERANK_API_BASE_URL}/rerank`

Request body:

```json
{
  "model": "bge-reranker-v2",
  "query": "expense approval",
  "documents": [
    {
      "id": "unit-1",
      "text": "document title\nsection title\ncandidate text"
    }
  ],
  "top_n": 8
}
```

Response body:

```json
{
  "results": [
    {
      "id": "unit-1",
      "score": 0.98
    }
  ]
}
```

If the external rerank provider fails, retrieval falls back to heuristic rerank automatically.

## Layout-Aware Visual Retrieval

The vision pipeline now accepts richer external VLM/OCR JSON:

```json
{
  "ocr_text": "...",
  "summary": "...",
  "confidence": 0.92,
  "layout_hints": ["table", "header"],
  "regions": [
    {
      "label": "expense table",
      "text": "Meal 120\nHotel 300",
      "bbox": [0, 0, 100, 50]
    }
  ]
}
```

Behavior:

- Full-image OCR still creates `visual_ocr` sections/chunks
- Region entries additionally create `visual_region` sections/chunks
- Retrieval treats any `visual*` source as visual evidence

This keeps the old OCR-only path working while allowing region-level retrieval when the upstream provider can return layout-aware JSON.

## Verification

Run:

```powershell
python -m pytest tests/test_ai_platform_capabilities.py -q
python -m pytest tests -q
python -m compileall packages/python apps/services/api-gateway apps/services/knowledge-base
docker compose config --quiet
```
