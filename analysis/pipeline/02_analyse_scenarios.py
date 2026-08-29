from pathlib import Path
from collections import Counter
import argparse
import json
import numpy as np
import pandas as pd

from common import *


def load_person_set(path):
    if not Path(path).exists():
        return set()
    df = pd.read_csv(path, dtype=str)
    c = choose_col(df.columns, ["person_id", "person", "personId"])
    return set(df[c].dropna().astype(str)) if c else set()


def load_trip_key_set(path):
    if not Path(path).exists():
        return set()
    df = pd.read_csv(path, dtype=str)
    pc = choose_col(df.columns, ["person_id", "person"])
    tc = choose_col(df.columns, ["trip_key", "trip_number", "trip_id"])
    if not pc or not tc:
        return set()
    return set(zip(df[pc].astype(str), df[tc].astype(str)))


def utility_rows(people):
    cohorts = {
        "all_matched": pd.Series(True, index=people.index),
        "baseline_target_line_riders": people.get("baseline_target_line_rider", False),
        "scenario_drt_users": people.get("scenario_drt_user", False),
    }
    if "baseline_target_line_rider" in people.columns and "scenario_drt_user" in people.columns:
        cohorts["target_line_riders_using_drt"] = people["baseline_target_line_rider"] & people["scenario_drt_user"]
        cohorts["target_line_riders_not_using_drt"] = people["baseline_target_line_rider"] & ~people["scenario_drt_user"]
    rows = []
    for name, mask in cohorts.items():
        if isinstance(mask, bool):
            continue
        x = people[mask]
        d = pd.to_numeric(x["delta_score"], errors="coerce").dropna()
        if len(d):
            rows.append({
                "cohort": name, "n": int(len(d)),
                "mean_delta_score": float(d.mean()), "median_delta_score": float(d.median()),
                "p10_delta_score": float(d.quantile(.10)), "p25_delta_score": float(d.quantile(.25)),
                "p75_delta_score": float(d.quantile(.75)), "p90_delta_score": float(d.quantile(.90)),
                "share_better": float((d > 1e-9).mean()), "share_worse": float((d < -1e-9).mean()),
                "share_unchanged": float((d.abs() <= 1e-9).mean()),
            })
    return pd.DataFrame(rows)


def trip_outcome_summary(trips):
    rows = []
    cohorts = {
        "all_compared_relevant_trips": pd.Series(True, index=trips.index),
        "baseline_target_line_trips": trips.get("baseline_target_line_trip", False),
        "scenario_drt_containing_trips": trips.get("scenario_drt_trip", False),
    }
    if "baseline_target_line_trip" in trips.columns and "scenario_drt_trip" in trips.columns:
        cohorts["target_line_trips_using_drt"] = trips["baseline_target_line_trip"] & trips["scenario_drt_trip"]
        cohorts["target_line_trips_not_using_drt"] = trips["baseline_target_line_trip"] & ~trips["scenario_drt_trip"]
    for name, mask in cohorts.items():
        if isinstance(mask, bool):
            continue
        x = trips[mask]
        if x.empty:
            continue
        row = {"cohort": name, "n_trips": int(len(x))}
        if "delta_journey_sec" in x:
            d = pd.to_numeric(x["delta_journey_sec"], errors="coerce").dropna() / 60.0
            if len(d):
                row.update({
                    "mean_delta_journey_min": float(d.mean()), "median_delta_journey_min": float(d.median()),
                    "p90_delta_journey_min": float(d.quantile(.90)), "p95_delta_journey_min": float(d.quantile(.95)),
                    "share_journey_time_improved": float((d < 0).mean()),
                })
        if "b0_wait_sec" in x:
            bw = pd.to_numeric(x["b0_wait_sec"], errors="coerce").dropna() / 60.0
            if len(bw):
                row.update({
                    "b0_wait_mean_min": float(bw.mean()), "b0_wait_median_min": float(bw.median()),
                    "b0_wait_p90_min": float(bw.quantile(.90)), "b0_wait_p95_min": float(bw.quantile(.95)),
                    "b0_wait_max_min": float(bw.max()), "b0_wait_cv": cv(bw), "b0_wait_gini": gini(bw),
                })
        if "scenario_wait_sec" in x:
            w = pd.to_numeric(x["scenario_wait_sec"], errors="coerce").dropna() / 60.0
            if len(w):
                row.update({
                    "scenario_wait_mean_min": float(w.mean()), "scenario_wait_median_min": float(w.median()),
                    "scenario_wait_p90_min": float(w.quantile(.90)), "scenario_wait_p95_min": float(w.quantile(.95)),
                    "scenario_wait_max_min": float(w.max()), "scenario_wait_cv": cv(w), "scenario_wait_gini": gini(w),
                })
        if "delta_departure_sec" in x:
            dd = pd.to_numeric(x["delta_departure_sec"], errors="coerce").dropna() / 60.0
            if len(dd):
                row["mean_delta_departure_min"] = float(dd.mean())
                row["mean_abs_departure_shift_min"] = float(dd.abs().mean())
        if "delta_trip_distance_m" in x:
            dist = pd.to_numeric(x["delta_trip_distance_m"], errors="coerce").dropna() / 1000.0
            if len(dist):
                row["mean_delta_trip_distance_km"] = float(dist.mean())
        if "delta_wait_sec" in x:
            dw = pd.to_numeric(x["delta_wait_sec"], errors="coerce").dropna() / 60.0
            if len(dw):
                row["mean_delta_wait_min"] = float(dw.mean())
                row["median_delta_wait_min"] = float(dw.median())
        rows.append(row)
    return pd.DataFrame(rows)


