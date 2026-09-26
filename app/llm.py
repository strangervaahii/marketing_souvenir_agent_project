import re
from abc import ABC, abstractmethod

import requests

from .config import settings
from .schemas import LineInterpretation


class LLMClient(ABC):
    @abstractmethod
    def interpret_line(self, line_text: str, catalog_names: list[str]) -> LineInterpretation:
        raise NotImplementedError


class MockLLMClient(LLMClient):
    """Deterministic local implementation used before the internal LLM is connected."""

    def interpret_line(self, line_text: str, catalog_names: list[str]) -> LineInterpretation:
        match = re.match(r"\s*(\d+)\s*x\s*(.+?)\s*$", line_text, re.IGNORECASE)
        if not match:
            return LineInterpretation(
                raw_text=line_text,
                quantity=1,
                sku=None,
                confidence=0.20,
                reason="Could not reliably parse the quantity/product format.",
            )

        quantity = int(match.group(1))
        product_text = match.group(2).strip()

        return LineInterpretation(
            raw_text=line_text,
            quantity=quantity,
            sku=None,
            confidence=0.95,
            reason=f"Parsed quantity={quantity}; product text='{product_text}'.",
        )


class HttpLLMClient(LLMClient):
    """Generic adapter. Change only this method if the internal endpoint differs."""

    def interpret_line(self, line_text: str, catalog_names: list[str]) -> LineInterpretation:
        url = settings.llm_base_url.rstrip("/") + "/interpret-line"
        payload = {
            "model": settings.llm_model,
            "line_text": line_text,
            "catalog_candidates": catalog_names,
            "instruction": (
                "Interpret one promotional merchandise line. Return JSON with "
                "quantity, sku if known, confidence, and reason. Never invent a SKU."
            ),
        }
        headers = {"Content-Type": "application/json"}
        if settings.llm_api_key:
            headers["Authorization"] = f"Bearer {settings.llm_api_key}"

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()

        return LineInterpretation(
            raw_text=line_text,
            quantity=int(data.get("quantity", 0)),
            sku=data.get("sku"),
            confidence=float(data.get("confidence", 0)),
            reason=str(data.get("reason", "")),
        )


def build_llm_client() -> LLMClient:
    if settings.llm_mode.lower() == "http":
        return HttpLLMClient()
    return MockLLMClient()
