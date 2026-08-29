"""Add the completed Case B and Case C runs to an existing Case A analysis.

This script reconstructs the incremental workflow used for the dissertation:

1. validate B0, B6-PTI and C22-PTI;
2. analyse B6-PTI and C22-PTI in an isolated staging directory;
3. preserve the existing Case A scenario folders;
4. merge the B/C scenario and network summaries;
5. rebuild the RQ1/RQ2/RQ3 tables from the full manifest;
6. write the B/C QA and whole-analysis coverage tables; and
7. optionally package analysis_results/00-04.

The original one-off orchestration file was not retained. This implementation
was reconstructed from the recorded commands and verified against the archived
``ABC_analysis_results_01_04`` directory structure. It calls the preserved core
analysis modules and does not change their metric definitions.
"""

from __future__ import annotations

from pathlib import Path
import argparse
import datetime as dt
import shutil
import subprocess
import sys
import tarfile

import numpy as np
import pandas as pd


DEFAULT_SCENARIOS = ("B6_PTI", "C22_PTI")

REQUIRED_SCENARIO_FILES = (
    "convergence.csv",
    "drt_adoption_summary.csv",
    "drt_kpi_canonical.csv",
    "drt_kpi_raw_final_window.csv",
    "mode_transitions_original_target_bus_trips.csv",
    "mode_transitions_relevant.csv",
    "drt_mode_origins.csv",
    "person_level_impacts.csv.gz",
    "trip_level_impacts.csv.gz",
    "utility_summary.csv",
    "trip_outcome_summary.csv",
    "equity_utility_target_riders.csv",
    "equity_target_trip_behaviour.csv",
    "time_of_day_trip_impacts.csv",
    "system_main_mode_share.csv",
)


def truthy(value):
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def read_csv_optional(path, **kwargs):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, **kwargs)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def run_python(script_dir, script_name, arguments):
    command = [sys.executable, str(script_dir / script_name)] + [str(x) for x in arguments]
    print("\n>>>", " ".join(command))
    subprocess.run(command, cwd=str(script_dir), check=True)


def merge_by_key(old_path, new_path, output_path, key):
    old = read_csv_optional(old_path)
    new = read_csv_optional(new_path)
    if old.empty and new.empty:
        return
    if old.empty:
        merged = new
    elif new.empty:
        merged = old
    else:
        merged = pd.concat([old, new], ignore_index=True, sort=False)
        if key in merged.columns:
            merged = merged.drop_duplicates(subset=[key], keep="last")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False)


def copy_scenario_directory(source, destination, force):
    if destination.exists() and not force:
        raise SystemExit(
            "Refusing to overwrite existing scenario directory: {}\n"
            "Use --force only when intentionally rebuilding B/C.".format(destination)
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=force)


def pick_cohort(path, cohort, count_field):
    data = read_csv_optional(path)
    if data.empty or "cohort" not in data.columns:
        return {}
    row = data[data["cohort"] == cohort]
    if row.empty:
        return {}
    result = row.iloc[0].to_dict()
    result["_count"] = pd.to_numeric(result.get(count_field), errors="coerce")
    return result


def count_rows(path):
    data = read_csv_optional(path)
    return float(len(data)) if not data.empty else np.nan


def build_bc_qa(analysis_root, scenarios):
    baseline = analysis_root / "01_baseline"
    scenario_root = analysis_root / "02_scenarios"
    network_root = analysis_root / "03_network"
    rows = []

    case_lookup = {"B6_PTI": "B", "C22_PTI": "C"}
    for scenario in scenarios:
        case = case_lookup.get(scenario, "")
        scenario_dir = scenario_root / scenario
        missing = [name for name in REQUIRED_SCENARIO_FILES if not (scenario_dir / name).exists()]

        utility = pick_cohort(
            scenario_dir / "utility_summary.csv",
            "baseline_target_line_riders",
            "n",
        )
        trips = pick_cohort(
            scenario_dir / "trip_outcome_summary.csv",
            "baseline_target_line_trips",
            "n_trips",
        )
        adoption = read_csv_optional(scenario_dir / "drt_adoption_summary.csv")
        adoption_row = adoption.iloc[0].to_dict() if not adoption.empty else {}

        rows.append(
            {
                "scenario": scenario,
                "case": case,
                "scenario_dir_exists": int(scenario_dir.exists()),
                "required_files_present": len(REQUIRED_SCENARIO_FILES) - len(missing),
                "required_files_total": len(REQUIRED_SCENARIO_FILES),
                "missing_files": "|".join(missing),
                "baseline_unique_target_riders": count_rows(
                    baseline / "case_{}_target_line_persons.csv".format(case)
                ),
                "baseline_target_boardings": count_rows(
                    baseline / "case_{}_target_line_trips.csv".format(case)
                ),
                "paired_target_riders_n": utility.get("_count", np.nan),
                "paired_target_trips_n": trips.get("_count", np.nan),
                "mean_delta_utility": pd.to_numeric(
                    utility.get("mean_delta_score"), errors="coerce"
                ),
                "share_better": pd.to_numeric(utility.get("share_better"), errors="coerce"),
                "share_worse": pd.to_numeric(utility.get("share_worse"), errors="coerce"),
                "mean_delta_journey_min": pd.to_numeric(
                    trips.get("mean_delta_journey_min"), errors="coerce"
                ),
                "drt_users": pd.to_numeric(adoption_row.get("drt_users"), errors="coerce"),
                "drt_containing_trip_keys": pd.to_numeric(
                    adoption_row.get("drt_containing_trip_keys"), errors="coerce"
                ),
                "network_summary_present": int(
                    (network_root / scenario / "network_summary.csv").exists()
                ),
                "network_hourly_present": int(
                    (network_root / scenario / "network_by_hour.csv").exists()
                ),
            }
        )
    return pd.DataFrame(rows)


