from pathlib import Path
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def read_df(path):
    try:
        return pd.read_csv(path) if Path(path).exists() else pd.DataFrame()
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def numeric(df, c):
    return pd.to_numeric(df[c], errors="coerce") if c in df.columns else pd.Series(np.nan, index=df.index)


def main():
    ap = argparse.ArgumentParser(description="Create thesis-ready diagnostic figures from RQ tables.")
    ap.add_argument("--rq-dir", default="analysis_results/04_RQ_outputs")
    ap.add_argument("--out", default="analysis_results/05_figures")
    args = ap.parse_args()
    src = Path(args.rq_dir); out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    rq1 = read_df(src / "RQ1_context_suitability_A_B_C.csv")
    if not rq1.empty:
        labels = rq1["scenario"].astype(str)
        if "target_riders::mean_delta_score" in rq1:
            fig, ax = plt.subplots(figsize=(7, 4.5))
            ax.bar(labels, numeric(rq1, "target_riders::mean_delta_score"))
            ax.axhline(0, linewidth=1)
            ax.set_ylabel("Mean same-agent Δ score (target-line riders)")
            ax.set_title("RQ1: passenger welfare relative to B0")
            save(fig, out / "RQ1_mean_delta_score_structural_cases.png")
        if "resource::DRT_VKT_to_removed_bus_VKT_ratio" in rq1:
            fig, ax = plt.subplots(figsize=(7, 4.5))
            ax.bar(labels, numeric(rq1, "resource::DRT_VKT_to_removed_bus_VKT_ratio"))
            ax.axhline(1, linewidth=1)
            ax.set_ylabel("DRT VKT / removed target-bus VKT")
            ax.set_title("RQ1: road-resource requirement relative to removed bus")
            save(fig, out / "RQ1_DRT_to_bus_VKT_ratio.png")
        if "network::relative_delta_road_delay_h" in rq1:
            fig, ax = plt.subplots(figsize=(7, 4.5))
            ax.bar(labels, 100 * numeric(rq1, "network::relative_delta_road_delay_h"))
            ax.axhline(0, linewidth=1)
            ax.set_ylabel("Change in network road delay vs B0 (%)")
            ax.set_title("RQ1: secondary congestion effect")
            save(fig, out / "RQ1_network_delay_change.png")

    rq2 = read_df(src / "RQ2_caseA_intervention_design.csv")
    if not rq2.empty:
        sens = rq2[rq2["pricing_group"].isin(["FL", "FH"])].copy()
        for metric, ylabel, fname in [
            ("target_riders::mean_delta_score", "Mean same-agent Δ score", "RQ2_fleet_vs_utility.png"),
            ("drt::wait_p95_sec", "DRT P95 waiting time (s)", "RQ2_fleet_vs_P95_wait.png"),
            ("drt::drt_vkt_per_served_request_km", "DRT VKT per served request (km)", "RQ2_fleet_vs_VKT_per_request.png"),
            ("drt::empty_vkt_share", "Empty VKT share", "RQ2_fleet_vs_empty_VKT_share.png"),
        ]:
            if metric not in sens.columns or sens.empty:
                continue
            fig, ax = plt.subplots(figsize=(7, 4.5))
            for fare, g in sens.groupby("pricing_group"):
                g = g.sort_values("fleet")
                ax.plot(numeric(g, "fleet"), numeric(g, metric), marker="o", label=fare)
            ax.set_xlabel("Fleet size")
            ax.set_ylabel(ylabel)
            ax.set_title("RQ2: fleet sensitivity by fare policy")
            ax.legend()
            save(fig, out / fname)

        p8 = read_df(src / "RQ2_pricing_chain_8veh_FM_SUB1_FL_FH.csv")
        if not p8.empty and "target_riders::mean_delta_score" in p8.columns:
            fig, ax = plt.subplots(figsize=(7, 4.5))
            ax.bar(p8["pricing_group"].astype(str), numeric(p8, "target_riders::mean_delta_score"))
            ax.axhline(0, linewidth=1)
            ax.set_xlabel("8-vehicle monetary treatment")
            ax.set_ylabel("Mean same-agent Δ score")
            ax.set_title("RQ2: pricing/integration policy at fixed supply")
            save(fig, out / "RQ2_8veh_pricing_chain_utility.png")

    trans = read_df(src / "RQ3_original_bus_trip_mode_transitions.csv")
    if not trans.empty and {"scenario", "scenario_effective_mode", "trips"}.issubset(trans.columns):
        for scen, g in trans.groupby("scenario"):
            p = g.groupby("scenario_effective_mode")["trips"].sum().sort_values(ascending=False)
            fig, ax = plt.subplots(figsize=(7, 4.5))
            ax.bar(p.index.astype(str), p.values / p.values.sum())
            ax.set_ylabel("Share of original target-bus trips")
            ax.set_title(f"RQ3: destination modes after intervention — {scen}")
            ax.tick_params(axis="x", rotation=35)
            save(fig, out / f"RQ3_target_bus_transition_{scen}.png")

    eq = read_df(src / "RQ3_equity_utility.csv")
    if not eq.empty and {"scenario", "dimension", "group", "mean_delta_score"}.issubset(eq.columns):
        for (scen, dim), g in eq.groupby(["scenario", "dimension"]):
            if len(g) < 2:
                continue
            fig, ax = plt.subplots(figsize=(7, 4.5))
            ax.bar(g["group"].astype(str), numeric(g, "mean_delta_score"))
            ax.axhline(0, linewidth=1)
            ax.set_ylabel("Mean same-agent Δ score")
            ax.set_title(f"RQ3: {dim} distribution — {scen}")
            ax.tick_params(axis="x", rotation=30)
            save(fig, out / f"RQ3_equity_{scen}_{dim}.png")

    print("Figures written to", out)


if __name__ == "__main__":
    main()
