"""Pydantic data schemas for grosme."""

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class GroceryItem(BaseModel):
    """A single grocery item extracted from a note."""

    name: str
    quantity: int = 1
    unit: str | None = None
    category: str | None = None
    raw_text: str = ""
    source_type: Literal["text"] = "text"


class WalmartProduct(BaseModel):
    """A product scraped from Walmart."""

    name: str
    price: float | None = None
    url: str
    image_url: str | None = None
    availability: str | None = None
    size: str | None = None
    brand: str | None = None


class MatchedItem(BaseModel):
    """A grocery item matched to a Walmart product."""

    grocery_item: GroceryItem
    matched_product: WalmartProduct | None = None
    confidence: float = 0.0
    alternatives: list[WalmartProduct] = Field(default_factory=list)
    status: Literal["matched", "partial", "not_found"] = "not_found"


class GroceryList(BaseModel):
    """The full grocery list with matched products."""

    items: list[MatchedItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    source_file: str | None = None
    total_estimated_cost: float = 0.0

    def summary(self) -> str:
        """Return a text summary of the grocery list."""
        matched = self.matched_count()
        total = len(self.items)
        unmatched = total - matched
        return (
            f"Total items: {total} | "
            f"Matched: {matched} | "
            f"Unmatched: {unmatched} | "
            f"Estimated cost: ${self.total_estimated_cost:.2f}"
        )

    def matched_count(self) -> int:
        """Count how many items were successfully matched."""
        return sum(1 for item in self.items if item.status == "matched")

    def unmatched_items(self) -> list["MatchedItem"]:
        """Return items that were not matched."""
        return [item for item in self.items if item.status != "matched"]


class NotesInput(BaseModel):
    """An ingested note file or text input."""

    file_path: Path | None = None
    content_type: Literal["text"] = "text"
    raw_content: str = ""
