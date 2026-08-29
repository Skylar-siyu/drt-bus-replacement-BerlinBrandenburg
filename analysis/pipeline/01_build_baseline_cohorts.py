from pathlib import Path
from collections import defaultdict
import argparse
import gzip
import json
import math
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

from common import *


def match_boardings_to_trips(boardings, trips, tol=120, nearest_max=1800):
    if boardings.empty or trips.empty:
        return pd.DataFrame()
    t = trips.copy()
    t["arrival_sec"] = t["b0_dep_sec"] + t["b0_trav_sec"]
    per = {pid: g.sort_values("b0_dep_sec") for pid, g in t.groupby("person_id")}
    rows = []
    for _, b in boardings.iterrows():
        pid = str(b["person_id"]); bt = time_to_seconds(b["time"])
        if pid not in per or pd.isna(bt):
            continue
        g = per[pid]
        direct = g[(g["b0_dep_sec"] - tol <= bt) & (g["arrival_sec"] + tol >= bt)]
        method = "inside_interval"
        if direct.empty:
            dist = np.minimum((bt - g["arrival_sec"]).abs(), (bt - g["b0_dep_sec"]).abs())
            if len(dist) == 0 or dist.min() > nearest_max:
                continue
            direct = g.loc[[dist.idxmin()]]
            method = "nearest"
        r = direct.iloc[0]
        rows.append({
            "person_id": pid, "trip_key": str(r["trip_key"]), "boarding_time_sec": bt,
            "b0_dep_sec": r["b0_dep_sec"], "b0_trav_sec": r["b0_trav_sec"],
            "b0_mode": r["b0_mode"], "match_method": method,
            "line_id": b.get("line_id", ""), "route_id": b.get("route_id", ""),
            "vehicle_id": b.get("vehicle_id", "")
        })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description="Build exact B0 target-line person/trip cohorts and baseline bus operational metrics.")
    ap.add_argument("--manifest", default="scenario_manifest.csv")
    ap.add_argument("--config", default="analysis_config.json")
    ap.add_argument("--out", default="analysis_results/01_baseline")
    args = ap.parse_args()

    man = read_manifest(args.manifest)
    cfg = json.load(open(args.config))
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    b0 = man[man["case"] == "B0"]
    if b0.empty:
        raise SystemExit("Manifest has no B0 row")
    b0dir = resolve_dir(b0.iloc[0]["output_dir"])
    if not b0dir:
        raise SystemExit("B0 output_dir missing")
    events = find_file(b0dir, ["*output_events.xml.gz", "*events.xml.gz", "*output_events.xml"])
    trips = find_file(b0dir, ["*output_trips.csv.gz", "*output_trips.csv", "*trips.csv.gz"])
    network = find_file(b0dir, ["*output_network.xml.gz", "*output_network.xml", "*network.xml.gz", "*network.xml"])
    if not events or not trips:
        raise SystemExit("B0 events and trips are required")

    case_patterns = {}
    for case in sorted(set(man["case"]) - {"B0"}):
        vals = []
        for v in man.loc[man["case"] == case, "target_line_ids"].tolist():
            vals += split_pipe(v)
        if vals:
            case_patterns[case] = sorted(set(vals))
    if not case_patterns:
        raise SystemExit("No target_line_ids in manifest")

    links = parse_network(network) if network else {}
    print(f"Loaded {len(links):,} network links" if links else "Network file absent: baseline target-bus VKT/congestion metrics will be unavailable")

    vehicle_line = {}
    vehicle_route = {}
    occupancy = defaultdict(int)
    boardings = {c: [] for c in case_patterns}
    stats = {c: defaultdict(float) for c in case_patterns}
    route_boardings = {c: defaultdict(int) for c in case_patterns}
    netacc = empty_network_accumulator()
    pending = {}

    with open_binary(events) as fh:
        for _, elem in ET.iterparse(fh, events=("end",)):
            if strip_tag(elem.tag) != "event":
                continue
            a = elem.attrib
            typ = event_type(a); compact = typ.replace(" ", "")
            veh = attr_get(a, ["vehicle", "vehicleId", "vehicle_id"])

            if ("transitdriverstarts" in compact) or ("transit" in typ and "driver" in typ and "start" in typ):
                line = attr_get(a, ["transitLineId", "transitLine", "line", "lineId"])
                route = attr_get(a, ["transitRouteId", "transitRoute", "route", "routeId"])
                if veh and line:
                    vehicle_line[str(veh)] = str(line)
                    vehicle_route[str(veh)] = str(route or "")
                    occupancy[str(veh)] = 0
                    for case, pats in case_patterns.items():
                        if line_matches(line, pats):
                            stats[case]["departures"] += 1
            elif "personentersvehicle" in compact and veh:
                person = attr_get(a, ["person", "personId", "person_id"])
                line = vehicle_line.get(str(veh), "")
                route = vehicle_route.get(str(veh), "")
                if person:
                    for case, pats in case_patterns.items():
                        if line_matches(line, pats):
                            stats[case]["boardings"] += 1
                            route_boardings[case][route] += 1
                            boardings[case].append({
                                "person_id": str(person), "time": attr_get(a, ["time"]),
                                "vehicle_id": str(veh), "line_id": line, "route_id": route,
                            })
                occupancy[str(veh)] += 1
            elif "personleavesvehicle" in compact and veh:
                occupancy[str(veh)] = max(0, occupancy[str(veh)] - 1)
            elif ("linkenter" in compact or "enteredlink" in compact) and veh:
                line = vehicle_line.get(str(veh), "")
                lid = attr_get(a, ["link", "linkId", "link_id"])
                if lid in links:
                    length_km = links[lid]["length"] / 1000.0
                    for case, pats in case_patterns.items():
                        if line_matches(line, pats):
                            stats[case]["bus_vkt_km"] += length_km
                            occ = occupancy[str(veh)]
                            stats[case]["bus_passenger_km"] += occ * length_km
                            if occ <= 0:
                                stats[case]["bus_empty_vkt_km"] += length_km
            elif ("vehicleleavestraffic" in compact or "vehicleleave" in compact) and veh:
                vehicle_line.pop(str(veh), None)
                vehicle_route.pop(str(veh), None)
                occupancy.pop(str(veh), None)
            if links:
                update_network_event(netacc, a, links, pending)
            elem.clear()

    total_net, hourly_net = network_accumulator_to_frames(netacc)
    total_net.to_csv(out / "B0_network_summary.csv", index=False)
    hourly_net.to_csv(out / "B0_network_by_hour.csv", index=False)

    # Write boarding/person cohorts.
    all_target_persons = set()
    summary_rows = []
    for case, rows in boardings.items():
        df = pd.DataFrame(rows)
        if df.empty:
            print("WARNING: no B0 target-line boardings for case", case)
            continue
        df.to_csv(out / f"case_{case}_target_line_boardings.csv.gz", index=False, compression="gzip")
        persons = sorted(set(df["person_id"].astype(str)))
        all_target_persons |= set(persons)
        pd.DataFrame({"person_id": persons}).to_csv(out / f"case_{case}_target_line_persons.csv", index=False)
        s = dict(stats[case])
        s["case"] = case
        s["unique_target_line_persons"] = len(persons)
        if s.get("bus_vkt_km", 0):
            s["bus_empty_vkt_share"] = safe_div(s.get("bus_empty_vkt_km", 0), s["bus_vkt_km"])
            s["bus_distance_weighted_occupancy"] = safe_div(s.get("bus_passenger_km", 0), s["bus_vkt_km"])
        s["route_boardings"] = json.dumps(route_boardings[case], ensure_ascii=False)
        summary_rows.append(s)

    pd.DataFrame(summary_rows).to_csv(out / "baseline_target_line_operational_summary.csv", index=False)

    # Match exact target-line boarding events to B0 trip rows.
    print(f"Scanning B0 trips for {len(all_target_persons):,} target-line riders...")
    _, _, _, det, cmap = scan_trips(trips, keep_persons=all_target_persons, drt_mode_regex=cfg["drt_mode_regex"])
    normdet = normalise_trip_detail(det, cmap, "b0")
    normdet.to_csv(out / "B0_target_rider_trips.csv.gz", index=False, compression="gzip")

    tol = int(cfg.get("trip_match_tolerance_seconds", 120))
    nearest = int(cfg.get("trip_match_max_nearest_seconds", 1800))
    match_summary = []
    for case in case_patterns:
        bf = out / f"case_{case}_target_line_boardings.csv.gz"
        if not bf.exists():
            continue
        bdf = pd.read_csv(bf, dtype=str)
        m = match_boardings_to_trips(bdf, normdet, tol=tol, nearest_max=nearest)
        if m.empty:
            print("WARNING: no target-line boardings matched to B0 trips for", case)
            continue
        m.to_csv(out / f"case_{case}_target_line_boarding_trip_matches.csv.gz", index=False, compression="gzip")
        keys = m[["person_id", "trip_key"]].drop_duplicates()
        keys.to_csv(out / f"case_{case}_target_line_trips.csv", index=False)
        match_summary.append({
            "case": case,
            "boarding_events": len(bdf),
            "matched_boarding_events": len(m),
            "matched_unique_trips": len(keys),
            "match_rate": len(m) / len(bdf) if len(bdf) else np.nan,
            "nearest_match_share": (m["match_method"] == "nearest").mean(),
        })
    pd.DataFrame(match_summary).to_csv(out / "target_trip_match_quality.csv", index=False)
    print("Baseline cohorts written to", out)


if __name__ == "__main__":
    main()
