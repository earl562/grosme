"""grosme — Grocery Shopping Made Easy. CLI entrypoint."""

from dotenv import load_dotenv

load_dotenv()

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agent import check_ollama, run_conversation
from tools import (
    fetch_note_content,
    fetch_notes_from_folder,
    fetch_notes_list,
    notify_user,
    search_walmart,
)

console = Console()
app = typer.Typer(add_completion=False)

BANNER = r"""
   _____ _____   ____   _____ __  __ ______
  / ____|  __ \ / __ \ / ____|  \/  |  ____|
 | |  __| |__) | |  | | (___ | \  / | |__
 | | |_ |  _  /| |  | |\___ \| |\/| |  __|
 | |__| | | \ \| |__| |____) | |  | | |____
  \_____|_|  \_\\____/|_____/|_|  |_|______|

  Grocery Shopping Made Easy
"""

# Tools and function registry for the agent
TOOLS = [search_walmart, fetch_notes_list, fetch_note_content, notify_user]
AVAILABLE_FUNCTIONS = {
    "search_walmart": search_walmart,
    "fetch_notes_list": fetch_notes_list,
    "fetch_note_content": fetch_note_content,
    "fetch_notes_from_folder": fetch_notes_from_folder,
    "notify_user": notify_user,
}


def _display_banner() -> None:
    """Show the grosme startup banner."""
    console.print(Panel(BANNER, style="bold green", expand=False))


def _display_results_table(tool_results: list[dict]) -> None:
    """Display a Rich table from collected search_walmart tool results."""
    search_results = [r for r in tool_results if r["tool"] == "search_walmart"]
    if not search_results:
        return

    table = Table(title="Walmart Grocery List")
    table.add_column("#", style="dim", width=4)
    table.add_column("Item", style="bold")
    table.add_column("Best Match")
    table.add_column("Price", justify="right", style="green")
    table.add_column("Size")

    total = 0.0
    for i, sr in enumerate(search_results, 1):
        query = sr["args"].get("query", "?")
        products = sr["result"]
        if products and isinstance(products, list) and len(products) > 0:
            top = products[0]
            name = (top.get("name") or "?")[:55]
            price_val = top.get("price")
            price = f"${price_val:.2f}" if price_val else "-"
            size = top.get("size") or "-"
            if price_val:
                total += float(price_val)
        else:
            name = "[red]No results[/]"
            price = "-"
            size = "-"
        table.add_row(str(i), query, name, price, size)

    console.print(table)
    console.print(f"\n[bold]Estimated total: ${total:.2f}[/]")

    item_count = len(search_results)
    found = sum(1 for sr in search_results if sr["result"])
    console.print(f"[dim]{found}/{item_count} items found[/]")


