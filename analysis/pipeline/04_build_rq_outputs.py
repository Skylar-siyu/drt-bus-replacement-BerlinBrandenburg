from pathlib import Path
import argparse
import numpy as np
import pandas as pd

from common import *


def read_df(path):
    p = Path(path)
    try:
        return pd.read_csv(p) if p.exists() else pd.DataFrame()
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def pick_cohort(df, cohort):
    if df.empty or "cohort" not in df.columns:
        return {}
    x = df[df["cohort"] == cohort]
    return x.iloc[0].to_dict() if not x.empty else {}


def prefix_dict(d, prefix, skip=None):
    skip = set(skip or [])
    return {prefix + str(k): v for k, v in d.items() if k not in skip}


def transition_shares(path):
    df = read_df(path)
    out = {}
    if df.empty:
        return out
    if "transition_class" in df.columns:
        if "share_of_original_target_bus_trips" in df.columns:
            for cls, g in df.groupby("transition_class"):
                out[f"target_transition_share::{cls}"] = pd.to_numeric(g["share_of_original_target_bus_trips"], errors="coerce").sum()
        else:
            tot = pd.to_numeric(df.get("trips"), errors="coerce").sum()
            for cls, g in df.groupby("transition_class"):
                out[f"target_transition_share::{cls}"] = safe_div(pd.to_numeric(g["trips"], errors="coerce").sum(), tot)
    return out


def drt_origin_shares(path):
    df = read_df(path)
    out = {}
    if df.empty:
        return out
    total = pd.to_numeric(df.get("trips"), errors="coerce").sum()
    for _, r in df.iterrows():
        cls = str(r.get("transition_class", ""))
        out[f"drt_origin_share::{cls}"] = out.get(f"drt_origin_share::{cls}", 0) + safe_div(pd.to_numeric(r.get("trips"), errors="coerce"), total)
    return out


