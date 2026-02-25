"""Ollama LLM client for grocery item extraction using lfm2.5-thinking."""

import json
import os
import re

import httpx
from rich.console import Console

from models import GroceryItem

console = Console()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL_NAME = "lfm2.5-thinking:latest"

EXTRACTION_PROMPT = """Extract ALL grocery items from the text into a JSON array.

Example input: "2 gallons milk, 6 eggs, chx breast, 3 bananas, advocados"
Example output: [{"name": "milk", "quantity": 2, "unit": "gallon", "category": "dairy"}, {"name": "eggs", "quantity": 6, "unit": null, "category": "dairy"}, {"name": "chicken breast", "quantity": 1, "unit": null, "category": "meat"}, {"name": "bananas", "quantity": 3, "unit": null, "category": "produce"}, {"name": "avocados", "quantity": 1, "unit": null, "category": "produce"}]

Example input: "Grapes(Green), 3 bananas, 2 advocados"
Example output: [{"name": "green grapes", "quantity": 1, "unit": null, "category": "produce"}, {"name": "bananas", "quantity": 3, "unit": null, "category": "produce"}, {"name": "avocados", "quantity": 2, "unit": null, "category": "produce"}]

Rules: Fix typos. Parse quantities from text like "3 bananas" = quantity 3. Default quantity to 1. Skip non-food lines. Return ONLY the JSON array.
"""

MATCH_RANKING_PROMPT = """You are a grocery shopping assistant. Given a desired grocery item and a list of
Walmart products found, select the BEST match.

Desired item: {item_name} ({quantity} {unit})

Available products:
{products_json}

Return ONLY JSON:
{{
  "best_match_index": 0,
  "confidence": 0.95,
  "reasoning": "brief explanation"
}}

Prefer:
- Exact size/quantity matches
- Store brand (Great Value) for generic items
- Lower price when quality is comparable
"""


def _call_ollama(prompt: str) -> str:
    """Call Ollama's generate API.

    Args:
        prompt: The text prompt to send.

    Returns:
        The raw response text from the model.
    """
    payload: dict = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
    }

    try:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=120.0,
        )
        response.raise_for_status()
        return response.json().get("response", "")
    except httpx.ConnectError:
        console.print(
            "[bold red]Error:[/] Cannot connect to Ollama. "
            "Make sure Ollama is running (ollama serve)."
        )
        raise SystemExit(1)
    except httpx.HTTPStatusError as e:
        console.print(
            f"[bold red]Ollama API error:[/] {e.response.status_code} — "
            f"is the model '{MODEL_NAME}' pulled? Run: ollama pull {MODEL_NAME}"
        )
        raise SystemExit(1)


def _parse_llm_response(raw: str) -> list[dict]:
    """Strip thinking tags and extract JSON from the LLM response.

    Args:
        raw: The raw model output string.

    Returns:
        A parsed list of dicts from the JSON in the response.
    """
    # Strip <think>...</think> or <thinking>...</thinking> blocks
    cleaned = re.sub(
        r"<think(?:ing)?>.*?</think(?:ing)?>", "", raw, flags=re.DOTALL
    )

    # Try to extract JSON from markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", cleaned, re.DOTALL)
    if fence_match:
        json_str = fence_match.group(1).strip()
    else:
        # Try to find a raw JSON array
        bracket_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if bracket_match:
            json_str = bracket_match.group(0)
        else:
            # Try to find a raw JSON object
            brace_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if brace_match:
                json_str = brace_match.group(0)
            else:
                return []

    try:
        parsed = json.loads(json_str)
        if isinstance(parsed, dict):
            return [parsed]
        return parsed
    except json.JSONDecodeError:
        console.print("[yellow]Warning:[/] Could not parse LLM JSON response.")
        return []


def extract_items_from_text(text: str) -> list[GroceryItem]:
    """Extract grocery items from text input using the LLM.

    Args:
        text: The grocery list text to parse.

    Returns:
        A list of parsed GroceryItem objects.
    """
    # Collapse excessive blank lines — Memo output from Notes with removed
    # attachments can have many empty lines that confuse the small LLM.
    import re as _re

    cleaned_text = _re.sub(r"\n\s*\n", "\n", text).strip()
    prompt = f"{EXTRACTION_PROMPT}\n\nHere is the grocery list:\n{cleaned_text}"
    raw = _call_ollama(prompt)
    items_data = _parse_llm_response(raw)

    items = []
    for item_dict in items_data:
        try:
            unit = item_dict.get("unit")
            if unit == "null" or unit is None:
                unit = None
            items.append(
                GroceryItem(
                    name=item_dict.get("name", "unknown"),
                    quantity=int(item_dict.get("quantity", 1)),
                    unit=unit,
                    category=item_dict.get("category"),
                    raw_text=item_dict.get("name", ""),
                    source_type="text",
                )
            )
        except (ValueError, TypeError):
            continue

    return items


def rank_products(
    item: GroceryItem, products: list[dict]
) -> dict:
    """Use the LLM to rank Walmart products and pick the best match.

    Args:
        item: The grocery item to match.
        products: A list of product dicts to rank.

    Returns:
        A dict with best_match_index, confidence, and reasoning.
    """
    prompt = MATCH_RANKING_PROMPT.format(
        item_name=item.name,
        quantity=item.quantity,
        unit=item.unit or "unit",
        products_json=json.dumps(products, indent=2),
    )
    raw = _call_ollama(prompt)
    results = _parse_llm_response(raw)

    if results and isinstance(results[0], dict):
        return results[0]

    return {"best_match_index": 0, "confidence": 0.5, "reasoning": "default pick"}


def check_ollama() -> bool:
    """Check if Ollama is running and the model is available.

    Returns:
        True if Ollama is reachable and the model is pulled.
    """
    try:
        response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
        response.raise_for_status()
        models = response.json().get("models", [])
        model_names = [m.get("name", "") for m in models]
        return any(MODEL_NAME.split(":")[0] in name for name in model_names)
    except (httpx.ConnectError, httpx.HTTPStatusError):
        return False
