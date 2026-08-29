#!/usr/bin/env python3
"""Check that generated PNGs are complete, readable and non-empty."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--figure-dir", type=Path, required=True)
    parser.add_argument(
        "--include-maps", action="store_true", help="Also require Figures 3.1, B.5 and B.10"
    )
    args = parser.parse_args()
    manifest = Path(__file__).resolve().with_name("FIGURE_MANIFEST.csv")
    with manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not args.include_maps:
        rows = [row for row in rows if not row["generator"].startswith("maps/")]

    failures: list[str] = []
    for row in rows:
        path = args.figure_dir / row["output_file"]
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                width, height = image.size
            if width < 600 or height < 300:
                raise ValueError(f"unexpectedly small canvas {width}x{height}")
            print(f"[OK] Figure {row['figure']}: {path.name} ({width}x{height})")
        except Exception as exc:  # provide one consolidated failure report
            failures.append(f"Figure {row['figure']}: {path} — {exc}")
            print(f"[FAIL] {failures[-1]}")
    if failures:
        raise SystemExit(f"\n{len(failures)} figure-output check(s) failed")
    print(f"\nValidated {len(rows)} generated figure files.")


if __name__ == "__main__":
    main()