def main():
    ap = argparse.ArgumentParser(description="Build final thesis tables organised by frozen RQ1/RQ2/RQ3 framework.")
    ap.add_argument("--manifest", default="scenario_manifest.csv")
    ap.add_argument("--baseline-dir", default="analysis_results/01_baseline")
    ap.add_argument("--scenario-dir", default="analysis_results/02_scenarios")
    ap.add_argument("--network-dir", default="analysis_results/03_network")
    ap.add_argument("--out", default="analysis_results/04_RQ_outputs")
    args = ap.parse_args()

    man = read_manifest(args.manifest)
    bdir, sroot, nroot = Path(args.baseline_dir), Path(args.scenario_dir), Path(args.network_dir)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    baseops = read_df(bdir / "baseline_target_line_operational_summary.csv")
    netcomp = read_df(nroot / "network_comparison_vs_B0.csv")

    rows = []
    availability = []
    for _, r in man.iterrows():
        if r["case"] == "B0" or not is_ready(r):
            continue
        sd = sroot / r["scenario"]
        if not sd.exists():
            continue
        row = {
            "scenario": r["scenario"], "case": r["case"], "role": r["role"],
            "fleet": r.get("fleet"), "capacity": r.get("capacity"), "service_hours": r.get("service_hours"),
            "pricing_group": r.get("pricing_group"), "monetary_treatment": r.get("monetary_treatment"),
            "rq1_structural": r.get("rq1_structural"), "rq2_design": r.get("rq2_design"), "rq3_distribution": r.get("rq3_distribution"),
        }
        u = read_df(sd / "utility_summary.csv")
        row.update(prefix_dict(pick_cohort(u, "baseline_target_line_riders"), "target_riders::", skip=["cohort"]))
        row.update(prefix_dict(pick_cohort(u, "target_line_riders_using_drt"), "target_riders_using_drt::", skip=["cohort"]))
        row.update(prefix_dict(pick_cohort(u, "all_matched"), "all_agents::", skip=["cohort"]))

        t = read_df(sd / "trip_outcome_summary.csv")
        row.update(prefix_dict(pick_cohort(t, "baseline_target_line_trips"), "target_trips::", skip=["cohort"]))
        row.update(prefix_dict(pick_cohort(t, "target_line_trips_using_drt"), "target_trips_using_drt::", skip=["cohort"]))
        row.update(prefix_dict(pick_cohort(t, "scenario_drt_containing_trips"), "drt_trips::", skip=["cohort"]))

        k = read_df(sd / "drt_kpi_canonical.csv")
        if not k.empty:
            row.update(prefix_dict(k.iloc[0].to_dict(), "drt::"))

        bx = baseops[baseops["case"] == r["case"]] if not baseops.empty and "case" in baseops.columns else pd.DataFrame()
        if not bx.empty:
            b = bx.iloc[0].to_dict()
            row.update(prefix_dict(b, "baseline_bus::", skip=["case"]))
            base_vkt = pd.to_numeric(b.get("bus_vkt_km"), errors="coerce")
            base_board = pd.to_numeric(b.get("boardings"), errors="coerce")
            drt_vkt = pd.to_numeric(row.get("drt::drt_total_vkt_km"), errors="coerce")
            if not pd.isna(base_vkt) and not pd.isna(drt_vkt):
                row["resource::DRT_VKT_to_removed_bus_VKT_ratio"] = safe_div(drt_vkt, base_vkt)
                row["resource::DRT_minus_removed_bus_VKT_km"] = drt_vkt - base_vkt
            if not pd.isna(base_board) and base_board > 0:
                if not pd.isna(r.get("fleet")):
                    row["resource::fleet_per_100_baseline_boardings"] = float(r["fleet"]) / base_board * 100
                if not pd.isna(r.get("fleet")) and not pd.isna(r.get("capacity")):
                    row["resource::nominal_fleet_seats_per_100_baseline_boardings"] = float(r["fleet"]) * float(r["capacity"]) / base_board * 100
                if not pd.isna(drt_vkt):
                    row["resource::DRT_VKT_per_baseline_boarding_km"] = drt_vkt / base_board

        nx = netcomp[netcomp["scenario"] == r["scenario"]] if not netcomp.empty and "scenario" in netcomp.columns else pd.DataFrame()
        if not nx.empty:
            row.update(prefix_dict(nx.iloc[0].to_dict(), "network::", skip=["scenario", "case"]))

        row.update(transition_shares(sd / "mode_transitions_original_target_bus_trips.csv"))
        row.update(drt_origin_shares(sd / "drt_mode_origins.csv"))
        rows.append(row)

        availability.append({
            "scenario": r["scenario"], "case": r["case"],
            "utility": int((sd / "utility_summary.csv").exists()),
            "paired_trip_service": int((sd / "trip_outcome_summary.csv").exists()),
            "mode_transitions": int((sd / "mode_transitions_original_target_bus_trips.csv").exists()),
            "equity": int((sd / "equity_utility_target_riders.csv").exists()),
            "spatial_person_file": int((sd / "person_level_impacts.csv.gz").exists()),
            "DRT_KPI": int((sd / "drt_kpi_canonical.csv").exists()),
            "network_congestion": int(not nx.empty),
            "direct_emissions": int(not nx.empty and any(str(c).startswith("emission::") for c in nx.columns)),
        })

    allsum = pd.DataFrame(rows)
    allsum.to_csv(out / "all_scenario_summary.csv", index=False)
    pd.DataFrame(availability).to_csv(out / "data_availability_matrix.csv", index=False)

    if allsum.empty:
        print("No ready scenario analysis found. Run 02_analyse_scenarios.py first.")
        return

    # RQ1: context suitability. Monetary treatment aligned structural scenarios only.
    rq1 = allsum[allsum["rq1_structural"].astype(str).str.lower().isin(["1", "true", "yes", "y"])].copy()
    order = {"A": 0, "B": 1, "C": 2}
    if not rq1.empty:
        rq1["_order"] = rq1["case"].map(order).fillna(99)
        rq1.sort_values("_order", inplace=True); rq1.drop(columns="_order", inplace=True)
    rq1.to_csv(out / "RQ1_context_suitability_A_B_C.csv", index=False)

    # RQ2: Case A service-design mechanisms.
    rq2 = allsum[(allsum["case"] == "A") & allsum["rq2_design"].astype(str).str.lower().isin(["1", "true", "yes", "y"])].copy()
    rq2.sort_values(["pricing_group", "fleet"], inplace=True, na_position="last")
    rq2.to_csv(out / "RQ2_caseA_intervention_design.csv", index=False)
    for fare in ["FL", "FH"]:
        rq2[rq2["pricing_group"] == fare].sort_values("fleet").to_csv(out / f"RQ2_fleet_sensitivity_{fare}.csv", index=False)
    p8 = rq2[pd.to_numeric(rq2["fleet"], errors="coerce") == 8].copy()
    cat = pd.CategoricalDtype(["FM", "SUB1", "FL", "FH"], ordered=True)
    if not p8.empty:
        p8["_p"] = p8["pricing_group"].astype(cat)
        p8.sort_values("_p", inplace=True); p8.drop(columns="_p", inplace=True)
    p8.to_csv(out / "RQ2_pricing_chain_8veh_FM_SUB1_FL_FH.csv", index=False)

    # RQ3: distributional, mode, spatial and temporal outputs.
    eqs, eqbeh, transitions, origins, temporal, spatial = [], [], [], [], [], []
    for _, r in man.iterrows():
        if r["case"] == "B0" or not is_ready(r):
            continue
        if str(r.get("rq3_distribution", "0")).strip().lower() not in {"1", "true", "yes", "y"}:
            continue
        sd = sroot / r["scenario"]
        for fname, bucket in [
            ("equity_utility_target_riders.csv", eqs), ("equity_target_trip_behaviour.csv", eqbeh),
            ("mode_transitions_original_target_bus_trips.csv", transitions), ("drt_mode_origins.csv", origins),
            ("time_of_day_trip_impacts.csv", temporal),
        ]:
            d = read_df(sd / fname)
            if not d.empty:
                d.insert(0, "scenario", r["scenario"]); d.insert(1, "case", r["case"]); bucket.append(d)
        pf = sd / "person_level_impacts.csv.gz"
        if pf.exists():
            d = pd.read_csv(pf)
            keep = [c for c in ["person_id", "delta_score", "baseline_target_line_rider", "scenario_drt_user", "home_x", "home_y", "home_link",
                                     "income_group", "age_group", "gender_group", "car_availability_group", "employment_group"] if c in d.columns]
            d = d[keep]
            d.insert(0, "scenario", r["scenario"]); d.insert(1, "case", r["case"]); spatial.append(d)

    if eqs: pd.concat(eqs, ignore_index=True).to_csv(out / "RQ3_equity_utility.csv", index=False)
    if eqbeh: pd.concat(eqbeh, ignore_index=True).to_csv(out / "RQ3_equity_mode_and_journey.csv", index=False)
    if transitions: pd.concat(transitions, ignore_index=True).to_csv(out / "RQ3_original_bus_trip_mode_transitions.csv", index=False)
    if origins: pd.concat(origins, ignore_index=True).to_csv(out / "RQ3_DRT_mode_origins.csv", index=False)
    if temporal: pd.concat(temporal, ignore_index=True).to_csv(out / "RQ3_time_of_day_impacts.csv", index=False)
    if spatial: pd.concat(spatial, ignore_index=True).to_csv(out / "RQ3_spatial_person_impacts.csv.gz", index=False, compression="gzip")

    # Multi-stakeholder evidence table: no arbitrary weights and no synthetic total score.
    stakeholder_cols = [
        "scenario", "case", "role",
        "target_riders::mean_delta_score", "target_riders::share_better", "target_riders::share_worse",
        "target_trips::mean_delta_journey_min", "target_trips::scenario_wait_p95_min",
        "drt::rejection_rate", "drt::served_requests", "drt::sharing_factor", "drt::pooling_rate",
        "drt::drt_total_vkt_km", "drt::drt_empty_vkt_km", "drt::empty_vkt_share", "drt::served_requests_per_vehicle",
        "resource::DRT_VKT_to_removed_bus_VKT_ratio",
        "target_transition_share::target_bus_to_DRT", "target_transition_share::target_bus_to_car",
        "drt_origin_share::car_to_DRT", "drt_origin_share::active_mode_to_DRT",
        "network::delta_road_vkt_km", "network::delta_road_delay_h",
    ]
    stakeholder = allsum[[c for c in stakeholder_cols if c in allsum.columns]].copy()
    stakeholder.to_csv(out / "integrated_stakeholder_evidence_matrix.csv", index=False)
    print("RQ-organised thesis outputs written to", out)


if __name__ == "__main__":
    main()
