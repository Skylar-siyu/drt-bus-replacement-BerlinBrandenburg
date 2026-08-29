from pathlib import Path
import argparse
import json
import pandas as pd

from common import *


def max_iteration(path):
    if not path:
        return None
    try:
        df = read_csv_auto(path)
        c = choose_col(df.columns, ["iteration", "iter"])
        if not c:
            return None
        x = pd.to_numeric(df[c], errors="coerce").dropna()
        return int(x.max()) if len(x) else None
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="Audit final MATSim outputs before dissertation analysis.")
    ap.add_argument("--manifest", default="scenario_manifest.csv")
    ap.add_argument("--config", default="analysis_config.json")
    ap.add_argument("--out", default="analysis_results/00_preflight")
    ap.add_argument("--strict", action="store_true", help="Exit non-zero if a ready scenario is incomplete.")
    args = ap.parse_args()

    man = read_manifest(args.manifest)
    cfg = json.load(open(args.config))
    final_end = int(cfg["final_iteration_end"])
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    rows = []
    for _, r in man.iterrows():
        scen = r["scenario"]
        ready = is_ready(r)
        od = resolve_dir(r.get("output_dir"))
        found = {"events": None, "plans": None, "trips": None, "legs": None, "scorestats": None,
                 "modestats": None, "network": None, "drt_customer": None, "drt_vehicle": None, "drt_sharing": None}
        if od:
            found["events"] = find_file(od, ["*output_events.xml.gz", "*events.xml.gz", "*output_events.xml"])
            found["plans"] = find_file(od, ["*output_experienced_plans.xml.gz", "*experienced_plans.xml.gz", "*output_plans.xml.gz", "*output_plans.xml"])
            found["trips"] = find_file(od, ["*output_trips.csv.gz", "*output_trips.csv", "*trips.csv.gz"])
            found["legs"] = find_file(od, ["*output_legs.csv.gz", "*output_legs.csv", "*legs.csv.gz"])
            found["scorestats"] = find_file(od, ["*scorestats.csv", "*scorestats*.csv"])
            found["modestats"] = find_file(od, ["*modestats.csv", "*modestats*.csv"])
            found["network"] = find_file(od, ["*output_network.xml.gz", "*output_network.xml", "*network.xml.gz", "*network.xml"])
            found["drt_customer"] = find_file(od, ["*drt_customer_stats_drt.csv", "*customer_stats*drt*.csv"])
            found["drt_vehicle"] = find_file(od, ["*drt_vehicle_stats_drt.csv", "*vehicle_stats*drt*.csv"])
            found["drt_sharing"] = find_file(od, ["*drt_sharing_metrics_drt.csv", "*sharing_metrics*drt*.csv"])

        last_it = max_iteration(found["scorestats"])
        issues = []
        if ready:
            if not od:
                issues.append("output_dir_missing_or_EDIT_ME")
            for key in ["plans", "trips", "scorestats"]:
                if not found[key]:
                    issues.append(f"missing_{key}")
            if r["case"] == "B0" and not found["events"]:
                issues.append("missing_events_required_for_baseline_cohorts")
            if last_it is not None and last_it < final_end:
                issues.append(f"scorestats_only_to_it{last_it}")
            if last_it is None:
                issues.append("cannot_verify_final_iteration")
        status = "SKIP_READY0" if not ready else ("OK" if not issues else "ERROR")
        row = {
            "scenario": scen, "case": r["case"], "role": r["role"], "ready": int(ready),
            "output_dir": str(od or r.get("output_dir", "")), "status": status,
            "last_score_iteration": last_it, "issues": "|".join(issues),
        }
        for k, v in found.items():
            row[f"has_{k}"] = int(v is not None)
            row[f"file_{k}"] = str(v or "")
        rows.append(row)

    report = pd.DataFrame(rows)
    report.to_csv(out / "preflight_report.csv", index=False)
    valid = report[(report["ready"] == 1) & (report["status"] == "OK")][["scenario", "case", "output_dir"]]
    valid.to_csv(out / "valid_ready_scenarios.csv", index=False)

    print(report[["scenario", "ready", "status", "last_score_iteration", "issues"]].to_string(index=False))
    errors = report[(report["ready"] == 1) & (report["status"] == "ERROR")]
    if len(errors):
        print("\nReady scenarios with problems are listed in", out / "preflight_report.csv")
        if args.strict:
            raise SystemExit(2)


if __name__ == "__main__":
    main()