def build_coverage(manifest, analysis_root):
    scenario_root = analysis_root / "02_scenarios"
    network_root = analysis_root / "03_network"
    checks = {
        "has_utility": "utility_summary.csv",
        "has_trip_impacts": "trip_level_impacts.csv.gz",
        "has_mode_transition": "mode_transitions_relevant.csv",
        "has_target_bus_transition": "mode_transitions_original_target_bus_trips.csv",
        "has_drt_origins": "drt_mode_origins.csv",
        "has_equity": "equity_utility_target_riders.csv",
        "has_person_level": "person_level_impacts.csv.gz",
        "has_time_of_day": "time_of_day_trip_impacts.csv",
        "has_raw_drt_kpi": "drt_kpi_raw_final_window.csv",
    }
    rows = []
    for _, record in manifest.iterrows():
        if record.get("case") == "B0" or not truthy(record.get("ready", 1)):
            continue
        scenario = str(record["scenario"])
        scenario_dir = scenario_root / scenario
        row = {"scenario": scenario}
        for column, filename in checks.items():
            row[column] = int((scenario_dir / filename).exists())
        row["has_network"] = int((network_root / scenario / "network_summary.csv").exists())
        rows.append(row)
    return pd.DataFrame(rows)


def make_archive(analysis_root, archive_path):
    archive_path = Path(archive_path).resolve()
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w:gz") as archive:
        for number in range(5):
            directory = analysis_root / "{:02d}_{}".format(
                number,
                {
                    0: "preflight",
                    1: "baseline",
                    2: "scenarios",
                    3: "network",
                    4: "RQ_outputs",
                }[number],
            )
            if directory.exists():
                archive.add(directory, arcname=str(Path("analysis_results") / directory.name))
    print("\nArchive written to", archive_path)


