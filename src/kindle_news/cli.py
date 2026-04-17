from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and send weekly Kindle news digest")
    parser.add_argument("--config", type=str, default=None, help="Optional path to config yaml")
    parser.add_argument("--no-email", action="store_true", help="Generate digest without SMTP send")
    parser.add_argument(
        "--mode",
        choices=("weekly", "ingest"),
        default="weekly",
        help="Run weekly digest generation or daily feed ingest cache collection",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    config_path = Path(args.config) if args.config else None
    output = run(
        root=root,
        config_path=config_path,
        send_email=not args.no_email,
        mode=args.mode,
    )
    print(output)


if __name__ == "__main__":
    main()
