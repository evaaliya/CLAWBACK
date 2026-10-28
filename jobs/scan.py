"""Serverless Job entrypoint. Full scan() lands in M2."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    print("scan: not implemented until M2")
    sys.exit(0)


if __name__ == "__main__":
    main()
