"""Portal gate errors."""


class ApprovalRequired(Exception):
    """Raised when confirm_cancel runs without a stored user confirmation."""

    def __init__(self, *, merchant: str) -> None:
        self.merchant = merchant
        super().__init__(f"cancel for {merchant} has no stored confirmation")


class ActionUnavailable(Exception):
    """Raised when a portal action is not available for the current state."""

    def __init__(self, *, merchant: str, action: str, reason: str = "") -> None:
        self.merchant = merchant
        self.action = action
        self.reason = reason
        super().__init__(
            f"action {action!r} unavailable for {merchant}"
            + (f": {reason}" if reason else "")
        )
