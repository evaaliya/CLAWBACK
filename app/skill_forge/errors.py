"""Skill Forge errors."""

from app.portal.errors import ActionUnavailable, ApprovalRequired

__all__ = ["ActionUnavailable", "ApprovalRequired", "SkillReplayError"]


class SkillReplayError(Exception):
    """Raised when replaying a saved skill fails mid-run."""

    def __init__(self, *, skill_id: int, action: str, reason: str) -> None:
        self.skill_id = skill_id
        self.action = action
        self.reason = reason
        super().__init__(f"skill {skill_id} failed at {action!r}: {reason}")
