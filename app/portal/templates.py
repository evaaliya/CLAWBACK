"""Mock portal templates and cancellation step graphs."""

from __future__ import annotations

from typing import Any

ACCOUNT_MEMBERSHIP = "account-membership"
SETTINGS_MENU = "settings-menu"

TEMPLATE_STEPS: dict[str, list[str]] = {
    ACCOUNT_MEMBERSHIP: [
        "open_account_settings",
        "find_cancel_link",
        "confirm_cancel",
        "save_confirmation",
    ],
    SETTINGS_MENU: [
        "open_settings",
        "open_subscription",
        "manage_plan",
        "end_plan",
        "confirm_cancel",
        "save_confirmation",
    ],
}

TEMPLATE_NOTES: dict[str, dict[str, str]] = {
    ACCOUNT_MEMBERSHIP: {
        "open_account_settings": "Account > Membership",
        "find_cancel_link": "Cancel membership",
        "confirm_cancel": "Requires user confirmation",
        "save_confirmation": "Store confirmation in memory",
    },
    SETTINGS_MENU: {
        "open_settings": "Settings",
        "open_subscription": "Subscription",
        "manage_plan": "Manage plan",
        "end_plan": "End plan",
        "confirm_cancel": "Requires user confirmation",
        "save_confirmation": "Store confirmation in memory",
    },
}

HELP_PATHS: dict[str, str] = {
    ACCOUNT_MEMBERSHIP: (
        "To cancel: open Account, choose Membership, click Cancel membership, "
        "then Confirm. Confirmation number is shown on the status page."
    ),
    SETTINGS_MENU: (
        "To cancel: open Settings, choose Subscription, Manage plan, End plan, "
        "then Confirm. Confirmation number is shown on the status page."
    ),
}


def default_steps_for_template(portal_template: str) -> list[dict[str, str]]:
    notes = TEMPLATE_NOTES.get(portal_template, {})
    return [
        {"action": action, "note": notes.get(action, action)}
        for action in TEMPLATE_STEPS.get(portal_template, [])
    ]


def account_payload(merchant: str, portal_template: str, status: str) -> dict[str, Any]:
    steps = TEMPLATE_STEPS.get(portal_template, [])
    return {
        "merchant": merchant,
        "portal_template": portal_template,
        "status": status,
        "actions": list(steps),
        "path_summary": HELP_PATHS.get(portal_template, ""),
    }


def help_payload(merchant: str, portal_template: str) -> dict[str, Any]:
    return {
        "merchant": merchant,
        "portal_template": portal_template,
        "title": f"How to cancel {merchant}",
        "body": HELP_PATHS.get(portal_template, "No help available."),
        "steps": default_steps_for_template(portal_template),
        "source": f"mock-portal://{portal_template}/help/cancel",
    }
