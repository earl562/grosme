"""grosme — Grocery Shopping Made Easy. CLI entrypoint."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from model import check_ollama
from models import GroceryList
from notes import (
    fetch_note_content,
    fetch_notes_list,
    ingest_directory,
    ingest_from_memo,
    ingest_text,
    process_notes,
)
from notify import notify_user
from walmart_search import process_grocery_list

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


def _display_banner() -> None:
    """Show the grosme startup banner."""
    console.print(Panel(BANNER, style="bold green", expand=False))


def _display_items_table(items: list) -> None:
    """Display extracted grocery items in a Rich table."""
    table = Table(title="Extracted Grocery Items")
    table.add_column("#", style="dim", width=4)
    table.add_column("Item", style="bold")
    table.add_column("Qty", justify="right")
    table.add_column("Unit")
    table.add_column("Category", style="cyan")

    for i, item in enumerate(items, 1):
        table.add_row(
            str(i),
            item.name,
            str(item.quantity),
            item.unit or "-",
            item.category or "-",
        )

    console.print(table)


def _display_results_table(grocery_list: GroceryList) -> None:
    """Display matched products in a Rich table."""
    table = Table(title="Walmart Product Matches")
    table.add_column("#", style="dim", width=4)
    table.add_column("Item", style="bold")
    table.add_column("Matched Product")
    table.add_column("Price", justify="right", style="green")
    table.add_column("Status", justify="center")

    for i, matched in enumerate(grocery_list.items, 1):
        if matched.status == "matched" and matched.matched_product:
            product_name = matched.matched_product.name[:50]
            price = (
                f"${matched.matched_product.price:.2f}"
                if matched.matched_product.price
                else "-"
            )
            status = "[green]Matched[/]"
        elif matched.status == "partial" and matched.matched_product:
            product_name = matched.matched_product.name[:50]
            price = (
                f"${matched.matched_product.price:.2f}"
                if matched.matched_product.price
                else "-"
            )
            status = "[yellow]Partial[/]"
        else:
            product_name = "-"
            price = "-"
            status = "[red]Not Found[/]"

        table.add_row(
            str(i),
            matched.grocery_item.name,
            product_name,
            price,
            status,
        )

    console.print(table)
    console.print(f"\n[bold]{grocery_list.summary()}[/]")


def _save_results(grocery_list: GroceryList, output_dir: Path) -> Path:
    """Save the grocery list results to a JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"grocery_list_{timestamp}.json"

    data = {
        "created_at": grocery_list.created_at.isoformat(),
        "source": grocery_list.source_file,
        "items": [
            {
                "grocery_item": m.grocery_item.model_dump(),
                "matched_product": (
                    m.matched_product.model_dump() if m.matched_product else None
                ),
                "confidence": m.confidence,
                "status": m.status,
            }
            for m in grocery_list.items
        ],
        "total_estimated_cost": grocery_list.total_estimated_cost,
        "matched": grocery_list.matched_count(),
        "unmatched": len(grocery_list.items) - grocery_list.matched_count(),
    }

    output_file.write_text(json.dumps(data, indent=2, default=str))
    return output_file


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

    # Show notes in a table
    table = Table(title="Apple Notes")
    table.add_column("#", style="dim", width=5)
    table.add_column("Folder", style="cyan")
    table.add_column("Title")

    for note in notes[:30]:  # Show first 30
        table.add_row(str(note["index"]), note["folder"], note["title"][:70])

    console.print(table)

    if len(notes) > 30:
        console.print(f"[dim]...and {len(notes) - 30} more notes[/]")

    # Prompt for selection
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
    input: Optional[Path] = typer.Option(
        None, "--input", "-i", help="Input directory or file path."
    ),
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
        False, "--notify", "-n", help="Send notification when done (Phase 2)."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-d", help="Extract items only, skip Walmart search."
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
    console.print("[green]Ollama is ready.[/]")

    # --- Ingestion ---
    source_label = ""

    if text:
        console.print("[bold]Using direct text input.[/]")
        notes_inputs = [ingest_text(text)]
        source_label = "direct text"

    elif note is not None:
        console.print(f"[bold]Reading Apple Note #{note} via Memo...[/]")
        notes_inputs = [ingest_from_memo(note)]
        content = notes_inputs[0].raw_content
        if isinstance(content, str) and content:
            console.print(Panel(content[:500], title=f"Note #{note}", expand=False))
        source_label = f"Apple Note #{note}"

    elif notes:
        content = _pick_note_interactive()
        if not content:
            console.print("[yellow]No note selected.[/]")
            raise typer.Exit(0)
        notes_inputs = [ingest_text(content)]
        source_label = "Apple Notes"

    elif input:
        input_path = Path(input)
        if input_path.is_dir():
            with console.status("[bold]Scanning notes..."):
                notes_inputs = ingest_directory(input_path)
        elif input_path.is_file():
            from notes import ingest_file

            note_file = ingest_file(input_path)
            notes_inputs = [note_file] if note_file else []
        else:
            console.print(f"[bold red]Path not found:[/] {input_path}")
            raise typer.Exit(1)
        source_label = str(input_path)

    else:
        # Default: scan ./input/
        default_dir = Path("input")
        if not default_dir.exists():
            console.print(
                "[bold red]No input provided.[/] Use --text, --notes, --note #, "
                "or --input, or place files in ./input/"
            )
            raise typer.Exit(1)
        with console.status("[bold]Scanning input/ directory..."):
            notes_inputs = ingest_directory(default_dir)
        source_label = "input/"

    if not notes_inputs:
        console.print("[bold red]No input found to process.[/]")
        raise typer.Exit(1)

    # --- Extraction ---
    with console.status("[bold]Extracting grocery items..."):
        items = process_notes(notes_inputs)

    if not items:
        console.print("[bold red]No grocery items could be extracted.[/]")
        raise typer.Exit(1)

    _display_items_table(items)

    if dry_run:
        console.print("\n[yellow]Dry run — skipping Walmart search.[/]")
        raise typer.Exit(0)

    # --- Confirm ---
    proceed = typer.confirm(
        f"\nFound {len(items)} items. Proceed with Walmart search?"
    )
    if not proceed:
        console.print("[yellow]Cancelled.[/]")
        raise typer.Exit(0)

    # --- Search & Match ---
    console.print()
    grocery_list = process_grocery_list(items)
    grocery_list.source_file = source_label

    # --- Results ---
    console.print()
    _display_results_table(grocery_list)

    # --- Save ---
    output_file = _save_results(grocery_list, output)
    console.print(f"\n[green]Results saved to:[/] {output_file}")

    # --- Notification ---
    if notify:
        notify_user(grocery_list, method="all")


if __name__ == "__main__":
    app()
