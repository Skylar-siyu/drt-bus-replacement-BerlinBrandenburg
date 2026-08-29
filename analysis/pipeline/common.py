from __future__ import annotations

from pathlib import Path
from collections import Counter, defaultdict
import csv
import gzip
import json
import math
import re
import statistics
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd


# ----------------------------
# General IO helpers
# ----------------------------

def norm(s):
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def choose_col(columns, candidates):
    cols = list(columns)
    by_norm = {norm(c): c for c in cols}
    for cand in candidates:
        n = norm(cand)
        if n in by_norm:
            return by_norm[n]
    for cand in candidates:
        n = norm(cand)
        if not n:
            continue
        for k, original in by_norm.items():
            if n in k or k in n:
                return original
    return None


def sniff_sep(path):
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
        line = fh.readline()
    counts = {";": line.count(";"), ",": line.count(","), "\t": line.count("\t")}
    return max(counts, key=counts.get) if max(counts.values()) else ";"


def read_csv_auto(path, **kwargs):
    return pd.read_csv(path, sep=sniff_sep(path), **kwargs)


def find_file(outdir, patterns):
    if not outdir:
        return None
    outdir = Path(outdir)
    if not outdir.exists():
        return None
    for pattern in patterns:
        hits = sorted(outdir.glob(pattern))
        if hits:
            return hits[0]
    return None


