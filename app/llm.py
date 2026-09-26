import json
import re
from abc import ABC, abstractmethod

import requests

from .config import settings
from .schemas import LineInterpretation


class LLMClient(ABC):

    @abstractmethod
    def interpret_line(
        self,
        line_text: str,
        catalog_names: list[str],
    ) -> LineInterpretation:
        raise NotImplementedError


class MockLLMClient(LLMClient):
    """Local fallback implementation."""

    def interpret_line(
        self,
        line_text: str,
        catalog_names: list[str],
    ) -> LineInterpretation:

        match = re.match(
            r"\s*(\d+)\s*x\s*(.+?)\s*$",
            line_text,
            re.IGNORECASE,
        )

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
            reason=(
                f"Parsed quantity={quantity}; "
                f"product text='{product_text}'."
            ),
        )


class HttpLLMClient(LLMClient):
    """OpenAI-compatible client for the internal CIB LLM API."""

    def interpret_line(
        self,
        line_text: str,
        catalog_names: list[str],
    ) -> LineInterpretation:

        # CIB OpenAI-compatible Chat Completions endpoint
        url = (
            settings.llm_base_url.rstrip("/")
            + "/chat/completions"
        )

        system_prompt = """
You are an order-line interpretation assistant for a promotional
merchandise fulfillment system.

Interpret one promotional merchandise order line.

Return ONLY valid JSON in exactly this structure:

{
  "quantity": integer,
  "sku": string or null,
  "confidence": number,
  "reason": "short explanation"
}

Rules:
1. Extract the requested quantity.
2. Identify the product description.
3. Never invent a SKU.
4. Only return a SKU if it is supported by the catalog candidates.
5. If there is no reliable catalog SKU, return null for sku.
6. Confidence must be between 0 and 1.
7. Do not create products that are not present in the catalog.
"""

        user_prompt = f"""
Order line:
{line_text}

Catalog candidates:
{json.dumps(catalog_names, ensure_ascii=False)}

Interpret the order line and return ONLY valid JSON.
"""

        payload = {
            "model": settings.llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt.strip(),
                },
                {
                    "role": "user",
                    "content": user_prompt.strip(),
                },
            ],
            "temperature": 0,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.llm_api_key}",
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=settings.llm_timeout_seconds,
        )

        response.raise_for_status()

        data = response.json()

        # Read OpenAI-compatible response
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"Unexpected LLM response format: {data}"
            ) from exc

        content = content.strip()

        # Handle responses wrapped in ```json ... ```
        if content.startswith("```"):
            content = re.sub(
                r"^```(?:json)?\s*",
                "",
                content,
                flags=re.IGNORECASE,
            )

            content = re.sub(
                r"\s*```$",
                "",
                content,
            )

        # Convert model JSON into Python object
        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"LLM did not return valid JSON: {content}"
            ) from exc

        return LineInterpretation(
            raw_text=line_text,
            quantity=int(result.get("quantity", 0)),
            sku=result.get("sku"),
            confidence=float(result.get("confidence", 0)),
            reason=str(result.get("reason", "")),
        )


def build_llm_client() -> LLMClient:
    """
    Select the LLM implementation based on configuration.

    LLM_MODE=http  -> Internal CIB LLM
    Anything else  -> Local mock
    """

    if settings.llm_mode.lower() == "http":
        return HttpLLMClient()

    return MockLLMClient()