def _save_results(tool_results: list[dict], output_dir: Path, source: str) -> Path:
    """Save the agent results to a JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"grocery_list_{timestamp}.json"

    search_results = [r for r in tool_results if r["tool"] == "search_walmart"]
    items = []
    for sr in search_results:
        query = sr["args"].get("query", "")
        products = sr["result"]
        top = products[0] if products and isinstance(products, list) else None
        items.append({
            "query": query,
            "matched_product": top,
            "status": "matched" if top else "not_found",
        })

    data = {
        "created_at": datetime.now().isoformat(),
        "source": source,
        "items": items,
    }

    output_file.write_text(json.dumps(data, indent=2, default=str))
    return output_file


def _parse_note_lines(content: str) -> list[str]:
    """Parse note content into grocery item lines.

    Keeps full brand/size detail. Only strips quantity suffixes (× 2)
    and skips blank/title lines.
    """
    import re

    items: list[str] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or len(line) < 3:
            continue
        # Skip title-like lines (e.g. "Walmart Order")
        if line.lower().startswith(("walmart", "grocery", "shopping", "#")):
            continue
        # Strip quantity suffix like "× 2" or "x 3"
        line = re.sub(r"\s*[×x]\s*\d+\s*$", "", line, flags=re.IGNORECASE)
        line = line.strip()
        if line:
            items.append(line)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def _pick_note_interactive() -> str | None:
    """Show Apple Notes list and let user pick one.

    Returns:
        The note content as text, or None if cancelled.
    """
    with console.status("[bold]Fetching Apple Notes via Memo..."):
        notes = fetch_notes_list()

    if not notes:
        console.print("[bold red]No notes found.[/]")
        return None

    table = Table(title="Apple Notes")
    table.add_column("#", style="dim", width=5)
    table.add_column("Folder", style="cyan")
    table.add_column("Title")

    for note in notes[:30]:
        table.add_row(str(note["index"]), note["folder"], note["title"][:70])

    console.print(table)

    if len(notes) > 30:
        console.print(f"[dim]...and {len(notes) - 30} more notes[/]")

    console.print()
    selection = typer.prompt("Enter note # to use as grocery list (0 to cancel)")
    try:
        idx = int(selection)
    except ValueError:
        console.print("[red]Invalid selection.[/]")
        return None

    if idx == 0:
        return None

    with console.status(f"[bold]Reading note #{idx}..."):
        content = fetch_note_content(idx)

    if not content:
        console.print("[bold red]Could not read note content.[/]")
        return None

    console.print(Panel(content[:500], title=f"Note #{idx}", expand=False))
    return content


@app.command()
def main(
    text: Optional[str] = typer.Option(
        None, "--text", "-t", help="Direct text grocery list."
    ),
    note: Optional[int] = typer.Option(
        None, "--note", help="Apple Notes index to use (from memo notes list)."
    ),
    notes: bool = typer.Option(
        False, "--notes", help="Browse and pick from Apple Notes interactively."
    ),
    output: Path = typer.Option(
        Path("output"), "--output", "-o", help="Output directory."
    ),
    notify: bool = typer.Option(
        False, "--notify", "-n", help="Send notification when done."
    ),
    verbose: bool = typer.Option(
        True, "--verbose/--quiet", "-v/-q", help="Show agent reasoning."
    ),
) -> None:
    """grosme — Grocery Shopping Made Easy."""
    _display_banner()

    # --- Startup checks ---
    with console.status("[bold]Checking Ollama..."):
        if not check_ollama():
            console.print(
                "[bold red]Ollama is not running or model is not available.[/]\n"
                "Run: [bold]ollama serve[/] and "
                "[bold]ollama pull lfm2.5-thinking:latest[/]"
            )
            raise typer.Exit(1)
    console.print("[green]Ollama is ready.[/]\n")

    # --- Build item list based on input mode ---
    source_label = ""
    parsed_items: list[str] | None = None

    if text:
        source_label = "direct text"

    elif note is not None:
        with console.status(f"[bold]Reading Apple Note #{note} via Memo...[/]"):
            content = fetch_note_content(note)
        if not content:
            console.print("[bold red]Could not read note content.[/]")
            raise typer.Exit(1)
        console.print(Panel(content[:500], title=f"Note #{note}", expand=False))
        parsed_items = _parse_note_lines(content)
        if not parsed_items:
            console.print("[bold red]No grocery items found in note.[/]")
            raise typer.Exit(1)
        console.print(f"[dim]Found {len(parsed_items)} items in note[/]")
        source_label = f"Apple Note #{note}"

    elif notes:
        content = _pick_note_interactive()
        if not content:
            console.print("[yellow]No note selected.[/]")
            raise typer.Exit(0)
        parsed_items = _parse_note_lines(content)
        if not parsed_items:
            console.print("[bold red]No grocery items found in note.[/]")
            raise typer.Exit(0)
        console.print(f"[dim]Found {len(parsed_items)} items in note[/]")
        source_label = "Apple Notes"

    else:
        console.print(
            "[bold red]No input provided.[/] Use --text, --notes, or --note #"
        )
        raise typer.Exit(1)

    # --- Search ---
    all_tool_results: list[dict] = []
    final_response = ""

    if parsed_items:
        # Pre-parsed items from note: search directly (no agent reasoning needed)
        console.print(
            f"[bold]Searching Walmart for {len(parsed_items)} items...[/]\n"
        )
        for i, item in enumerate(parsed_items, 1):
            if verbose:
                console.print(f"[cyan]({i}/{len(parsed_items)}) Searching: {item}[/]")
            result = search_walmart(item)
            full_result = getattr(search_walmart, "_last_full_results", result)
            if verbose:
                if result:
                    top = result[0]
                    console.print(
                        f"[green]  -> {top['name'][:60]} — ${top['price']:.2f}[/]"
                    )
                else:
                    console.print("[yellow]  -> No results[/]")
            all_tool_results.append(
                {"tool": "search_walmart", "args": {"query": item}, "result": full_result}
            )
    else:
        # Direct text input: use agent for reasoning about the items
        user_message = f"Search Walmart for each item: {text}"
        console.print("[bold]Starting agent...[/]\n")
        final_response, all_tool_results = run_conversation(
            user_message=user_message,
            tools=TOOLS,
            available_functions=AVAILABLE_FUNCTIONS,
            verbose=verbose,
        )

    tool_results = all_tool_results

    # --- Display results ---
    console.print()
    _display_results_table(tool_results)

    if final_response:
        console.print(f"\n[bold]Agent Summary:[/]\n{final_response}")

    # --- Save ---
    if tool_results:
        output_file = _save_results(tool_results, output, source_label)
        console.print(f"\n[green]Results saved to:[/] {output_file}")

    # --- Notification ---
    if notify:
        search_results = [r for r in tool_results if r["tool"] == "search_walmart"]
        item_count = len(search_results)
        found = sum(1 for sr in search_results if sr["result"])
        total = sum(
            float(sr["result"][0].get("price", 0))
            for sr in search_results
            if sr["result"] and isinstance(sr["result"], list)
        )
        msg = f"Grosme found {found}/{item_count} items. Estimated total: ${total:.2f}"
        notify_user(message=msg, method="all")


if __name__ == "__main__":
    app()
