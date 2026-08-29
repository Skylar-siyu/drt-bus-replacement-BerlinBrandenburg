#!/usr/bin/env python3
"""Validate that an analysis archive is the frozen A/B/C figure input set."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np

from data_access import AnalysisStore


EXPECTED_SCENARIOS = {
    "A4_FL",
    "A8_FL",
    "A12_FL",
    "A4_FH",
    "A8_FH",
    "A12_FH",
    "A8_FM",
    "A8_SUB1",
    "B6_PTI",
    "C22_PTI",
}


def check(condition: bool, message: str, failures: list[str]) -> None:
    marker = "OK" if condition else "FAIL"
    print(f"[{marker}] {message}")
    if not condition:
        failures.append(message)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-source", type=Path, required=True)
    args = parser.parse_args()
    failures: list[str] = []

    with AnalysisStore(args.analysis_source) as store:
        scenarios = set(store.available_scenarios())
        check(
            EXPECTED_SCENARIOS.issubset(scenarios),
            "all ten frozen intervention scenarios are present",
            failures,
        )

        baseline = store.csv("01_baseline/baseline_target_line_operational_summary.csv")
        check(set(baseline["case"].astype(str)) == {"A", "B", "C"}, "baseline has A/B/C", failures)
        boardings_per_departure = baseline.set_index("case")["boardings"] / baseline.set_index("case")["departures"]
        expected = {"A": 89 / 42, "B": 70 / 37, "C": 1833 / 127}
        check(
            all(np.isclose(boardings_per_departure.loc[k], v) for k, v in expected.items()),
            "baseline boardings/departure matches the submitted analysis",
            failures,
        )

        rq1 = store.rq("RQ1_context_suitability_A_B_C.csv")
        check(
            set(rq1["scenario"].astype(str)) == {"A8_FM", "B6_PTI", "C22_PTI"},
            "RQ1 contains the three structural replacements",
            failures,
        )
        check(
            len(store.rq("RQ2_caseA_intervention_design.csv")) == 8,
            "RQ2 contains all eight Case A designs",
            failures,
        )
        check(
            len(store.rq("RQ2_pricing_chain_8veh_FM_SUB1_FL_FH.csv")) == 4,
            "pricing chain contains FM/SUB1/FL/FH",
            failures,
        )

        for scenario in ("A8_FM", "B6_PTI", "C22_PTI"):
            for filename in (
                "person_level_impacts.csv.gz",
                "trip_level_impacts.csv.gz",
                "drt_kpi_canonical.csv",
                "drt_kpi_raw_final_window.csv",
            ):
                check(
                    store.exists(f"02_scenarios/{scenario}/{filename}"),
                    f"{scenario}/{filename}",
                    failures,
                )

    if failures:
        print(f"\nValidation failed ({len(failures)} checks).", file=sys.stderr)
        raise SystemExit(1)
    print("\nValidation passed: this source has the frozen A/B/C figure inputs.")


if __name__ == "__main__":
    main()
