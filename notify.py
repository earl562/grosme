"""Notifications — Gmail + Google Calendar (Phase 2 stubs)."""

from datetime import datetime

from rich.console import Console

from models import GroceryList

console = Console()


def send_gmail_notification(grocery_list: GroceryList, recipient: str) -> bool:
    """Send an email summary of the matched grocery list.

    Args:
        grocery_list: The completed grocery list to summarize.
        recipient: The email address to send to.

    Returns:
        True if the notification was sent successfully.
    """
    # TODO: Phase 2 — integrate Gmail API (google-api-python-client)
    console.print(
        f"[yellow][Phase 2][/] Would send email to {recipient} with "
        f"{len(grocery_list.items)} items, "
        f"estimated cost: ${grocery_list.total_estimated_cost:.2f}"
    )
    return True


def create_calendar_event(
    grocery_list: GroceryList, delivery_time: datetime
) -> bool:
    """Create a Google Calendar event for the grocery delivery.

    Args:
        grocery_list: The grocery list for the delivery.
        delivery_time: When the delivery is expected.

    Returns:
        True if the event was created successfully.
    """
    # TODO: Phase 2 — integrate Google Calendar API
    console.print(
        f"[yellow][Phase 2][/] Would create calendar event: "
        f"'Walmart Grocery Delivery' at {delivery_time.isoformat()}"
    )
    return True


def notify_user(grocery_list: GroceryList, method: str = "email") -> bool:
    """Send a notification to the user about the completed grocery list.

    Args:
        grocery_list: The completed grocery list.
        method: Notification method — "email" or "calendar" or "all".

    Returns:
        True if notification was sent successfully.
    """
    # TODO: Phase 2 — accept recipient/time from config or CLI
    success = True

    if method in ("email", "all"):
        success = send_gmail_notification(grocery_list, "user@example.com") and success

    if method in ("calendar", "all"):
        success = (
            create_calendar_event(grocery_list, datetime.now()) and success
        )

    return success
