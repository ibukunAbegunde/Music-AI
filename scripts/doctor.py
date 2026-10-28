"""CLI wrapper for environment doctor."""

from __future__ import annotations

import json

from backend.app.core.doctor import run_doctor


def main() -> None:
    print(json.dumps(run_doctor(), indent=2))


if __name__ == "__main__":
    main()
