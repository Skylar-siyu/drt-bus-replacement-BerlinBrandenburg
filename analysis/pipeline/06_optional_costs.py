from pathlib import Path
import argparse
import numpy as np
import pandas as pd

from common import *


def load_assumptions(path):
    df = pd.read_csv(path)
    vals = {}
    for _, r in df.iterrows():
        try:
            vals[str(r["parameter"])] = float(r["value"])
        except Exception:
            pass
    return vals


def main():
    ap = argparse.ArgumentParser(description="OPTIONAL monetised cost module. Runs only with explicit cost assumptions.")
    ap.add_argument("--manifest", default="scenario_manifest.csv")
    ap.add_argument("--assumptions", default="optional_cost_assumptions.csv")
    ap.add_argument("--baseline-dir", default="analysis_results/01_baseline")
    ap.add_argument("--scenario-dir", default="analysis_results/02_scenarios")
    ap.add_argument("--out", default="analysis_results/06_optional_costs")
    args = ap.parse_args()

    vals = load_assumptions(args.assumptions)
    required = ["DRT_vehicle_hour_cost", "DRT_vehicle_km_cost"]
    if not all(k in vals for k in required):
        print("Cost module skipped: fill at least DRT_vehicle_hour_cost and DRT_vehicle_km_cost with defensible sourced values.")
        return

    man = read_manifest(args.manifest)
    baseops_file = Path(args.baseline_dir) / "baseline_target_line_operational_summary.csv"
    baseops = pd.read_csv(baseops_file) if baseops_file.exists() else pd.DataFrame()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    rows = []
    for _, r in man.iterrows():
        if r["case"] == "B0" or not is_ready(r):
            continue
        kf = Path(args.scenario_dir) / r["scenario"] / "drt_kpi_canonical.csv"
        if not kf.exists():
            continue
        k = pd.read_csv(kf)
        if k.empty:
            continue
        kv = k.iloc[0].to_dict()
        vkt = pd.to_numeric(kv.get("drt_total_vkt_km"), errors="coerce")
        vh = pd.to_numeric(kv.get("drt_vehicle_hours"), errors="coerce")
        if pd.isna(vh) and not pd.isna(r.get("service_hours")) and not pd.isna(r.get("fleet")):
            vh = float(r["service_hours"]) * float(r["fleet"])
        if pd.isna(vkt) or pd.isna(vh):
            continue
        drt_cost = vkt * vals["DRT_vehicle_km_cost"] + vh * vals["DRT_vehicle_hour_cost"]
        if "DRT_fixed_vehicle_day_cost" in vals and not pd.isna(r.get("fleet")):
            drt_cost += float(r["fleet"]) * vals["DRT_fixed_vehicle_day_cost"]
        row = {"scenario": r["scenario"], "case": r["case"], "estimated_DRT_operator_cost_EUR_per_simulated_day": drt_cost,
               "assumption_based": True}

        # Removed-bus cost is only estimated if bus unit costs are explicitly provided.
        bx = baseops[baseops["case"] == r["case"]] if not baseops.empty and "case" in baseops.columns else pd.DataFrame()
        if not bx.empty and "BUS_vehicle_km_cost" in vals:
            bus_vkt = pd.to_numeric(bx.iloc[0].get("bus_vkt_km"), errors="coerce")
            if not pd.isna(bus_vkt):
                bus_cost = bus_vkt * vals["BUS_vehicle_km_cost"]
                # Vehicle-hours are not inferred from bus VKT; only add if future data supports it.
                row["estimated_removed_bus_distance_cost_component_EUR_per_day"] = bus_cost
                row["removed_bus_cost_is_partial"] = True
        rows.append(row)
    pd.DataFrame(rows).to_csv(out / "optional_cost_comparison.csv", index=False)
    print("Optional cost estimates written to", out)


if __name__ == "__main__":
    main()
