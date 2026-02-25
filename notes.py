"""Apple Notes ingestion — via Memo CLI, text files, or direct text."""

import subprocess
from pathlib import Path

from rich.console import Console

from model import extract_items_from_text
from models import GroceryItem, NotesInput

console = Console()


def fetch_notes_list() -> list[dict]:
    """Fetch the list of all Apple Notes via Memo CLI.

    Returns:
        A list of dicts with index, folder, and title for each note.
    """
    try:
        result = subprocess.run(
            ["memo", "notes"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError:
        console.print(
            "[bold red]Error:[/] memo CLI not found. "
            "Install it: brew tap antoniorodr/memo && brew install antoniorodr/memo/memo"
        )
        return []

    notes = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line or not line[0].isdigit():
            continue
        dot_pos = line.find(".")
        if dot_pos == -1:
            continue
        try:
            index = int(line[:dot_pos])
        except ValueError:
            continue
        rest = line[dot_pos + 1:].strip()
        dash_pos = rest.find(" - ")
        if dash_pos != -1:
            folder = rest[:dash_pos].strip()
            title = rest[dash_pos + 3:].strip()
        else:
            folder = ""
            title = rest
        notes.append({"index": index, "folder": folder, "title": title})

    return notes


def fetch_note_content(note_index: int) -> str:
    """Fetch the full content of a specific note by its index.

    Args:
        note_index: The 1-based index of the note from memo notes list.

    Returns:
        The note content as text.
    """
    try:
        result = subprocess.run(
            ["memo", "notes", "-v", str(note_index)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def fetch_notes_from_folder(folder: str) -> list[dict]:
    """Fetch notes from a specific Apple Notes folder via Memo CLI.

    Args:
        folder: The folder name to filter by.

    Returns:
        A list of dicts with index and title for each note in the folder.
    """
    try:
        result = subprocess.run(
            ["memo", "notes", "-f", folder],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError:
        console.print("[bold red]Error:[/] memo CLI not found.")
        return []

    notes = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line or not line[0].isdigit():
            continue
        dot_pos = line.find(".")
        if dot_pos == -1:
            continue
        try:
            index = int(line[:dot_pos])
        except ValueError:
            continue
        rest = line[dot_pos + 1:].strip()
        dash_pos = rest.find(" - ")
        title = rest[dash_pos + 3:].strip() if dash_pos != -1 else rest
        notes.append({"index": index, "title": title})

    return notes


def ingest_from_memo(note_index: int) -> NotesInput:
    """Ingest a note directly from Apple Notes via Memo.

    Args:
        note_index: The note index to read.

    Returns:
        A NotesInput wrapping the note content.
    """
    content = fetch_note_content(note_index)
    return NotesInput(
        file_path=None,
        content_type="text",
        raw_content=content,
    )


def ingest_directory(directory: Path) -> list[NotesInput]:
    """Scan a directory for .txt files.

    Args:
        directory: The directory to scan.

    Returns:
        A list of NotesInput objects for each text file found.
    """
    if not directory.is_dir():
        console.print(f"[bold red]Error:[/] {directory} is not a directory.")
        return []

    inputs: list[NotesInput] = []
    for file_path in sorted(directory.iterdir()):
        if file_path.suffix.lower() == ".txt":
            raw_content = file_path.read_text(encoding="utf-8")
            inputs.append(
                NotesInput(
                    file_path=file_path,
                    content_type="text",
                    raw_content=raw_content,
                )
            )

    if not inputs:
        console.print(f"[yellow]No .txt files found in {directory}[/]")
    else:
        console.print(f"Found [bold green]{len(inputs)}[/] file(s) to process.")

    return inputs


def ingest_text(raw_text: str) -> NotesInput:
    """Create a NotesInput from direct text input.

    Args:
        raw_text: The grocery list text provided by the user.

    Returns:
        A NotesInput wrapping the text.
    """
    return NotesInput(
        file_path=None,
        content_type="text",
        raw_content=raw_text,
    )


def process_notes(inputs: list[NotesInput]) -> list[GroceryItem]:
    """Process all ingested notes and extract grocery items.

    Args:
        inputs: A list of NotesInput objects to process.

    Returns:
        A consolidated list of GroceryItem objects.
    """
    all_items: list[GroceryItem] = []

    for note in inputs:
        if isinstance(note.raw_content, str) and note.raw_content.strip():
            items = extract_items_from_text(note.raw_content)
            all_items.extend(items)

    return _deduplicate_items(all_items)


def _deduplicate_items(items: list[GroceryItem]) -> list[GroceryItem]:
    """Merge duplicate grocery items by combining quantities.

    Args:
        items: The raw list of extracted items (may have duplicates).

    Returns:
        A deduplicated list with merged quantities.
    """
    seen: dict[str, GroceryItem] = {}

    for item in items:
        key = item.name.lower().strip()
        if key in seen:
            seen[key].quantity += item.quantity
        else:
            seen[key] = item.model_copy()

    return list(seen.values())
