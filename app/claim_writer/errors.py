"""Claim gate errors."""


class ApprovalRequired(Exception):
    """Raised when send runs without a stored user approval."""

    def __init__(self, claim_id: int) -> None:
        self.claim_id = claim_id
        super().__init__(f"claim {claim_id} has no stored approval")
