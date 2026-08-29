from pathlib import Path
import argparse
import json
import re
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

from common import *


def main():
    ap = argparse.ArgumentParser(description="Secondary system analysis: road VKT, congestion/delay, direct emission events.")
    ap.add_argument("--manifest", default="scenario_manifest.csv")
    ap.add_argument("--config", default="analysis_config.json")
    ap.add_argument("--baseline-dir", default="analysis_results/01_baseline")
    ap.add_argument("--out", default="analysis_results/03_network")
    args = ap.parse_args()

    man = read_manifest(args.manifest)
    cfg = json.load(open(args.config))
    drt_vehicle_re = re.compile(cfg.get("drt_vehicle_regex", r"(?i)drt|taxi"))
    outroot = Path(args.out); outroot.mkdir(parents=True, exist_ok=True)
    basedir = Path(args.baseline_dir)

    b0row = man[man["case"] == "B0"].iloc[0]
    b0dir = resolve_dir(b0row["output_dir"])
    if not b0dir:
        raise SystemExit("B0 output dir missing")
    network = find_file(b0dir, ["*output_network.xml.gz", "*output_network.xml", "*network.xml.gz", "*network.xml"])
    links = parse_network(network) if network else {}
    if not links:
        raise SystemExit("Network file not found; cannot calculate road VKT/delay")

    b0summary_file = basedir / "B0_network_summary.csv"
    b0hour_file = basedir / "B0_network_by_hour.csv"
    b0summary = pd.read_csv(b0summary_file) if b0summary_file.exists() else pd.DataFrame()
    b0hour = pd.read_csv(b0hour_file) if b0hour_file.exists() else pd.DataFrame()
    if not b0summary.empty:
        b0summary.to_csv(outroot / "B0_network_summary.csv", index=False)
    if not b0hour.empty:
        b0hour.to_csv(outroot / "B0_network_by_hour.csv", index=False)

    comparison = []
    for _, r in man.iterrows():
        if r["case"] == "B0" or not is_ready(r):
            continue
        if str(r.get("network_events", "0")).strip().lower() not in {"1", "true", "yes", "y"}:
            continue
        od = resolve_dir(r["output_dir"])
        if not od:
            continue
        events = find_file(od, ["*output_events.xml.gz", "*events.xml.gz", "*output_events.xml"])
        if not events:
            print("SKIP network analysis", r["scenario"], "- events missing")
            continue
        print("Scanning network events:", r["scenario"])
        acc = empty_network_accumulator(); pending = {}
        drtacc = empty_network_accumulator(); drtpending = {}
        drt_regex_vehicle_ids = set()

        with open_binary(events) as fh:
            for _, elem in ET.iterparse(fh, events=("end",)):
                if strip_tag(elem.tag) != "event":
                    continue
                a = elem.attrib
                update_network_event(acc, a, links, pending)
                veh = attr_get(a, ["vehicle", "vehicleId", "vehicle_id"])
                if veh and drt_vehicle_re.search(str(veh)):
                    drt_regex_vehicle_ids.add(str(veh))
                    update_network_event(drtacc, a, links, drtpending)
                elem.clear()

        total, hours = network_accumulator_to_frames(acc)
        dtotal, dhours = network_accumulator_to_frames(drtacc)
        for c in list(dtotal.columns):
            dtotal.rename(columns={c: "drt_regex_" + c}, inplace=True)
        if not dhours.empty:
            dhours.rename(columns={c: (c if c == "hour" else "drt_regex_" + c) for c in dhours.columns}, inplace=True)
        merged_total = pd.concat([total.reset_index(drop=True), dtotal.reset_index(drop=True)], axis=1)
        merged_total["drt_regex_vehicle_ids_detected"] = len(drt_regex_vehicle_ids)
        sd = outroot / r["scenario"]; sd.mkdir(exist_ok=True)
        merged_total.to_csv(sd / "network_summary.csv", index=False)
        if not dhours.empty:
            hours = hours.merge(dhours, on="hour", how="outer").sort_values("hour")
        hours.to_csv(sd / "network_by_hour.csv", index=False)

        row = {"scenario": r["scenario"], "case": r["case"]}
        for col in merged_total.columns:
            row[col] = merged_total.iloc[0][col]
        if not b0summary.empty:
            for metric in ["road_vkt_km", "road_travel_time_h", "road_delay_h", "link_traversals", "unique_road_vehicles"]:
                if metric in merged_total.columns and metric in b0summary.columns:
                    b = pd.to_numeric(b0summary.iloc[0][metric], errors="coerce")
                    s = pd.to_numeric(merged_total.iloc[0][metric], errors="coerce")
                    row["delta_" + metric] = s - b
                    row["relative_delta_" + metric] = safe_div(s - b, b)
        # Direct emission event deltas only when the same pollutant exists in both files.
        if not b0summary.empty:
            for col in merged_total.columns:
                if col.startswith("emission::") and col in b0summary.columns:
                    b = pd.to_numeric(b0summary.iloc[0][col], errors="coerce")
                    s = pd.to_numeric(merged_total.iloc[0][col], errors="coerce")
                    row["delta_" + col] = s - b
                    row["relative_delta_" + col] = safe_div(s - b, b)
        comparison.append(row)

    pd.DataFrame(comparison).to_csv(outroot / "network_comparison_vs_B0.csv", index=False)
    print("Network/system analysis written to", outroot)


if __name__ == "__main__":
    main()
