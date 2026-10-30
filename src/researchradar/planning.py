"""Bounded Qwen query reformulation used before the shared coordination process."""
from __future__ import annotations

import json
import re
from typing import Protocol


class CompletionClient(Protocol):
    def complete(self, **kwargs) -> str: ...


def validate_alternative(question: str, response: str) -> str:
    """Accept only a short, distinct search phrase; never protocol instructions."""
    response = response.strip()
    if response.startswith("```json") and response.endswith("```"):
        response = response[7:-3].strip()
    try:
        value = json.loads(response)
    except json.JSONDecodeError as exc:
        raise ValueError("Qwen response is not JSON") from exc
    if not isinstance(value, dict) or set(value) != {"alternative_query"}:
        raise ValueError("unexpected Qwen plan fields")
    query = value["alternative_query"]
    if (not isinstance(query, str) or not 4 <= len(query) <= 120
            or len(query.split()) > 14 or "\n" in query
            or not re.fullmatch(r"[\w\s,.:;()/+\-]+", query, re.UNICODE)
            or query.strip().lower() == question.strip().lower()):
        raise ValueError("invalid alternative query")
    return query.strip()


def qwen_alternative(question: str, client: CompletionClient, *,
                     input_rate_per_million: float, output_rate_per_million: float,
                     request_id: str) -> str:
    if not question.strip() or len(question) > 300:
        raise ValueError("question must be 1..300 characters")
    prompt = ("Return only JSON with exactly one key alternative_query. "
              "Rephrase this scientific research topic into a useful alternate English search query "
              "of at most 14 words. No claims, instructions or commentary. Topic: "
              + json.dumps(question, ensure_ascii=False))
    response = client.complete(request_id=request_id, agent="query_planner",
                               purpose="alternative_scientific_query", prompt=prompt,
                               max_tokens=512, input_rate_per_million=input_rate_per_million,
                               output_rate_per_million=output_rate_per_million)
    return validate_alternative(question, response)