def main():
    parser = argparse.ArgumentParser(
        description="Incrementally add formal B6-PTI and C22-PTI results while preserving Case A."
    )
    parser.add_argument("--manifest", default="scenario_manifest.csv")
    parser.add_argument("--config", default="analysis_config.json")
    parser.add_argument("--analysis-root", default="analysis_results")
    parser.add_argument("--scenarios", nargs="+", default=list(DEFAULT_SCENARIOS))
    parser.add_argument(
        "--archive",
        default="ABC_analysis_results_01_04.tar.gz",
        help="Output archive path; pass an empty string to skip packaging.",
    )
    parser.add_argument("--force", action="store_true", help="Replace existing selected B/C folders.")
    parser.add_argument("--keep-staging", action="store_true")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    manifest_path = Path(args.manifest).resolve()
    config_path = Path(args.config).resolve()
    analysis_root = Path(args.analysis_root).resolve()
    baseline_dir = analysis_root / "01_baseline"

    manifest = pd.read_csv(manifest_path, dtype=str).fillna("")
    if "B0" not in set(manifest["scenario"]):
        raise SystemExit("The manifest must contain B0.")
    missing_scenarios = sorted(set(args.scenarios) - set(manifest["scenario"]))
    if missing_scenarios:
        raise SystemExit("Scenarios missing from manifest: " + ", ".join(missing_scenarios))
    selected_rows = manifest[manifest["scenario"].isin(args.scenarios)]
    not_ready = selected_rows[~selected_rows["ready"].map(truthy)]["scenario"].tolist()
    if not_ready:
        raise SystemExit("Selected scenarios are not marked ready: " + ", ".join(not_ready))
    if not baseline_dir.exists():
        raise SystemExit(
            "Existing baseline cohort directory is required: {}\n"
            "Run 01_build_baseline_cohorts.py before the incremental step.".format(baseline_dir)
        )

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    staging = analysis_root.parent / ("_bc_incremental_staging_" + timestamp)
    staging.mkdir(parents=True, exist_ok=False)
    incremental_manifest = staging / "incremental_manifest_BC.csv"
    incremental = pd.concat(
        [manifest[manifest["scenario"] == "B0"], selected_rows], ignore_index=True
    )
    incremental.to_csv(incremental_manifest, index=False)

    try:
        run_python(
            script_dir,
            "00_preflight.py",
            [
                "--manifest", incremental_manifest,
                "--config", config_path,
                "--out", staging / "00_preflight",
                "--strict",
            ],
        )
        run_python(
            script_dir,
            "02_analyse_scenarios.py",
            [
                "--manifest", incremental_manifest,
                "--config", config_path,
                "--baseline-dir", baseline_dir,
                "--out", staging / "02_scenarios",
            ],
        )
        run_python(
            script_dir,
            "03_analyse_network_events.py",
            [
                "--manifest", incremental_manifest,
                "--config", config_path,
                "--baseline-dir", baseline_dir,
                "--out", staging / "03_network",
            ],
        )

        # Validate the staged products before changing the established Case A results.
        for scenario in args.scenarios:
            staged_dir = staging / "02_scenarios" / scenario
            missing = [name for name in REQUIRED_SCENARIO_FILES if not (staged_dir / name).exists()]
            if missing:
                raise SystemExit(
                    "Staged analysis for {} is incomplete: {}".format(
                        scenario, ", ".join(missing)
                    )
                )

        backup = analysis_root / ("incremental_backup_" + timestamp)
        backup.mkdir(parents=True, exist_ok=True)
        for relative in (
            Path("02_scenarios/analysis_inventory.csv"),
            Path("03_network/network_comparison_vs_B0.csv"),
        ):
            existing = analysis_root / relative
            if existing.exists():
                target = backup / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(existing, target)

        # Merge only B/C products. Existing Case A scenario folders remain untouched.
        for scenario in args.scenarios:
            copy_scenario_directory(
                staging / "02_scenarios" / scenario,
                analysis_root / "02_scenarios" / scenario,
                args.force,
            )
            staged_network = staging / "03_network" / scenario
            if staged_network.exists():
                copy_scenario_directory(
                    staged_network,
                    analysis_root / "03_network" / scenario,
                    args.force,
                )

        merge_by_key(
            analysis_root / "02_scenarios/analysis_inventory.csv",
            staging / "02_scenarios/analysis_inventory.csv",
            analysis_root / "02_scenarios/analysis_inventory.csv",
            "scenario",
        )
        merge_by_key(
            analysis_root / "03_network/network_comparison_vs_B0.csv",
            staging / "03_network/network_comparison_vs_B0.csv",
            analysis_root / "03_network/network_comparison_vs_B0.csv",
            "scenario",
        )

        for filename in ("B0_network_summary.csv", "B0_network_by_hour.csv"):
            staged_file = staging / "03_network" / filename
            destination = analysis_root / "03_network" / filename
            if staged_file.exists() and not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(staged_file, destination)

        # Rebuild the complete outputs from A+B+C and refresh the full preflight record.
        run_python(
            script_dir,
            "00_preflight.py",
            [
                "--manifest", manifest_path,
                "--config", config_path,
                "--out", analysis_root / "00_preflight",
                "--strict",
            ],
        )
        run_python(
            script_dir,
            "04_build_rq_outputs.py",
            [
                "--manifest", manifest_path,
                "--baseline-dir", baseline_dir,
                "--scenario-dir", analysis_root / "02_scenarios",
                "--network-dir", analysis_root / "03_network",
                "--out", analysis_root / "04_RQ_outputs",
            ],
        )

        qa = build_bc_qa(analysis_root, args.scenarios)
        coverage = build_coverage(manifest, analysis_root)
        rq_dir = analysis_root / "04_RQ_outputs"
        rq_dir.mkdir(parents=True, exist_ok=True)
        qa.to_csv(rq_dir / "BC_incremental_QA.csv", index=False)
        coverage.to_csv(rq_dir / "ABC_analysis_coverage.csv", index=False)

        print("\nB/C incremental QA")
        print(qa.to_string(index=False))
        if (qa["required_files_present"] != qa["required_files_total"]).any():
            raise SystemExit("B/C QA failed after merge.")

        if args.archive:
            make_archive(analysis_root, args.archive)
    finally:
        if args.keep_staging:
            print("Staging directory retained:", staging)
        elif staging.exists():
            shutil.rmtree(staging)


if __name__ == "__main__":
    main()
