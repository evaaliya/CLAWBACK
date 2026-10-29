"""Upload size and type limits for /api/ingest/*."""

from __future__ import annotations

from dataclasses import dataclass

ALLOWED_EXTENSIONS = frozenset({".csv", ".json", ".txt", ".pdf", ".png", ".jpg", ".jpeg"})
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "text/csv",
        "text/plain",
        "application/csv",
        "application/json",
        "application/pdf",
        "image/png",
        "image/jpeg",
        "application/octet-stream",
    }
)


@dataclass
class UploadRejected(Exception):
    code: str
    message: str

    def as_error(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}


def validate_upload(
    *,
    content: bytes,
    filename: str | None,
    content_type: str | None,
    max_bytes: int,
) -> None:
    if len(content) > max_bytes:
        raise UploadRejected(
            code="upload_too_large",
            message=f"Upload exceeds the {max_bytes} byte limit.",
        )

    name = (filename or "").lower().strip()
    if name:
        # Take the last suffix (handles .tar.gz-style names poorly by design — we want .pdf etc.)
        dot = name.rfind(".")
        ext = name[dot:] if dot >= 0 else ""
        if ext == ".jpeg":
            ext = ".jpg"
        if ext not in ALLOWED_EXTENSIONS:
            raise UploadRejected(
                code="upload_type_not_allowed",
                message="Allowed types: csv, json, txt, pdf, png, jpg.",
            )
        return

    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype and ctype not in ALLOWED_CONTENT_TYPES:
        raise UploadRejected(
            code="upload_type_not_allowed",
            message="Allowed types: csv, json, txt, pdf, png, jpg.",
        )