def resolve_dir(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.upper().startswith("EDIT_ME"):
        return None
    p = Path(s)
    return p if p.exists() else None


def read_manifest(path):
    df = pd.read_csv(path, dtype=str).fillna("")
    for col in ["fleet", "capacity", "service_hours"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def is_ready(row):
    return str(row.get("ready", "1")).strip().lower() in {"1", "true", "yes", "y"}


def split_pipe(value):
    return [x.strip() for x in str(value or "").split("|") if x.strip()]


def line_matches(line_id, patterns):
    lid = str(line_id or "")
    for p in patterns:
        p = str(p)
        if lid == p or lid.startswith(p + "---") or p == lid.split("---")[0]:
            return True
    return False


def time_to_seconds(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return np.nan
    if isinstance(v, (int, float, np.number)):
        return float(v)
    s = str(v).strip()
    if not s:
        return np.nan
    try:
        return float(s)
    except ValueError:
        pass
    parts = s.split(":")
    try:
        if len(parts) == 3:
            h, m, sec = parts
            return 3600 * float(h) + 60 * float(m) + float(sec)
        if len(parts) == 2:
            m, sec = parts
            return 60 * float(m) + float(sec)
    except Exception:
        return np.nan
    return np.nan


def safe_div(a, b):
    try:
        if b is None or pd.isna(b) or float(b) == 0:
            return np.nan
        return float(a) / float(b)
    except Exception:
        return np.nan


def gini(values):
    x = pd.to_numeric(pd.Series(values), errors="coerce").dropna().to_numpy(float)
    if len(x) == 0:
        return np.nan
    if np.any(x < 0):
        x = x - x.min()
    if np.allclose(x, 0):
        return 0.0
    x = np.sort(x)
    n = len(x)
    return float((2 * np.sum((np.arange(1, n + 1)) * x) / (n * np.sum(x))) - (n + 1) / n)


def cv(values):
    x = pd.to_numeric(pd.Series(values), errors="coerce").dropna().to_numpy(float)
    if len(x) < 2:
        return np.nan
    m = np.mean(x)
    if abs(m) < 1e-12:
        return np.nan
    return float(np.std(x, ddof=1) / m)


def describe_series(values, prefix=""):
    x = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    if len(x) == 0:
        return {}
    p = (prefix + "_" if prefix else "")
    return {
        p + "n": int(len(x)),
        p + "mean": float(x.mean()),
        p + "median": float(x.median()),
        p + "p10": float(x.quantile(.10)),
        p + "p25": float(x.quantile(.25)),
        p + "p75": float(x.quantile(.75)),
        p + "p90": float(x.quantile(.90)),
        p + "p95": float(x.quantile(.95)),
        p + "max": float(x.max()),
        p + "cv": cv(x),
        p + "gini": gini(x),
    }


# ----------------------------
# MATSim XML helpers
# ----------------------------

def strip_tag(tag):
    return tag.split("}")[-1].lower()


def event_type(attrs):
    return str(attrs.get("type", "")).lower().replace("_", " ").replace("-", " ")


def attr_get(attrs, names):
    lower = {str(k).lower(): v for k, v in attrs.items()}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return None


def open_binary(path):
    return gzip.open(path, "rb") if str(path).endswith(".gz") else open(path, "rb")


def parse_network(path):
    """Return link_id -> {length, freespeed, allowed_modes, road}."""
    links = {}
    if not path or not Path(path).exists():
        return links
    with open_binary(path) as fh:
        for _, elem in ET.iterparse(fh, events=("end",)):
            if strip_tag(elem.tag) != "link":
                continue
            a = elem.attrib
            lid = a.get("id")
            if lid is None:
                elem.clear(); continue
            try:
                length = float(a.get("length", 0) or 0)
            except Exception:
                length = 0.0
            try:
                freespeed = float(a.get("freespeed", 0) or 0)
            except Exception:
                freespeed = 0.0
            modes_raw = a.get("modes", a.get("allowedModes", "")) or ""
            modes = {m.strip().lower() for m in re.split(r"[,;\s]+", modes_raw) if m.strip()}
            # OpenBerlin road links normally allow car. If modes are omitted, keep the link
            # because some MATSim network writers omit allowed modes for unrestricted links.
            road = (not modes) or bool(modes & {"car", "ride", "truck", "freight", "drt", "taxi"})
            links[str(lid)] = {"length": length, "freespeed": freespeed, "modes": modes, "road": road}
            elem.clear()
    return links


def parse_person_scores_attributes(path, keep_persons=None, include_home=True):
    """
    Stream experienced plans/plans and return one row per person.
    Keeps selected-plan score, likely equity attributes, and a representative home/first-activity coordinate.
    """
    keep = set(map(str, keep_persons)) if keep_persons is not None else None
    rows = []
    with open_binary(path) as fh:
        for _, elem in ET.iterparse(fh, events=("end",)):
            if strip_tag(elem.tag) != "person":
                continue
            pid = str(elem.attrib.get("id", ""))
            if keep is not None and pid not in keep:
                elem.clear(); continue

            attrs = {}
            plans = []
            for child in list(elem):
                tag = strip_tag(child.tag)
                if tag == "attributes":
                    for at in child.iter():
                        if strip_tag(at.tag) == "attribute":
                            name = at.attrib.get("name", "")
                            if name:
                                attrs[name] = (at.text or "").strip()
                elif tag == "plan":
                    plans.append(child)
            selected = None
            for p in plans:
                if str(p.attrib.get("selected", "")).lower() in {"yes", "true", "1"}:
                    selected = p; break
            if selected is None and plans:
                selected = plans[0]

            score = np.nan
            if selected is not None:
                try:
                    score = float(selected.attrib.get("score"))
                except Exception:
                    pass

            rec = {"person_id": pid, "score": score}
            for k, v in attrs.items():
                nk = norm(k)
                if any(token in nk for token in [
                    "income", "age", "sex", "gender", "caravail", "caravailability",
                    "carownership", "householdincome", "employment", "employed"
                ]):
                    rec[k] = v

            if include_home and selected is not None:
                acts = [c for c in list(selected) if strip_tag(c.tag) in {"act", "activity"}]
                home = None
                for act in acts:
                    atype = str(act.attrib.get("type", "")).lower()
                    if "home" in atype:
                        home = act; break
                if home is None and acts:
                    home = acts[0]
                if home is not None:
                    rec["home_activity_type"] = home.attrib.get("type", "")
                    for c in ["x", "y"]:
                        try:
                            rec["home_" + c] = float(home.attrib.get(c))
                        except Exception:
                            rec["home_" + c] = np.nan
                    rec["home_link"] = home.attrib.get("link", home.attrib.get("linkId", ""))
            rows.append(rec)
            elem.clear()
    return pd.DataFrame(rows)


# ----------------------------
# Trip / leg outputs
# ----------------------------

def trip_column_map(path):
    head = read_csv_auto(path, nrows=5)
    cols = list(head.columns)
    return {
        "person": choose_col(cols, ["person", "person_id", "personId"]),
        "trip": choose_col(cols, ["trip_number", "tripNumber", "trip_id", "tripId"]),
        "mode": choose_col(cols, ["main_mode", "mainMode", "longest_distance_mode", "mode"]),
        "trav": choose_col(cols, ["trav_time", "travel_time", "travTime", "travelTime"]),
        "wait": choose_col(cols, ["wait_time", "waiting_time", "waitTime", "waitingTime"]),
        "dep": choose_col(cols, ["dep_time", "departure_time", "depTime", "departureTime"]),
        "dist": choose_col(cols, ["traveled_distance", "travelled_distance", "distance", "traveledDistance"]),
        "start_act": choose_col(cols, ["start_activity_type", "startActivityType", "origin_activity_type"]),
        "end_act": choose_col(cols, ["end_activity_type", "endActivityType", "destination_activity_type"]),
    }


def leg_column_map(path):
    head = read_csv_auto(path, nrows=5)
    cols = list(head.columns)
    return {
        "person": choose_col(cols, ["person", "person_id", "personId"]),
        "trip": choose_col(cols, ["trip_number", "tripNumber", "trip_id", "tripId"]),
        "mode": choose_col(cols, ["mode", "leg_mode", "legMode"]),
    }


def scan_drt_leg_keys(path, drt_mode_regex=r"(?i)(?:^|[^a-z])drt(?:[^a-z]|$)|demand.*responsive"):
    if not path or not Path(path).exists():
        return set(), set()
    cmap = leg_column_map(path)
    if not cmap["person"] or not cmap["mode"]:
        return set(), set()
    sep = sniff_sep(path)
    use = [c for c in [cmap["person"], cmap["trip"], cmap["mode"]] if c]
    keys, persons = set(), set()
    for ch in pd.read_csv(path, sep=sep, usecols=list(dict.fromkeys(use)), chunksize=250_000, dtype=str):
        m = ch[cmap["mode"]].fillna("").astype(str).str.contains(drt_mode_regex, regex=True, na=False)
        x = ch.loc[m]
        for _, r in x.iterrows():
            pid = str(r[cmap["person"]])
            tk = str(r[cmap["trip"]]) if cmap["trip"] else ""
            persons.add(pid)
            if tk:
                keys.add((pid, tk))
    return keys, persons



def scan_drt_users_from_events(path, drt_vehicle_regex=r"(?i)drt|taxi"):
    """Fallback DRT-user detector used only when legs/main-mode do not identify DRT."""
    if not path or not Path(path).exists():
        return set()
    vre = re.compile(drt_vehicle_regex)
    users = set(); known_drt_vehicles = set()
    with open_binary(path) as fh:
        for _, elem in ET.iterparse(fh, events=("end",)):
            if strip_tag(elem.tag) != "event":
                continue
            a = elem.attrib
            typ = event_type(a); compact = typ.replace(" ", "")
            veh = attr_get(a, ["vehicle", "vehicleId", "vehicle_id"])
            person = attr_get(a, ["person", "personId", "person_id", "passenger", "passengerId"])
            mode = str(attr_get(a, ["mode", "requestMode", "legMode"]) or "").lower()
            if veh and (vre.search(str(veh)) or "drt" in mode or "drt" in compact):
                known_drt_vehicles.add(str(veh))
            if person and ("drt" in mode or "drt" in compact):
                users.add(str(person))
            if person and veh and str(veh) in known_drt_vehicles and "personentersvehicle" in compact:
                users.add(str(person))
            elem.clear()
    return users

def scan_trips(path, keep_persons=None, drt_mode_regex=r"(?i)(?:^|[^a-z])drt(?:[^a-z]|$)|demand.*responsive"):
    """
    Stream trips. Returns mode_counts, drt_trip_keys, drt_users, detail_df, column_map.
    detail_df contains only keep_persons if supplied.
    """
    cmap = trip_column_map(path)
    if not cmap["person"] or not cmap["mode"]:
        raise ValueError(f"Cannot identify person/mode columns in {path}")
    sep = sniff_sep(path)
    usecols = list(dict.fromkeys([c for c in cmap.values() if c]))
    keep = set(map(str, keep_persons)) if keep_persons is not None else None
    modes = Counter(); drt_keys = set(); drt_users = set(); detail = []
    for ch in pd.read_csv(path, sep=sep, usecols=usecols, chunksize=250_000, dtype=str):
        pcol, mcol = cmap["person"], cmap["mode"]
        ch[pcol] = ch[pcol].astype(str)
        ch[mcol] = ch[mcol].fillna("").astype(str)
        modes.update(ch[mcol].value_counts().to_dict())
        m = ch[mcol].str.contains(drt_mode_regex, regex=True, na=False)
        for _, r in ch.loc[m].iterrows():
            pid = str(r[pcol]); drt_users.add(pid)
            if cmap["trip"]:
                drt_keys.add((pid, str(r[cmap["trip"]])))
        if keep is not None:
            x = ch[ch[pcol].isin(keep)].copy()
            if not x.empty:
                detail.append(x)
    det = pd.concat(detail, ignore_index=True) if detail else pd.DataFrame(columns=usecols)
    return modes, drt_keys, drt_users, det, cmap


def normalise_trip_detail(df, cmap, prefix):
    if df is None or df.empty:
        return pd.DataFrame()
    out = pd.DataFrame()
    out["person_id"] = df[cmap["person"]].astype(str)
    if cmap["trip"]:
        out["trip_key"] = df[cmap["trip"]].astype(str)
    else:
        out["trip_key"] = out.groupby("person_id").cumcount().astype(str)
    out[prefix + "_mode"] = df[cmap["mode"]].fillna("").astype(str)
    for label, key in [("trav_sec", "trav"), ("wait_sec", "wait"), ("dep_sec", "dep"), ("distance_m", "dist")]:
        c = cmap.get(key)
        if c:
            if key in {"trav", "wait", "dep"}:
                out[prefix + "_" + label] = df[c].map(time_to_seconds)
            else:
                out[prefix + "_" + label] = pd.to_numeric(df[c], errors="coerce")
    for label, key in [("start_activity", "start_act"), ("end_activity", "end_act")]:
        c = cmap.get(key)
        if c:
            out[prefix + "_" + label] = df[c].astype(str)
    return out


def system_mode_table(counts, source):
    total = sum(counts.values())
    return pd.DataFrame([
        {"source": source, "mode": mode, "trips": int(n), "share": n / total if total else np.nan}
        for mode, n in sorted(counts.items())
    ])


# ----------------------------
# Convergence and DRT KPI files
# ----------------------------

def window_numeric_summary(df, start_it=181, end_it=200):
    if df is None or df.empty:
        return {}
    itcol = choose_col(df.columns, ["iteration", "iter"])
    w = df.copy()
    if itcol:
        it = pd.to_numeric(w[itcol], errors="coerce")
        w = w[(it >= start_it) & (it <= end_it)]
    nums = w.apply(pd.to_numeric, errors="coerce")
    out = {}
    for c in nums.columns:
        x = nums[c].dropna()
        if len(x):
            out[c + "__mean"] = float(x.mean())
            out[c + "__median"] = float(x.median())
            out[c + "__min"] = float(x.min())
            out[c + "__max"] = float(x.max())
            out[c + "__last"] = float(x.iloc[-1])
    return out


def convergence_summary(outdir, start_it=181, end_it=200):
    rows = []
    for kind, pats in [
        ("scorestats", ["*scorestats.csv", "*scorestats*.csv"]),
        ("modestats", ["*modestats.csv", "*modestats*.csv"]),
    ]:
        f = find_file(outdir, pats)
        if not f:
            continue
        df = read_csv_auto(f)
        itcol = choose_col(df.columns, ["iteration", "iter"])
        if not itcol:
            continue
        it = pd.to_numeric(df[itcol], errors="coerce")
        a = df[(it >= max(start_it, end_it - 19)) & (it <= end_it - 10)]
        b = df[(it >= end_it - 9) & (it <= end_it)]
        for c in df.columns:
            if c == itcol:
                continue
            aa = pd.to_numeric(a[c], errors="coerce").dropna()
            bb = pd.to_numeric(b[c], errors="coerce").dropna()
            if len(aa) and len(bb):
                ma, mb = float(aa.mean()), float(bb.mean())
                denom = abs(ma) if abs(ma) > 1e-12 else 1.0
                rows.append({
                    "source": kind,
                    "metric": c,
                    "window1_mean": ma,
                    "window2_mean": mb,
                    "absolute_change": mb - ma,
                    "relative_change": (mb - ma) / denom,
                })
    return pd.DataFrame(rows)


def _candidate_numeric(df, candidates):
    c = choose_col(df.columns, candidates)
    if c is None:
        return None, pd.Series(dtype=float)
    return c, pd.to_numeric(df[c], errors="coerce")


def _distance_to_km(series, colname):
    n = norm(colname)
    if "km" in n:
        return series
    # MATSim core distances are conventionally metres; only normalise when header
    # is distance-like and lacks an explicit km marker.
    if "distance" in n or "dist" in n:
        return series / 1000.0
    return series


def _time_to_hours(series, colname):
    n = norm(colname)
    if "hour" in n or n.endswith("h"):
        return series
    if "time" in n or "duration" in n:
        return series / 3600.0
    return series


def extract_drt_kpis(outdir, start_it, end_it, fleet=np.nan):
    """
    Read MATSim DRT CSV summaries. Returns (canonical_dict, raw_dict).
    The raw dictionary preserves all numeric final-window summaries; canonical fields
    are best-effort mappings used by thesis tables.
    """
    files = {
        "customer": ["*drt_customer_stats_drt.csv", "*customer_stats*drt*.csv"],
        "vehicle": ["*drt_vehicle_stats_drt.csv", "*vehicle_stats*drt*.csv"],
        "sharing": ["*drt_sharing_metrics_drt.csv", "*sharing_metrics*drt*.csv"],
    }
    raw = {}
    dfs = {}
    for label, pats in files.items():
        f = find_file(outdir, pats)
        if not f:
            continue
        df = read_csv_auto(f)
        itcol = choose_col(df.columns, ["iteration", "iter"])
        if itcol:
            it = pd.to_numeric(df[itcol], errors="coerce")
            dfw = df[(it >= start_it) & (it <= end_it)].copy()
        else:
            dfw = df.copy()
        dfs[label] = dfw
        for k, v in window_numeric_summary(df, start_it, end_it).items():
            raw[f"{label}::{k}"] = v

    can = {}
    cust = dfs.get("customer", pd.DataFrame())
    veh = dfs.get("vehicle", pd.DataFrame())
    shr = dfs.get("sharing", pd.DataFrame())

    if not cust.empty:
        mappings = {
            "served_requests": ["rides", "servedRequests", "served_requests", "performedRequests", "requestsServed"],
            "rejected_requests": ["rejections", "rejectedRequests", "rejected_requests", "requestsRejected"],
            "rejection_rate": ["rejectionRate", "rejectedRequestRate", "rejectedRequestsRate"],
            "wait_mean_sec": ["waitTime", "averageWaitTime", "meanWaitTime", "wait_time_mean", "waitAverage"],
            "wait_p95_sec": ["wait_p95", "waitP95", "waitTimeP95", "p95WaitTime", "wait95", "95thPercentileWaitTime", "wait_time_p95"],
            "ride_mean_sec": ["rideTime", "averageRideTime", "meanRideTime", "ride_time_mean"],
            "detour_mean": ["detour", "averageDetour", "meanDetour", "detourFactor"],
        }
        for outname, cands in mappings.items():
            c, s = _candidate_numeric(cust, cands)
            if c and s.notna().any():
                can[outname] = float(s.mean())
        if "rejection_rate" not in can and "served_requests" in can and "rejected_requests" in can:
            den = can["served_requests"] + can["rejected_requests"]
            can["rejection_rate"] = safe_div(can["rejected_requests"], den)

    if not veh.empty:
        distmaps = {
            "drt_total_vkt_km": ["totalDistance", "distance", "total_distance", "vehicleDistance"],
            "drt_empty_vkt_km": ["emptyDistance", "empty_distance", "emptyVehicleDistance"],
            "drt_occupied_vkt_km": ["occupiedDistance", "passengerDistance", "occupied_distance"],
        }
        for outname, cands in distmaps.items():
            c, s = _candidate_numeric(veh, cands)
            if c and s.notna().any():
                can[outname] = float(_distance_to_km(s, c).mean())
        timemaps = {
            "drt_vehicle_hours": ["totalDriveTime", "totalTime", "driveTime", "vehicleTime", "total_duration"],
            "drt_empty_hours": ["emptyDriveTime", "emptyTime", "idleDriveTime"],
            "drt_idle_hours": ["idleTime", "totalIdleTime"],
        }
        for outname, cands in timemaps.items():
            c, s = _candidate_numeric(veh, cands)
            if c and s.notna().any():
                can[outname] = float(_time_to_hours(s, c).mean())
        # Idle counts need exact-name matching. Partial matching can otherwise select the
        # generic `vehicles` column and silently report fleet size as the idle count.
        by_norm = {norm(col): col for col in veh.columns}
        c = next((by_norm[norm(name)] for name in ["minCountIdleVehicles", "minIdleVehicles", "minimumIdleVehicles", "min_idle_count"] if norm(name) in by_norm), None)
        if c:
            s = pd.to_numeric(veh[c], errors="coerce")
            if s.notna().any():
                can["min_idle_vehicles"] = float(s.mean())
        c = next((by_norm[norm(name)] for name in ["meanCountIdleVehicles", "meanIdleVehicles", "averageIdleVehicles", "avgIdleVehicles"] if norm(name) in by_norm), None)
        if c:
            s = pd.to_numeric(veh[c], errors="coerce")
            if s.notna().any():
                can["mean_idle_vehicles"] = float(s.mean())

    if not shr.empty:
        for outname, cands in {
            "pooling_rate": ["poolingRate", "sharingRate", "sharedRideRate"],
            "sharing_factor": ["sharingFactor", "occupancy", "averageOccupancy", "meanOccupancy"],
        }.items():
            c, s = _candidate_numeric(shr, cands)
            if c and s.notna().any():
                can[outname] = float(s.mean())

    if "drt_total_vkt_km" in can and "drt_empty_vkt_km" in can:
        can["empty_vkt_share"] = safe_div(can["drt_empty_vkt_km"], can["drt_total_vkt_km"])
    if "served_requests" in can and can.get("served_requests", 0):
        if "drt_total_vkt_km" in can:
            can["drt_vkt_per_served_request_km"] = safe_div(can["drt_total_vkt_km"], can["served_requests"])
        if fleet and not pd.isna(fleet):
            can["served_requests_per_vehicle"] = safe_div(can["served_requests"], fleet)
    return can, raw


# ----------------------------
# Equity helpers
# ----------------------------

def detect_equity_columns(df):
    out = {}
    for c in df.columns:
        n = norm(c)
        if "income" in n and "income" not in out:
            out["income"] = c
        elif ("gender" in n or "sex" in n) and "gender" not in out:
            out["gender"] = c
        elif "age" in n and "age" not in out:
            out["age"] = c
        elif ("caravail" in n or "carownership" in n) and "car_availability" not in out:
            out["car_availability"] = c
        elif ("employment" in n or "employed" in n) and "employment" not in out:
            out["employment"] = c
    return out


def add_equity_groups(df, reference_df=None):
    """Add robust derived groups without overwriting original attributes."""
    x = df.copy()
    ref = reference_df if reference_df is not None else df
    eq = detect_equity_columns(x)
    if "income" in eq:
        c = eq["income"]
        num = pd.to_numeric(x[c], errors="coerce")
        rnum = pd.to_numeric(ref[c], errors="coerce") if c in ref.columns else num
        if rnum.notna().sum() >= 30 and rnum.nunique() >= 3:
            q1, q2 = rnum.quantile([1/3, 2/3]).tolist()
            x["income_group"] = pd.cut(num, [-np.inf, q1, q2, np.inf], labels=["low", "middle", "high"], include_lowest=True)
            x.attrs["income_cutpoints"] = [float(q1), float(q2)]
        else:
            x["income_group"] = x[c].astype(str)
    if "age" in eq:
        c = eq["age"]
        num = pd.to_numeric(x[c], errors="coerce")
        if num.notna().sum() >= 10:
            x["age_group"] = pd.cut(num, [-np.inf, 24, 44, 64, np.inf], labels=["<25", "25-44", "45-64", "65+"], include_lowest=True)
        else:
            x["age_group"] = x[c].astype(str)
    if "gender" in eq:
        x["gender_group"] = x[eq["gender"]].astype(str)
    if "car_availability" in eq:
        x["car_availability_group"] = x[eq["car_availability"]].astype(str)
    if "employment" in eq:
        x["employment_group"] = x[eq["employment"]].astype(str)
    return x


def equity_summary(person_df, primary_mask=None):
    x = person_df.copy()
    if primary_mask is not None:
        x = x[primary_mask].copy()
    if x.empty or "delta_score" not in x.columns:
        return pd.DataFrame()
    group_cols = [c for c in ["income_group", "age_group", "gender_group", "car_availability_group", "employment_group"] if c in x.columns]
    rows = []
    for gc in group_cols:
        dim = gc.replace("_group", "")
        for g, gg in x.groupby(gc, dropna=False, observed=False):
            d = pd.to_numeric(gg["delta_score"], errors="coerce").dropna()
            if len(d) == 0:
                continue
            row = {
                "dimension": dim,
                "group": str(g),
                "n": int(len(d)),
                "mean_delta_score": float(d.mean()),
                "median_delta_score": float(d.median()),
                "p10_delta_score": float(d.quantile(.10)),
                "p90_delta_score": float(d.quantile(.90)),
                "share_better": float((d > 1e-9).mean()),
                "share_worse": float((d < -1e-9).mean()),
            }
            if "scenario_drt_user" in gg.columns:
                row["share_using_drt"] = float(gg["scenario_drt_user"].fillna(False).astype(bool).mean())
            rows.append(row)
    return pd.DataFrame(rows)


# ----------------------------
# Event-based network metrics / emissions
# ----------------------------

def empty_network_accumulator():
    return {
        "road_vkt_km": 0.0,
        "road_travel_time_h": 0.0,
        "road_delay_h": 0.0,
        "link_traversals": 0,
        "vehicles": set(),
        "by_hour": defaultdict(lambda: {"road_vkt_km": 0.0, "road_travel_time_h": 0.0, "road_delay_h": 0.0, "link_traversals": 0}),
        "emissions": defaultdict(float),
        "emission_events": 0,
    }


def update_network_event(acc, elem_attrs, links, pending):
    a = elem_attrs
    typ = event_type(a)
    compact = typ.replace(" ", "")
    veh = attr_get(a, ["vehicle", "vehicleId", "vehicle_id"])
    link = attr_get(a, ["link", "linkId", "link_id"])
    t = time_to_seconds(attr_get(a, ["time"]))

    if ("linkenter" in compact or "enteredlink" in compact) and veh and link and str(link) in links and links[str(link)]["road"]:
        info = links[str(link)]
        length = info["length"]
        acc["road_vkt_km"] += length / 1000.0
        acc["link_traversals"] += 1
        acc["vehicles"].add(str(veh))
        hr = int(t // 3600) if not pd.isna(t) else -1
        acc["by_hour"][hr]["road_vkt_km"] += length / 1000.0
        acc["by_hour"][hr]["link_traversals"] += 1
        pending[str(veh)] = (str(link), float(t) if not pd.isna(t) else np.nan, hr)
    elif ("linkleave" in compact or "leftlink" in compact) and veh and str(veh) in pending:
        plink, enter_t, hr = pending.pop(str(veh))
        if plink in links and not pd.isna(enter_t) and not pd.isna(t):
            tt = max(0.0, float(t) - enter_t)
            info = links[plink]
            ff = info["length"] / info["freespeed"] if info["freespeed"] > 0 else np.nan
            delay = max(0.0, tt - ff) if not pd.isna(ff) else 0.0
            acc["road_travel_time_h"] += tt / 3600.0
            acc["road_delay_h"] += delay / 3600.0
            acc["by_hour"][hr]["road_travel_time_h"] += tt / 3600.0
            acc["by_hour"][hr]["road_delay_h"] += delay / 3600.0
    elif "emission" in compact:
        acc["emission_events"] += 1
        ignore = {"time", "type", "vehicle", "vehicleid", "vehicle_id", "link", "linkid", "link_id"}
        for k, v in a.items():
            if k.lower() in ignore:
                continue
            try:
                acc["emissions"][k] += float(v)
            except Exception:
                pass


def network_accumulator_to_frames(acc):
    total = pd.DataFrame([{
        "road_vkt_km": acc["road_vkt_km"],
        "road_travel_time_h": acc["road_travel_time_h"],
        "road_delay_h": acc["road_delay_h"],
        "link_traversals": acc["link_traversals"],
        "unique_road_vehicles": len(acc["vehicles"]),
        "emission_events": acc["emission_events"],
        **{f"emission::{k}": v for k, v in sorted(acc["emissions"].items())},
    }])
    hours = []
    for h, d in sorted(acc["by_hour"].items()):
        hours.append({"hour": h, **d})
    return total, pd.DataFrame(hours)
