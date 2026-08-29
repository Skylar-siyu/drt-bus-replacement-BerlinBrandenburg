#!/usr/bin/env python3
"""Create a GitHub-sized spatial input for Figures B.5 and B.10.

The full RQ3 spatial table in the analysis archive is about 182 MB.  The map
scripts need only five columns and three frozen scenarios.  This utility writes
that subset as a small compressed CSV without person identifiers.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from data_access import AnalysisStore, bool_series


KEEP = ("scenario", "delta_score", "baseline_target_line_rider", "home_x", "home_y")
SCENARIOS = ("A8_FM", "B6_PTI", "C22_PTI")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-source", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=Path("spatial_target_riders.csv.gz")
    )
    args = parser.parse_args()

    with AnalysisStore(args.analysis_source) as store:
        data = store.rq("RQ3_spatial_person_impacts.csv.gz", usecols=KEEP)
    data = data[
        data["scenario"].isin(SCENARIOS)
        & bool_series(data["baseline_target_line_rider"])
    ].copy()
    data = data.sort_values(["scenario", "home_x", "home_y", "delta_score"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(args.output, index=False, compression="gzip")
    counts = data.groupby("scenario").size().to_dict()
    expected = {"A8_FM": 67, "B6_PTI": 47, "C22_PTI": 1190}
    if counts != expected:
        raise SystemExit(f"Unexpected target-rider counts: {counts}; expected {expected}")
    print(f"Saved {args.output} ({len(data):,} rows; {args.output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

