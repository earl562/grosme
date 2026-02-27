"""Ollama-powered grocery shopping agent with tool calling."""

import json
import os
import re

import httpx
from ollama import chat, ChatResponse
from rich.console import Console
from rich.panel import Panel

console = Console()

MODEL_NAME = os.getenv("GROSME_MODEL", "lfm2.5-thinking:latest")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

SYSTEM_PROMPT = """You are Grosme, a grocery shopping assistant with 4 tools.

DECISION TREE:
1. If the user gives you grocery items → call search_walmart(query) for each item
2. If the user mentions Apple Notes → call fetch_notes_list() first, then fetch_note_content(note_index) to read it, then search_walmart for each grocery item found
3. If the user asks to be notified → call notify_user(message)

RULES:
- One tool call per grocery item
- Process items one at a time
- After all items are searched, say Done"""


def _strip_thinking(text: str) -> str:
    """Strip <think>...</think> blocks from model output (fallback for non-SDK thinking)."""
    return re.sub(r"<think(?:ing)?>.*?</think(?:ing)?>", "", text, flags=re.DOTALL).strip()


def run_conversation(
    user_message: str,
    tools: list,
    available_functions: dict,
    max_iterations: int = 30,
    verbose: bool = True,
) -> tuple[str, list[dict]]:
    """Run agent conversation loop with tool calling.

    Args:
        user_message: The user's request.
        tools: List of Python functions to expose as tools.
        available_functions: Dict mapping function names to callables.
        max_iterations: Max agent loop iterations.
        verbose: Whether to print intermediate output.

    Returns:
        A tuple of (final_text_response, collected_tool_results).
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    collected_tool_results: list[dict] = []
    response: ChatResponse | None = None

    for iteration in range(max_iterations):
        if verbose:
            console.print(f"\n[bold dim]--- Agent iteration {iteration + 1} ---[/]")

        response = chat(
            model=MODEL_NAME,
            messages=messages,
            tools=tools,
            think=True,
        )
        messages.append(response.message)

        # Display thinking (ollama SDK puts it in .thinking, not in content)
        thinking = getattr(response.message, "thinking", None) or ""
        if verbose and thinking:
            display = thinking[:800] + ("..." if len(thinking) > 800 else "")
            console.print(Panel(display, title="Agent Thinking", style="dim yellow", expand=False))

        # Display content (the non-thinking response text)
        content = response.message.content or ""
        cleaned = _strip_thinking(content)
        if verbose and cleaned:
            console.print(f"[bold]{cleaned}[/]")

        if response.message.tool_calls:
            for tc in response.message.tool_calls:
                fn_name = tc.function.name
                fn_args = tc.function.arguments
                if fn_name in available_functions:
                    if verbose:
                        console.print(f"[cyan]-> Calling {fn_name}({fn_args})[/]")
                    result = available_functions[fn_name](**fn_args)
                    result_str = (
                        json.dumps(result, default=str)
                        if not isinstance(result, str)
                        else result
                    )
                    if verbose:
                        preview = result_str[:300] + ("..." if len(result_str) > 300 else "")
                        console.print(f"[green]<- Result: {preview}[/]")
                    messages.append(
                        {"role": "tool", "tool_name": fn_name, "content": result_str}
                    )
                    # Capture full product data for display (slim data goes to model)
                    full_result = result
                    if fn_name == "search_walmart":
                        fn = available_functions[fn_name]
                        full_result = getattr(fn, "_last_full_results", result)
                    collected_tool_results.append(
                        {"tool": fn_name, "args": fn_args, "result": full_result}
                    )
                else:
                    if verbose:
                        console.print(f"[red]Unknown tool: {fn_name}[/]")
                    messages.append(
                        {"role": "tool", "tool_name": fn_name, "content": "Unknown tool"}
                    )
        else:
            if verbose:
                console.print("[bold green]Agent finished (no more tool calls)[/]")
            break  # no more tool calls = final answer

    # Extract final response
    final_text = ""
    if response:
        content = response.message.content or ""
        final_text = _strip_thinking(content)
    return final_text, collected_tool_results


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