def classify_transition(r):
    b = str(r.get("b0_mode", "")).lower()
    s = str(r.get("scenario_mode", "")).lower()
    target = bool(r.get("baseline_target_line_trip", False))
    drt = bool(r.get("scenario_drt_trip", False))
    if target and drt:
        return "target_bus_to_DRT"
    if target and ("car" in s):
        return "target_bus_to_car"
    if target and ("walk" in s):
        return "target_bus_to_walk"
    if target and ("bike" in s or "bicycle" in s):
        return "target_bus_to_bike"
    if target and ("pt" in s or "transit" in s):
        return "target_bus_to_other_PT"
    if drt and "car" in b:
        return "car_to_DRT"
    if drt and ("walk" in b or "bike" in b or "bicycle" in b):
        return "active_mode_to_DRT"
    if drt and ("pt" in b or "transit" in b):
        return "other_PT_to_DRT"
    if drt:
        return "other_mode_to_DRT"
    if target:
        return "target_bus_to_other"
    return "other_transition"


def build_transition_tables(tripcmp):
    if tripcmp.empty:
        return pd.DataFrame(), pd.DataFrame()
    x = tripcmp.copy()
    x["b0_effective_mode"] = np.where(x["baseline_target_line_trip"], "TARGET_BUS", x["b0_mode"].astype(str))
    x["scenario_effective_mode"] = np.where(x["scenario_drt_trip"], "DRT_CONTAINING", x["scenario_mode"].astype(str))
    x["transition_class"] = x.apply(classify_transition, axis=1)
    alltab = x.groupby(["b0_effective_mode", "scenario_effective_mode", "transition_class"], dropna=False).size().reset_index(name="trips")
    alltab["share_of_compared_relevant_trips"] = alltab["trips"] / alltab["trips"].sum()
    target = x[x["baseline_target_line_trip"]].copy()
    if target.empty:
        targettab = pd.DataFrame()
    else:
        targettab = target.groupby(["scenario_effective_mode", "transition_class"], dropna=False).size().reset_index(name="trips")
        targettab["share_of_original_target_bus_trips"] = targettab["trips"] / targettab["trips"].sum()
    return alltab, targettab


def time_of_day_summary(tripcmp):
    if tripcmp.empty or "b0_dep_sec" not in tripcmp.columns:
        return pd.DataFrame()
    x = tripcmp.copy()
    x["hour"] = np.floor(pd.to_numeric(x["b0_dep_sec"], errors="coerce") / 3600).astype("Int64")
    rows = []
    for h, g in x.groupby("hour", dropna=True):
        row = {
            "hour": int(h), "compared_trips": len(g),
            "target_line_trips": int(g["baseline_target_line_trip"].sum()),
            "drt_containing_trips": int(g["scenario_drt_trip"].sum()),
        }
        if "delta_journey_sec" in g:
            d = pd.to_numeric(g["delta_journey_sec"], errors="coerce").dropna() / 60
            if len(d): row["mean_delta_journey_min"] = float(d.mean())
        if "scenario_wait_sec" in g:
            w = pd.to_numeric(g.loc[g["scenario_drt_trip"], "scenario_wait_sec"], errors="coerce").dropna() / 60
            if len(w):
                row["drt_wait_mean_min"] = float(w.mean()); row["drt_wait_p95_min"] = float(w.quantile(.95))
        rows.append(row)
    return pd.DataFrame(rows)


def equity_trip_summary(tripcmp, person_impacts):
    if tripcmp.empty or person_impacts.empty:
        return pd.DataFrame()
    group_cols = [c for c in ["income_group", "age_group", "gender_group", "car_availability_group", "employment_group"] if c in person_impacts.columns]
    if not group_cols:
        return pd.DataFrame()
    attrs = person_impacts[["person_id"] + group_cols].drop_duplicates("person_id")
    x = tripcmp.merge(attrs, on="person_id", how="left")
    x = x[x["baseline_target_line_trip"]].copy()
    rows = []
    for gc in group_cols:
        dim = gc.replace("_group", "")
        for g, gg in x.groupby(gc, dropna=False, observed=False):
            row = {"dimension": dim, "group": str(g), "target_bus_trips": int(len(gg))}
            row["share_target_trips_using_drt"] = float(gg["scenario_drt_trip"].mean()) if len(gg) else np.nan
            row["share_target_trips_to_car"] = float(gg["scenario_mode"].astype(str).str.contains("car", case=False, na=False).mean())
            if "delta_journey_sec" in gg:
                d = pd.to_numeric(gg["delta_journey_sec"], errors="coerce").dropna() / 60
                if len(d): row["mean_delta_journey_min"] = float(d.mean())
            if "scenario_wait_sec" in gg:
                w = pd.to_numeric(gg["scenario_wait_sec"], errors="coerce").dropna() / 60
                if len(w):
                    row["scenario_wait_mean_min"] = float(w.mean())
                    row["scenario_wait_p95_min"] = float(w.quantile(.95))
            if "delta_wait_sec" in gg:
                dw = pd.to_numeric(gg["delta_wait_sec"], errors="coerce").dropna() / 60
                if len(dw): row["mean_delta_wait_min"] = float(dw.mean())
            rows.append(row)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description="Core scenario analysis: utility, service, mode transitions, equity, DRT resources.")
    ap.add_argument("--manifest", default="scenario_manifest.csv")
    ap.add_argument("--config", default="analysis_config.json")
    ap.add_argument("--baseline-dir", default="analysis_results/01_baseline")
    ap.add_argument("--out", default="analysis_results/02_scenarios")
    args = ap.parse_args()

    man = read_manifest(args.manifest)
    cfg = json.load(open(args.config))
    fs, fe = int(cfg["final_iteration_start"]), int(cfg["final_iteration_end"])
    drt_regex = cfg["drt_mode_regex"]
    base_dir = Path(args.baseline_dir)
    outroot = Path(args.out); outroot.mkdir(parents=True, exist_ok=True)

    b0row = man[man["case"] == "B0"].iloc[0]
    b0dir = resolve_dir(b0row["output_dir"])
    if not b0dir:
        raise SystemExit("B0 output directory missing")
    b0plans = find_file(b0dir, ["*output_experienced_plans.xml.gz", "*experienced_plans.xml.gz", "*output_plans.xml.gz", "*output_plans.xml"])
    b0trips = find_file(b0dir, ["*output_trips.csv.gz", "*output_trips.csv", "*trips.csv.gz"])
    if not b0plans or not b0trips:
        raise SystemExit("B0 plans and trips required")

    # Cache B0 person attributes/scores once.
    cache = outroot / "_cache"; cache.mkdir(exist_ok=True)
    b0_person_file = cache / "B0_person_scores_attributes.csv.gz"
    if b0_person_file.exists():
        b0p = pd.read_csv(b0_person_file, dtype=str)
        b0p["score"] = pd.to_numeric(b0p["score"], errors="coerce")
    else:
        print("Parsing B0 experienced plans once...")
        b0p = parse_person_scores_attributes(b0plans)
        b0p.to_csv(b0_person_file, index=False, compression="gzip")
    b0p = b0p.rename(columns={c: ("b0_" + c if c != "person_id" else c) for c in b0p.columns})
    # Common Berlin-wide B0 attribute reference so income-group cut-points are identical
    # across A/B/C rather than silently changing by case.
    b0_equity_reference = b0p.copy()
    b0_equity_reference.rename(columns={c: c[3:] for c in b0_equity_reference.columns if c.startswith("b0_") and c != "b0_score"}, inplace=True)

    conv0 = convergence_summary(b0dir, fs, fe)
    conv0.to_csv(outroot / "B0_convergence.csv", index=False)

    # First pass: discover DRT-containing trips/users for every ready scenario.
    scenarios = {}
    union_relevant = set()
    for _, r in man.iterrows():
        if r["case"] == "B0" or not is_ready(r):
            continue
        od = resolve_dir(r["output_dir"])
        if not od:
            print("SKIP", r["scenario"], "- output_dir missing/EDIT_ME")
            continue
        tripf = find_file(od, ["*output_trips.csv.gz", "*output_trips.csv", "*trips.csv.gz"])
        if not tripf:
            print("SKIP", r["scenario"], "- trips missing")
            continue
        legf = find_file(od, ["*output_legs.csv.gz", "*output_legs.csv", "*legs.csv.gz"])
        target_people = load_person_set(base_dir / f"case_{r['case']}_target_line_persons.csv")
        target_trip_keys = load_trip_key_set(base_dir / f"case_{r['case']}_target_line_trips.csv")

        legkeys, legusers = scan_drt_leg_keys(legf, drt_regex) if legf else (set(), set())
        print("Pass 1 trips:", r["scenario"])
        modes, mainkeys, mainusers, _, _ = scan_trips(tripf, keep_persons=None, drt_mode_regex=drt_regex)
        drt_keys = legkeys | mainkeys
        drt_users = legusers | mainusers | {p for p, _ in drt_keys}
        # Fallback only when trip/leg outputs expose no DRT at all. This may scan a large
        # events file, so it is deliberately avoided when output_legs/main_mode suffice.
        if not drt_users and not legf:
            eventf = find_file(od, ["*output_events.xml.gz", "*events.xml.gz", "*output_events.xml"])
            if eventf:
                print("  No DRT trips in legs/main_mode; using event fallback for DRT users")
                drt_users |= scan_drt_users_from_events(eventf, cfg.get("drt_vehicle_regex", r"(?i)drt|taxi"))
        relevant = target_people | drt_users
        union_relevant |= relevant
        scenarios[r["scenario"]] = {
            "row": r, "outdir": od, "tripf": tripf, "legf": legf,
            "target_people": target_people, "target_trip_keys": target_trip_keys,
            "drt_trip_keys": drt_keys, "drt_users": drt_users, "mode_counts": modes,
            "relevant": relevant,
        }

    # One B0 trip scan for union of all relevant people.
    print(f"Scanning B0 trips once for {len(union_relevant):,} relevant persons...")
    b0_modes, _, _, b0det, b0map = scan_trips(b0trips, keep_persons=union_relevant, drt_mode_regex=drt_regex)
    b0norm = normalise_trip_detail(b0det, b0map, "b0")
    b0norm.to_csv(cache / "B0_relevant_trips.csv.gz", index=False, compression="gzip")
    system_mode_table(b0_modes, "B0").to_csv(outroot / "B0_system_mode_share.csv", index=False)

    inventory_rows = []
    for scen, c in scenarios.items():
        r = c["row"]; od = c["outdir"]
        sd = outroot / scen; sd.mkdir(parents=True, exist_ok=True)
        print("\nANALYSING", scen)

        # QA / convergence
        conv = convergence_summary(od, fs, fe)
        conv.to_csv(sd / "convergence.csv", index=False)

        # DRT operational resource/service stats
        can, raw = extract_drt_kpis(od, fs, fe, fleet=r.get("fleet", np.nan))
        pd.DataFrame([can]).to_csv(sd / "drt_kpi_canonical.csv", index=False)
        pd.DataFrame([raw]).to_csv(sd / "drt_kpi_raw_final_window.csv", index=False)

        # System main-mode share plus explicit DRT-containing-trip count.
        sys = pd.concat([system_mode_table(b0_modes, "B0"), system_mode_table(c["mode_counts"], scen)], ignore_index=True)
        sys.to_csv(sd / "system_main_mode_share.csv", index=False)
        pd.DataFrame([{
            "scenario": scen,
            "drt_containing_trip_keys": len(c["drt_trip_keys"]),
            "drt_users": len(c["drt_users"]),
            "total_scenario_trips_from_main_mode_counts": int(sum(c["mode_counts"].values())),
            "drt_containing_trip_share": safe_div(len(c["drt_trip_keys"]), sum(c["mode_counts"].values())),
        }]).to_csv(sd / "drt_adoption_summary.csv", index=False)

        # Scenario trip detail for relevant persons.
        _, _, _, sdet, smap = scan_trips(c["tripf"], keep_persons=c["relevant"], drt_mode_regex=drt_regex)
        snorm = normalise_trip_detail(sdet, smap, "scenario")
        bsub = b0norm[b0norm["person_id"].isin(c["relevant"])].copy()
        tripcmp = bsub.merge(snorm, on=["person_id", "trip_key"], how="inner") if not bsub.empty and not snorm.empty else pd.DataFrame()
        if not tripcmp.empty:
            tripcmp["baseline_target_line_trip"] = [(p, t) in c["target_trip_keys"] for p, t in zip(tripcmp["person_id"], tripcmp["trip_key"])]
            tripcmp["scenario_drt_trip"] = [(p, t) in c["drt_trip_keys"] for p, t in zip(tripcmp["person_id"], tripcmp["trip_key"])]
            if "b0_trav_sec" in tripcmp and "scenario_trav_sec" in tripcmp:
                tripcmp["delta_journey_sec"] = pd.to_numeric(tripcmp["scenario_trav_sec"], errors="coerce") - pd.to_numeric(tripcmp["b0_trav_sec"], errors="coerce")
            if "b0_wait_sec" in tripcmp and "scenario_wait_sec" in tripcmp:
                tripcmp["delta_wait_sec"] = pd.to_numeric(tripcmp["scenario_wait_sec"], errors="coerce") - pd.to_numeric(tripcmp["b0_wait_sec"], errors="coerce")
            if "b0_dep_sec" in tripcmp and "scenario_dep_sec" in tripcmp:
                tripcmp["delta_departure_sec"] = pd.to_numeric(tripcmp["scenario_dep_sec"], errors="coerce") - pd.to_numeric(tripcmp["b0_dep_sec"], errors="coerce")
            if "b0_distance_m" in tripcmp and "scenario_distance_m" in tripcmp:
                tripcmp["delta_trip_distance_m"] = pd.to_numeric(tripcmp["scenario_distance_m"], errors="coerce") - pd.to_numeric(tripcmp["b0_distance_m"], errors="coerce")
            tripcmp["transition_class"] = tripcmp.apply(classify_transition, axis=1)
            tripcmp.to_csv(sd / "trip_level_impacts.csv.gz", index=False, compression="gzip")
            trip_outcome_summary(tripcmp).to_csv(sd / "trip_outcome_summary.csv", index=False)
            alltrans, targettrans = build_transition_tables(tripcmp)
            alltrans.to_csv(sd / "mode_transitions_relevant.csv", index=False)
            targettrans.to_csv(sd / "mode_transitions_original_target_bus_trips.csv", index=False)
            drtorigin = tripcmp[tripcmp["scenario_drt_trip"]].groupby(["b0_mode", "transition_class"], dropna=False).size().reset_index(name="trips")
            if not drtorigin.empty:
                drtorigin["share_of_drt_containing_trips"] = drtorigin["trips"] / drtorigin["trips"].sum()
            drtorigin.to_csv(sd / "drt_mode_origins.csv", index=False)
            time_of_day_summary(tripcmp).to_csv(sd / "time_of_day_trip_impacts.csv", index=False)

        # Same-agent utility and equity. B0 attributes are canonical reference.
        planf = find_file(od, ["*output_experienced_plans.xml.gz", "*experienced_plans.xml.gz", "*output_plans.xml.gz", "*output_plans.xml"])
        if planf:
            sp = parse_person_scores_attributes(planf, include_home=False)
            sp = sp[[c for c in sp.columns if c in {"person_id", "score"}]].rename(columns={"score": "scenario_score"})
            ppl = b0p.merge(sp, on="person_id", how="inner")
            ppl["b0_score"] = pd.to_numeric(ppl["b0_score"], errors="coerce")
            ppl["scenario_score"] = pd.to_numeric(ppl["scenario_score"], errors="coerce")
            ppl["delta_score"] = ppl["scenario_score"] - ppl["b0_score"]
            ppl["baseline_target_line_rider"] = ppl["person_id"].isin(c["target_people"])
            ppl["scenario_drt_user"] = ppl["person_id"].isin(c["drt_users"])
            # Rename B0 attribute fields back to human-readable names for grouping.
            ren = {}
            for col in ppl.columns:
                if col.startswith("b0_") and col not in {"b0_score"}:
                    ren[col] = col[3:]
            ppl.rename(columns=ren, inplace=True)
            ppl = add_equity_groups(ppl, reference_df=b0_equity_reference)
            if "income_cutpoints" in ppl.attrs:
                cuts = ppl.attrs["income_cutpoints"]
                pd.DataFrame([{
                    "income_group_reference": "Berlin-wide B0 population attribute distribution",
                    "low_middle_cutpoint": cuts[0], "middle_high_cutpoint": cuts[1]
                }]).to_csv(sd / "equity_group_definitions.csv", index=False)
            ppl.to_csv(sd / "person_level_impacts.csv.gz", index=False, compression="gzip")
            utility_rows(ppl).to_csv(sd / "utility_summary.csv", index=False)
            eq = equity_summary(ppl, primary_mask=ppl["baseline_target_line_rider"])
            eq.to_csv(sd / "equity_utility_target_riders.csv", index=False)
            if not tripcmp.empty:
                equity_trip_summary(tripcmp, ppl).to_csv(sd / "equity_target_trip_behaviour.csv", index=False)

        inventory_rows.append({
            "scenario": scen, "case": r["case"], "target_people": len(c["target_people"]),
            "target_trip_keys": len(c["target_trip_keys"]), "drt_users": len(c["drt_users"]),
            "drt_trip_keys": len(c["drt_trip_keys"]), "relevant_people": len(c["relevant"]),
            "paired_trip_rows": len(tripcmp),
        })

    pd.DataFrame(inventory_rows).to_csv(outroot / "analysis_inventory.csv", index=False)
    print("\nScenario analysis written to", outroot)


if __name__ == "__main__":
    main()
