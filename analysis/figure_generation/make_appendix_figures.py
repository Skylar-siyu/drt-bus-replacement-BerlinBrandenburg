#!/usr/bin/env python3
"""Rebuild the non-map appendix figures from the dissertation analysis outputs.

The input may be either an extracted ``analysis_results`` directory or the
``ABC_analysis_results_01_04.tar.gz`` archive.  No values are digitised from
the submitted figures: every mark is recomputed from the analysis tables.

Examples
--------
python make_appendix_figures.py \
  --analysis-source /path/to/analysis_results \
  --output-dir figures

python make_appendix_figures.py \
  --analysis-source ABC_analysis_results_01_04.tar.gz \
  --figures B1 B4 B9 \
  --output-dir figures
"""

from __future__ import annotations

import argparse
import gzip
import io
import math
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats


# Colour-blind-conscious, print-safe palette used throughout the thesis.
CASE_COLOURS = {"A": "#2AA6AE", "B": "#8A7BD1", "C": "#FF8A62"}
NAVY = "#123E5A"
TEXT = "#34383D"
GRID = "#D7DCE1"
GREY = "#45484E"
LIGHT_GREY = "#F2F4F6"

SCENARIO_CASE = {"A8_FM": "A", "B6_PTI": "B", "C22_PTI": "C"}
CASE_ROUTE = {"A": "Line 890", "B": "Line 435", "C": "Line X36"}

OUTPUT_NAMES = {
    "B1": "Figure_B1_hourly_road_network_changes.png",
    "B2": "Figure_B2_representative_daily_sequences_journal.png",
    "B3": "Figure_B3_demographic_variation_violin.png",
    "B4": "Figure_B4_three_hour_variation.png",
    "B6": "Figure_B6_distance_to_rail_hubs_revised.png",
    "B7": "Figure_B7_income_and_same_agent_utility_revised.png",
    "B8": "Figure_B8_mode_and_waiting_distributions_revised.png",
    "B9": "Figure_B9_three_hour_variation_case_C_revised.png",
}


class AnalysisSource:
    """Read CSV members from either an extracted tree or a tar archive."""

    def __init__(self, source: str | Path):
        self.source = Path(source).expanduser().resolve()
        self._tar: tarfile.TarFile | None = None
        self._members: dict[str, tarfile.TarInfo] = {}

        if self.source.is_dir():
            nested = self.source / "analysis_results"
            self.root = nested if nested.is_dir() else self.source
            if not (self.root / "01_baseline").is_dir():
                raise ValueError(
                    f"{self.source} is not an analysis_results directory "
                    "(01_baseline was not found)."
                )
        elif self.source.is_file() and tarfile.is_tarfile(self.source):
            self.root = None
            self._tar = tarfile.open(self.source, mode="r:*")
            for member in self._tar.getmembers():
                if not member.isfile():
                    continue
                name = member.name.lstrip("./")
                self._members[name] = member
                marker = "analysis_results/"
                if marker in name:
                    self._members[name.split(marker, 1)[1]] = member
        else:
            raise ValueError(
                f"Analysis source does not exist or is not a supported tar archive: {self.source}"
            )

    def close(self) -> None:
        if self._tar is not None:
            self._tar.close()

    def __enter__(self) -> "AnalysisSource":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _normalise(relative: str | Path) -> str:
        return str(relative).replace("\\", "/").lstrip("./")

    def exists(self, relative: str | Path) -> bool:
        rel = self._normalise(relative)
        if self.root is not None:
            return (self.root / rel).is_file()
        return rel in self._members

    def read_csv(self, relative: str | Path, **kwargs: object) -> pd.DataFrame:
        rel = self._normalise(relative)
        kwargs.setdefault("low_memory", False)
        if self.root is not None:
            path = self.root / rel
            if not path.is_file():
                raise FileNotFoundError(f"Required analysis table not found: {path}")
            return pd.read_csv(path, **kwargs)

        if self._tar is None or rel not in self._members:
            raise FileNotFoundError(
                f"Required analysis table not found in {self.source.name}: {rel}"
            )
        extracted = self._tar.extractfile(self._members[rel])
        if extracted is None:
            raise FileNotFoundError(f"Could not read archive member: {rel}")
        raw = extracted.read()
        if rel.lower().endswith(".gz"):
            raw = gzip.decompress(raw)
        return pd.read_csv(io.BytesIO(raw), **kwargs)

    def scenario_csv(self, scenario: str, filename: str, **kwargs: object) -> pd.DataFrame:
        return self.read_csv(f"02_scenarios/{scenario}/{filename}", **kwargs)


def _truthy(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    if pd.api.types.is_numeric_dtype(series):
        return series.fillna(0).astype(float).ne(0)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def _set_style() -> None:
    sns.set_theme(style="whitegrid")
    mpl.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10.5,
            "axes.titlesize": 12.5,
            "axes.titleweight": "bold",
            "axes.labelsize": 11,
            "axes.edgecolor": "#8B939A",
            "axes.linewidth": 0.75,
            "axes.labelcolor": TEXT,
            "xtick.color": TEXT,
            "ytick.color": TEXT,
            "text.color": TEXT,
            "grid.color": GRID,
            "grid.linewidth": 0.7,
            "legend.frameon": False,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def _panel_title(ax: plt.Axes, letter: str, title: str) -> None:
    ax.set_title(f"{letter}  {title}", loc="left", pad=10, color=TEXT)


def _case_heading(fig: plt.Figure, x: float, y: float, case: str) -> None:
    fig.text(
        x,
        y,
        f"Case {case}  {CASE_ROUTE[case]}",
        ha="left",
        va="top",
        fontsize=14,
        fontweight="bold",
        color=NAVY,
    )


def _save(fig: plt.Figure, output_dir: Path, key: str, dpi: int) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / OUTPUT_NAMES[key]
    fig.savefig(path, dpi=dpi, bbox_inches="tight", pad_inches=0.10)
    plt.close(fig)
    print(f"[{key}] wrote {path}")
    return path


def _gini(values: Iterable[float]) -> float:
    x = np.asarray(list(values), dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return float("nan")
    x = np.maximum(x, 0)
    if np.allclose(x.sum(), 0):
        return 0.0
    x = np.sort(x)
    n = len(x)
    return float((2 * np.dot(np.arange(1, n + 1), x) / (n * x.sum())) - (n + 1) / n)


def _ecdf(values: Iterable[float]) -> tuple[np.ndarray, np.ndarray]:
    x = np.sort(np.asarray(list(values), dtype=float))
    x = x[np.isfinite(x)]
    if not len(x):
        return x, x
    return x, np.arange(1, len(x) + 1) / len(x)


def _finite_pair(x: pd.Series, y: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    xx = pd.to_numeric(x, errors="coerce").to_numpy(float)
    yy = pd.to_numeric(y, errors="coerce").to_numpy(float)
    ok = np.isfinite(xx) & np.isfinite(yy)
    return xx[ok], yy[ok]


def _linear_overlay(ax: plt.Axes, x: np.ndarray, y: np.ndarray, colour: str) -> None:
    """OLS line and analytical 95% confidence interval for the mean."""
    if len(x) < 3 or np.allclose(x, x[0]):
        return
    slope, intercept, _, _, _ = stats.linregress(x, y)
    grid = np.linspace(float(np.nanmin(x)), float(np.nanmax(x)), 160)
    fitted = intercept + slope * grid
    resid = y - (intercept + slope * x)
    dof = max(len(x) - 2, 1)
    s_err = math.sqrt(float(np.dot(resid, resid)) / dof)
    x_mean = float(np.mean(x))
    sxx = float(np.sum((x - x_mean) ** 2))
    tcrit = stats.t.ppf(0.975, dof)
    ci = tcrit * s_err * np.sqrt(1 / len(x) + (grid - x_mean) ** 2 / sxx)
    ax.fill_between(grid, fitted - ci, fitted + ci, color=colour, alpha=0.15, linewidth=0)
    ax.plot(grid, fitted, color=colour, linewidth=2.0)


# ---------------------------------------------------------------------------
# Figure B.1
# ---------------------------------------------------------------------------


def figure_b1(ds: AnalysisSource, output_dir: Path, dpi: int) -> Path:
    """Hourly road-network changes relative to daily B0 totals."""
    baseline = ds.read_csv("01_baseline/B0_network_by_hour.csv")
    metrics = [
        ("road_vkt_km", "Road vehicle-kilometres"),
        ("road_travel_time_h", "Road travel time"),
        ("road_delay_h", "Network delay"),
    ]
    baseline = baseline.groupby("hour", as_index=False)[[m[0] for m in metrics]].sum()

    fig, axes = plt.subplots(3, 1, figsize=(11.4, 9.1), sharex=True, constrained_layout=True)
    letters = "abc"
    for ax, (metric, label), letter in zip(axes, metrics, letters):
        daily_total = float(baseline[metric].sum())
        for scenario, case in SCENARIO_CASE.items():
            intervention = ds.read_csv(f"03_network/{scenario}/network_by_hour.csv")
            intervention = intervention.groupby("hour", as_index=False)[metric].sum()
            paired = baseline[["hour", metric]].merge(
                intervention, on="hour", how="outer", suffixes=("_b0", "_scenario")
            ).fillna(0)
            paired["change"] = (
                100.0 * (paired[f"{metric}_scenario"] - paired[f"{metric}_b0"]) / daily_total
            )
            ax.plot(
                paired["hour"],
                paired["change"],
                marker="o",
                markersize=3.6,
                linewidth=1.7,
                color=CASE_COLOURS[case],
                label=f"Case {case}",
            )
        ax.axhline(0, color="#737980", linestyle=(0, (4, 4)), linewidth=1)
        ax.axvline(24, color="#737980", linestyle=(0, (1, 3)), linewidth=1)
        _panel_title(ax, letter, label)
        ax.set_ylabel("Change (% of daily B0 total)")
        ax.grid(axis="x", alpha=0.45)
        ax.spines[["top", "right"]].set_visible(False)
    axes[-1].set_xlabel("Hour of day")
    max_hour = int(max(baseline["hour"].max(), 24))
    axes[-1].set_xticks(np.arange(0, max_hour + 1, 4))
    axes[-1].set_xlim(0, max_hour)
    axes[0].legend(ncol=3, loc="upper right")
    fig.suptitle(
        "Hourly road-network changes relative to daily B0 totals",
        x=0.06,
        ha="left",
        fontsize=15,
        fontweight="bold",
        color=NAVY,
    )
    return _save(fig, output_dir, "B1", dpi)


# ---------------------------------------------------------------------------
# Figure B.2
# ---------------------------------------------------------------------------


# Synthetic MATSim agent identifiers frozen by the submitted Figure B.2.
# They are not names or identifiers of real survey participants.
FROZEN_REPRESENTATIVES = {
    "DRT retention": "bb_3ce3f7ef",
    "Shift to other public transport": "bb_0297fb8a",
    "Shift to car": "berlin_0a204e53",
    "Shift to ride or another mode": "berlin_4b698842",
}


def _representative_candidates(trips: pd.DataFrame, people: pd.DataFrame) -> dict[str, str]:
    """Choose deterministic fallbacks nearest each category's bivariate median."""
    target = trips[_truthy(trips["baseline_target_line_trip"])].copy()
    definitions = {
        "DRT retention": target["transition_class"].eq("target_bus_to_DRT"),
        "Shift to other public transport": target["transition_class"].eq("target_bus_to_other_PT"),
        "Shift to car": target["transition_class"].eq("target_bus_to_car"),
        "Shift to ride or another mode": ~target["transition_class"].isin(
            ["target_bus_to_DRT", "target_bus_to_other_PT", "target_bus_to_car"]
        ),
    }
    utility = people.set_index("person_id")["delta_score"]
    chosen: dict[str, str] = {}
    for label, mask in definitions.items():
        subset = target.loc[mask]
        summary = (
            subset.groupby("person_id", as_index=False)["delta_journey_sec"]
            .mean()
            .rename(columns={"delta_journey_sec": "mean_delta"})
        )
        summary["utility"] = summary["person_id"].map(utility)
        summary = summary.dropna(subset=["utility", "mean_delta"]).sort_values("person_id")
        if summary.empty:
            raise ValueError(f"No candidates found for Figure B.2 category: {label}")
        for col in ["utility", "mean_delta"]:
            med = summary[col].median()
            scale = summary[col].mad() if hasattr(summary[col], "mad") else None
            # pandas 2 removed Series.mad; median absolute deviation is stable.
            scale = float(np.median(np.abs(summary[col] - med)))
            if not np.isfinite(scale) or scale <= 0:
                scale = float(summary[col].std()) or 1.0
            summary[f"z_{col}"] = (summary[col] - med) / scale
        summary["distance"] = np.hypot(summary["z_utility"], summary["z_mean_delta"])
        chosen[label] = str(summary.sort_values(["distance", "person_id"]).iloc[0]["person_id"])
    return chosen


def _mode_category(mode: object, target: bool = False, drt: bool = False) -> str:
    value = str(mode).strip().lower()
    if drt or value == "drt" or "drt" in value:
        return "DRT-containing"
    if target:
        return "Target route"
    if value in {"pt", "transit_walk", "access_walk"} or "pt" in value:
        return "Other PT"
    if value == "car" or value.startswith("car_"):
        return "Car"
    if value in {"walk", "bike"}:
        return "Active mode"
    return "Ride or other"


def figure_b2(ds: AnalysisSource, output_dir: Path, dpi: int) -> Path:
    scenario = "A8_FM"
    trips = ds.scenario_csv(scenario, "trip_level_impacts.csv.gz")
    people = ds.scenario_csv(scenario, "person_level_impacts.csv.gz")
    available = set(people["person_id"].astype(str)) & set(trips["person_id"].astype(str))
    fallback = _representative_candidates(trips, people)
    selected = {
        label: (person if person in available else fallback[label])
        for label, person in FROZEN_REPRESENTATIVES.items()
    }
    for label, person in selected.items():
        source = "frozen" if person == FROZEN_REPRESENTATIVES[label] else "fallback"
        print(f"[B2] {label}: using {source} representative")

    colours = {
        "Target route": "#6D2E80",
        "DRT-containing": "#24A5A6",
        "Other PT": "#0E4368",
        "Car": "#FF875B",
        "Ride or other": "#8173CF",
        "Active mode": "#393D42",
    }

    fig, axes = plt.subplots(2, 2, figsize=(15.5, 9.55), constrained_layout=False)
    fig.subplots_adjust(left=0.055, right=0.992, bottom=0.125, top=0.875, wspace=0.14, hspace=0.39)
    _case_heading(fig, 0.055, 0.975, "A")
    panel_letters = "abcd"
    people_idx = people.set_index("person_id")

    for ax, letter, (label, person_id) in zip(axes.flat, panel_letters, selected.items()):
        rows = trips[trips["person_id"].astype(str).eq(person_id)].sort_values("trip_key")
        if rows.empty:
            raise ValueError(f"Representative person {person_id} has no A8_FM trip records")
        target = rows[_truthy(rows["baseline_target_line_trip"])]
        delta_u = float(people_idx.loc[person_id, "delta_score"])
        mean_jt = float(pd.to_numeric(target["delta_journey_sec"], errors="coerce").mean() / 60)
        ax.set_facecolor("white")
        ax.axhspan(0.72, 1.28, color=LIGHT_GREY, zorder=0)
        ax.axhspan(-0.28, 0.28, color=LIGHT_GREY, zorder=0)
        for _, row in rows.iterrows():
            for lane, prefix in [(1.0, "b0"), (0.0, "scenario")]:
                start = pd.to_numeric(row.get(f"{prefix}_dep_sec"), errors="coerce")
                duration = pd.to_numeric(row.get(f"{prefix}_trav_sec"), errors="coerce")
                if not (np.isfinite(start) and np.isfinite(duration) and duration > 0):
                    continue
                if prefix == "b0":
                    category = _mode_category(
                        row.get("b0_mode"), target=bool(_truthy(pd.Series([row.get("baseline_target_line_trip")])).iloc[0])
                    )
                else:
                    category = _mode_category(
                        row.get("scenario_mode"),
                        drt=bool(_truthy(pd.Series([row.get("scenario_drt_trip")])).iloc[0]),
                    )
                left = max(0.0, float(start) / 3600)
                right = min(24.0, float(start + duration) / 3600)
                if right <= left:
                    continue
                ax.add_patch(
                    Rectangle(
                        (left, lane - 0.15),
                        right - left,
                        0.30,
                        facecolor=colours[category],
                        edgecolor="white",
                        linewidth=0.35,
                        zorder=3,
                    )
                )
        # Keep the panel heading and the numeric audit line on separate rows.
        ax.set_title(f"{letter}  {label}", loc="left", pad=35, color=TEXT)
        ax.text(
            0.0,
            1.015,
            f"ΔU = {delta_u:.2f}   Mean target ΔJT = {mean_jt:.1f} min",
            transform=ax.transAxes,
            fontsize=9.5,
            color="#5B6066",
            va="bottom",
        )
        ax.set_xlim(0, 24)
        ax.set_ylim(-0.5, 1.5)
        ax.set_yticks([1, 0], labels=["B0", "A8-FM"])
        ax.set_xticks(np.arange(0, 25, 4), labels=[f"{h:02d}:00" for h in range(0, 25, 4)])
        ax.set_xlabel("Time of day")
        ax.grid(axis="x")
        ax.grid(axis="y", visible=False)
        ax.tick_params(axis="y", length=0)
        ax.spines[["top", "right"]].set_visible(False)

    legend_order = ["Target route", "DRT-containing", "Other PT", "Car", "Ride or other", "Active mode"]
    fig.legend(
        [Patch(facecolor=colours[name], edgecolor="none") for name in legend_order],
        legend_order,
        ncol=6,
        loc="lower center",
        bbox_to_anchor=(0.52, 0.025),
        fontsize=9.5,
        columnspacing=1.4,
        handlelength=1.5,
    )

    return _save(fig, output_dir, "B2", dpi)


# ---------------------------------------------------------------------------
# Figure B.3
# ---------------------------------------------------------------------------


def _violin_panel(
    ax: plt.Axes,
    data: pd.DataFrame,
    group_col: str,
    order: Sequence[str],
    labels: Sequence[str],
    colour: str,
    letter: str,
    title: str,
    show_ylabel: bool,
) -> None:
    frame = data[data[group_col].isin(order)].copy()
    frame[group_col] = pd.Categorical(frame[group_col], categories=order, ordered=True)
    sns.violinplot(
        data=frame,
        x=group_col,
        y="delta_score",
        order=order,
        cut=2,
        inner=None,
        linewidth=0.6,
        color=colour,
        alpha=0.35,
        saturation=0.55,
        ax=ax,
    )
    sns.boxplot(
        data=frame,
        x=group_col,
        y="delta_score",
        order=order,
        width=0.19,
        showfliers=False,
        boxprops={"facecolor": "white", "edgecolor": GREY, "linewidth": 1},
        medianprops={"color": GREY, "linewidth": 1.2},
        whiskerprops={"color": GREY, "linewidth": 1},
        capprops={"color": GREY, "linewidth": 1},
        ax=ax,
    )
    means = frame.groupby(group_col, observed=False)["delta_score"].mean().reindex(order)
    ax.scatter(np.arange(len(order)), means, marker="D", s=42, facecolor="white", edgecolor=GREY, zorder=6)
    counts = frame.groupby(group_col, observed=False).size().reindex(order, fill_value=0)
    ax.set_xticks(np.arange(len(order)), [f"{lab}\nn = {int(n)}" for lab, n in zip(labels, counts)])
    ax.axhline(0, color="#737980", linestyle=(0, (4, 4)), linewidth=1)
    _panel_title(ax, letter, title)
    ax.set_xlabel("")
    ax.set_ylabel("Same-agent utility change" if show_ylabel else "")
    ax.set_ylim(-65, 32)
    ax.grid(axis="x", visible=False)
    ax.spines[["top", "right"]].set_visible(False)


def figure_b3(ds: AnalysisSource, output_dir: Path, dpi: int) -> Path:
    frames: dict[str, pd.DataFrame] = {}
    for scenario, case in [("A8_FM", "A"), ("B6_PTI", "B")]:
        d = ds.scenario_csv(scenario, "person_level_impacts.csv.gz")
        d = d[_truthy(d["baseline_target_line_rider"])].copy()
        d["age_plot"] = d["age_group"].astype(str)
        d["gender_plot"] = d["gender_group"].astype(str).str.lower()
        d["car_plot"] = d["car_availability_group"].astype(str).str.lower()
        frames[case] = d

    fig, axes = plt.subplots(2, 3, figsize=(14.3, 8.6), sharey=True)
    fig.subplots_adjust(left=0.07, right=0.99, bottom=0.09, top=0.88, wspace=0.18, hspace=0.43)
    _case_heading(fig, 0.07, 0.985, "A")
    _case_heading(fig, 0.07, 0.50, "B")
    specifications = [
        ("age_plot", ["<25", "25-44", "45-64", "65+"], ["<25", "25-44", "45-64", "65+"], "Age"),
        ("gender_plot", ["f", "m"], ["Female", "Male"], "Gender"),
        ("car_plot", ["always", "never"], ["Always", "Never"], "Car availability"),
    ]
    letters = iter("abcdef")
    for row, case in enumerate(["A", "B"]):
        for col, (field, order, labels, title) in enumerate(specifications):
            _violin_panel(
                axes[row, col],
                frames[case],
                field,
                order,
                labels,
                CASE_COLOURS[case],
                next(letters),
                title,
                show_ylabel=(col == 0),
            )
    return _save(fig, output_dir, "B3", dpi)


# ---------------------------------------------------------------------------
# Figures B.4 and B.9: common temporal aggregation
# ---------------------------------------------------------------------------


def _temporal_summary(ds: AnalysisSource, scenario: str) -> pd.DataFrame:
    trips = ds.scenario_csv(scenario, "trip_level_impacts.csv.gz")
    trips = trips[_truthy(trips["baseline_target_line_trip"])].copy()
    dep = pd.to_numeric(trips["b0_dep_sec"], errors="coerce")
    trips["bin"] = np.floor(dep / 3600 / 3).clip(0, 7).astype("Int64")
    trips["delta_journey_min"] = pd.to_numeric(trips["delta_journey_sec"], errors="coerce") / 60
    trips["scenario_wait_min"] = pd.to_numeric(trips["scenario_wait_sec"], errors="coerce") / 60
    trips["is_drt"] = _truthy(trips["scenario_drt_trip"])
    rows = []
    for bin_id in range(8):
        group = trips[trips["bin"].eq(bin_id)]
        drt = group[group["is_drt"]]
        rows.append(
            {
                "bin": bin_id,
                "label": f"{3 * bin_id:02d}–{3 * (bin_id + 1):02d}",
                "n": int(group["delta_journey_min"].notna().sum()),
                "mean_delta_journey": float(group["delta_journey_min"].mean()),
                "drt_n": int(drt["scenario_wait_min"].notna().sum()),
                "mean_drt_wait": float(drt["scenario_wait_min"].mean()),
            }
        )
    return pd.DataFrame(rows)


def _annotated_bars(
    ax: plt.Axes,
    summary: pd.DataFrame,
    value_col: str,
    n_col: str,
    colour: str,
    letter: str,
    title: str,
    ylabel: str,
    ylim: tuple[float, float],
    robust_n: int,
) -> None:
    x = np.arange(8)
    values = summary[value_col].to_numpy(float)
    counts = summary[n_col].to_numpy(int)
    clipped = np.clip(values, ylim[0] + 0.5, ylim[1] - 0.5)
    bars = ax.bar(x, clipped, width=0.67, color=colour, edgecolor=colour, alpha=0.78)
    for bar, n in zip(bars, counts):
        if 0 < n < robust_n:
            bar.set_facecolor(mpl.colors.to_rgba(colour, 0.13))
            bar.set_hatch("////")
            bar.set_linewidth(1.1)
    for i, (value, n) in enumerate(zip(values, counts)):
        if n == 0 or not np.isfinite(value):
            continue
        if value < ylim[0] + 0.5:
            ax.scatter(i, ylim[0] + 0.5, marker="v", s=55, facecolor="white", edgecolor=colour, zorder=5)
            ax.text(i + 0.08, ylim[0] + 1.15, f"{value:.1f}", color=colour, fontsize=8.5, ha="left")
        elif value > ylim[1] - 0.5:
            ax.scatter(i, ylim[1] - 0.5, marker="^", s=55, facecolor="white", edgecolor=colour, zorder=5)
            ax.text(i + 0.08, ylim[1] - 1.4, f"{value:.1f}", color=colour, fontsize=8.5, ha="left")
        else:
            offset = 0.7 if value >= 0 else -1.15
            va = "bottom" if value >= 0 else "top"
            ax.text(i, value + offset, f"{value:.1f}", ha="center", va=va, fontsize=8.4)
    ax.axhline(0, color="#737980", linestyle=(0, (4, 4)), linewidth=1)
    _panel_title(ax, letter, title)
    ax.set_ylabel(ylabel)
    ax.set_ylim(*ylim)
    ax.set_xticks(x, [f"{label}\nn = {n}" for label, n in zip(summary["label"], counts)])
    ax.set_xlabel("B0 departure period")
    ax.grid(axis="x", visible=False)
    ax.spines[["top", "right"]].set_visible(False)
    for tick, n in zip(ax.get_xticklabels(), counts):
        if n == 0:
            tick.set_color("#A3A7AB")
        elif n < robust_n:
            tick.set_color(colour)


def figure_b4(ds: AnalysisSource, output_dir: Path, dpi: int) -> Path:
    summaries = {"A": _temporal_summary(ds, "A8_FM"), "B": _temporal_summary(ds, "B6_PTI")}
    fig, axes = plt.subplots(2, 2, figsize=(14.2, 9.0))
    fig.subplots_adjust(left=0.07, right=0.99, bottom=0.10, top=0.88, wspace=0.16, hspace=0.42)
    _case_heading(fig, 0.07, 0.985, "A")
    _case_heading(fig, 0.565, 0.985, "B")
    _annotated_bars(
        axes[0, 0], summaries["A"], "mean_delta_journey", "n", CASE_COLOURS["A"], "a",
        "Paired target-route journey time", "Mean change in minutes", (-32, 13), 3,
    )
    _annotated_bars(
        axes[0, 1], summaries["B"], "mean_delta_journey", "n", CASE_COLOURS["B"], "b",
        "Paired target-route journey time", "", (-32, 13), 3,
    )
    _annotated_bars(
        axes[1, 0], summaries["A"], "mean_drt_wait", "drt_n", CASE_COLOURS["A"], "c",
        "Waiting on DRT-containing journeys", "Waiting in minutes", (0, 38), 3,
    )
    _annotated_bars(
        axes[1, 1], summaries["B"], "mean_drt_wait", "drt_n", CASE_COLOURS["B"], "d",
        "Waiting on DRT-containing journeys", "", (0, 38), 3,
    )
    return _save(fig, output_dir, "B4", dpi)


# ---------------------------------------------------------------------------
# Figure B.6
# ---------------------------------------------------------------------------


def _wgs84_to_utm32(lon: float, lat: float) -> tuple[float, float]:
    """Convert WGS84 lon/lat to ETRS89 / UTM zone 32N metre coordinates.

    At the precision needed here, WGS84 and ETRS89 are coincident.  Keeping
    this small conversion local avoids an online geocoder or a GIS dependency.
    """
    a = 6_378_137.0
    e2 = 0.0066943799901413165
    k0 = 0.9996
    zone = 32
    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    lon0 = math.radians((zone - 1) * 6 - 180 + 3)
    ep2 = e2 / (1 - e2)
    sin_lat = math.sin(lat_r)
    cos_lat = math.cos(lat_r)
    tan_lat = math.tan(lat_r)
    n = a / math.sqrt(1 - e2 * sin_lat**2)
    t = tan_lat**2
    c = ep2 * cos_lat**2
    aa = cos_lat * (lon_r - lon0)
    m = a * (
        (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * lat_r
        - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * math.sin(2 * lat_r)
        + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * math.sin(4 * lat_r)
        - (35 * e2**3 / 3072) * math.sin(6 * lat_r)
    )
    x = k0 * n * (
        aa
        + (1 - t + c) * aa**3 / 6
        + (5 - 18 * t + t**2 + 72 * c - 58 * ep2) * aa**5 / 120
    ) + 500_000
    y = k0 * (
        m
        + n
        * tan_lat
        * (
            aa**2 / 2
            + (5 - t + 9 * c + 4 * c**2) * aa**4 / 24
            + (61 - 58 * t + t**2 + 600 * c - 330 * ep2) * aa**6 / 720
        )
    )
    return x, y


HUBS = {
    "A": [_wgs84_to_utm32(13.591778, 52.675583)],  # Bernau station
    "B": [
        _wgs84_to_utm32(14.059694, 52.366611),  # Fuerstenwalde station
        _wgs84_to_utm32(13.925278, 52.253056),  # Storkow station
    ],
}


def _distance_frame(ds: AnalysisSource, scenario: str, case: str) -> pd.DataFrame:
    d = ds.scenario_csv(scenario, "person_level_impacts.csv.gz")
    d = d[_truthy(d["baseline_target_line_rider"])].copy()
    x = pd.to_numeric(d["home_x"], errors="coerce").to_numpy(float)
    y = pd.to_numeric(d["home_y"], errors="coerce").to_numpy(float)
    distances = np.vstack([np.hypot(x - hx, y - hy) for hx, hy in HUBS[case]])
    d["distance_km"] = np.nanmin(distances, axis=0) / 1000
    d = d[np.isfinite(d["distance_km"]) & np.isfinite(pd.to_numeric(d["delta_score"], errors="coerce"))]
    d["used_drt"] = _truthy(d["scenario_drt_user"]).to_numpy()
    d["quartile"] = pd.qcut(
        d["distance_km"].rank(method="first"), 4, labels=["Q1", "Q2", "Q3", "Q4"]
    )
    return d


def figure_b6(ds: AnalysisSource, output_dir: Path, dpi: int) -> Path:
    frames = {
        "A": _distance_frame(ds, "A8_FM", "A"),
        "B": _distance_frame(ds, "B6_PTI", "B"),
    }
    fig, axes = plt.subplots(2, 2, figsize=(14.7, 9.1))
    fig.subplots_adjust(left=0.07, right=0.99, bottom=0.11, top=0.90, wspace=0.18, hspace=0.42)
    _case_heading(fig, 0.07, 0.99, "A")
    _case_heading(fig, 0.56, 0.99, "B")
    for col, case in enumerate(["A", "B"]):
        d = frames[case]
        colour = CASE_COLOURS[case]
        ax = axes[0, col]
        x, y = _finite_pair(d["distance_km"], d["delta_score"])
        ax.scatter(x, y, s=30, color=colour, alpha=0.70, edgecolor=GREY, linewidth=0.35)
        _linear_overlay(ax, x, y, colour)
        ax.axhline(0, color="#737980", linestyle=(0, (4, 4)), linewidth=1)
        corr = stats.pearsonr(x, y).statistic if len(x) > 1 else float("nan")
        ax.text(
            0.025,
            0.955,
            f"Pearson r = {corr:.2f}\nn = {len(x):,}",
            transform=ax.transAxes,
            va="top",
            fontsize=10.5,
            bbox={"boxstyle": "round,pad=.25", "facecolor": "white", "edgecolor": "#C8CDD2", "alpha": 0.92},
        )
        _panel_title(ax, "a" if case == "A" else "b", "Distance to rail hub and same-agent utility")
        ax.set_xlabel("Distance from home to nearest rail hub (km)")
        ax.set_ylabel("Same-agent utility change" if col == 0 else "")
        ax.spines[["top", "right"]].set_visible(False)

        q = (
            d.groupby("quartile", observed=False)
            .agg(n=("distance_km", "size"), median=("distance_km", "median"), share=("used_drt", "mean"))
            .reset_index()
        )
        axb = axes[1, col]
        bars = axb.bar(np.arange(4), 100 * q["share"], color=colour, alpha=0.72, edgecolor=colour, width=0.62)
        for bar, share in zip(bars, q["share"]):
            axb.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2.0, f"{100*share:.1f}%", ha="center", fontweight="bold")
        axb.set_xticks(
            np.arange(4),
            [f"{row.quartile}\n{row.median:.1f} km\nn = {int(row.n)}" for row in q.itertuples()],
        )
        axb.set_ylim(0, 86)
        axb.set_ylabel("Affected travellers using DRT (%)" if col == 0 else "")
        axb.set_xlabel("Distance quartile, median distance and affected travellers")
        _panel_title(axb, "c" if case == "A" else "d", "DRT use by distance quartile")
        axb.grid(axis="x", visible=False)
        axb.spines[["top", "right"]].set_visible(False)
    return _save(fig, output_dir, "B6", dpi)


# ---------------------------------------------------------------------------
# Figure B.7
# ---------------------------------------------------------------------------


def _violin_with_points(
    ax: plt.Axes,
    data: pd.DataFrame,
    group_col: str,
    order: Sequence[str],
    labels: Sequence[str],
    colour: str,
) -> None:
    frame = data[data[group_col].isin(order)].copy()
    frame[group_col] = pd.Categorical(frame[group_col], categories=order, ordered=True)
    sns.violinplot(data=frame, x=group_col, y="delta_plot", order=order, cut=1, inner=None, color=colour, alpha=0.28, linewidth=0.5, ax=ax)
    sns.stripplot(data=frame, x=group_col, y="delta_plot", order=order, color=colour, alpha=0.25, jitter=0.16, size=2.2, ax=ax)
    sns.boxplot(
        data=frame,
        x=group_col,
        y="delta_plot",
        order=order,
        width=0.24,
        showfliers=False,
        boxprops={"facecolor": "white", "edgecolor": GREY},
        whiskerprops={"color": GREY},
        capprops={"color": GREY},
        medianprops={"color": GREY},
        ax=ax,
    )
    means = frame.groupby(group_col, observed=False)["delta_score"].mean().reindex(order)
    counts = frame.groupby(group_col, observed=False).size().reindex(order, fill_value=0)
    ax.scatter(np.arange(len(order)), np.clip(means, -59, 16), marker="D", s=48, facecolor="white", edgecolor=GREY, zorder=8)
    for i, mean in enumerate(means):
        ax.text(i + 0.18, max(-57, float(mean)), f"{mean:.2f}", va="center", fontsize=9.5)
    ax.set_xticks(np.arange(len(order)), [f"{lab}\nn = {int(n):,}" for lab, n in zip(labels, counts)])


def figure_b7(ds: AnalysisSource, output_dir: Path, dpi: int) -> Path:
    d = ds.scenario_csv("C22_PTI", "person_level_impacts.csv.gz")
    d = d[_truthy(d["baseline_target_line_rider"])].copy()
    d["income"] = pd.to_numeric(d["income"], errors="coerce")
    d["delta_score"] = pd.to_numeric(d["delta_score"], errors="coerce")
    d = d[np.isfinite(d["income"]) & (d["income"] > 0) & np.isfinite(d["delta_score"])].copy()
    d["income_group_plot"] = d["income_group"].astype(str).str.lower()
    d["delta_plot"] = d["delta_score"].clip(lower=-59)

    fig, axes = plt.subplots(1, 2, figsize=(14.8, 6.35))
    fig.subplots_adjust(left=0.07, right=0.99, bottom=0.13, top=0.82, wspace=0.18)
    _case_heading(fig, 0.07, 0.97, "C")
    colour = CASE_COLOURS["C"]
    ax = axes[0]
    x, y = _finite_pair(d["income"], d["delta_score"])
    ax.scatter(x, np.clip(y, -59, None), s=12, color=colour, alpha=0.30, edgecolor="none")
    _linear_overlay(ax, x, y, colour)
    ax.axhline(0, color="#737980", linestyle=(0, (4, 4)), linewidth=1)
    corr = stats.pearsonr(x, y).statistic
    ax.text(
        0.025, 0.95, f"Pearson r = {corr:.2f}\nn = {len(x):,}", transform=ax.transAxes, va="top",
        bbox={"boxstyle": "round,pad=.25", "facecolor": "white", "edgecolor": "#C8CDD2", "alpha": 0.92},
    )
    below = int((y < -60).sum())
    if below:
        ax.scatter(np.nanpercentile(x[y < -60], 50), -59, marker="v", s=55, color=colour, edgecolor=GREY, linewidth=0.5, zorder=6)
        ax.text(np.nanpercentile(x[y < -60], 50) + 60, -57.8, f"{below} observation{'s' if below != 1 else ''} below −60", fontsize=8.8)
    _panel_title(ax, "a", "Monthly income and same-agent utility")
    ax.set_xlabel("Monthly income attribute")
    ax.set_ylabel("Same-agent utility change")
    ax.set_ylim(-60, 16)
    ax.spines[["top", "right"]].set_visible(False)

    ax = axes[1]
    _violin_with_points(ax, d, "income_group_plot", ["low", "middle", "high"], ["Low", "Middle", "High"], colour)
    ax.axhline(0, color="#737980", linestyle=(0, (4, 4)), linewidth=1)
    _panel_title(ax, "b", "Same-agent utility by income group")
    ax.set_xlabel("")
    ax.set_ylabel("Same-agent utility change")
    ax.set_ylim(-60, 16)
    ax.grid(axis="x", visible=False)
    ax.spines[["top", "right"]].set_visible(False)
    if below:
        ax.scatter(0, -59, marker="v", s=50, color=colour, edgecolor=GREY, linewidth=0.5, zorder=9)
    return _save(fig, output_dir, "B7", dpi)


# ---------------------------------------------------------------------------
# Figure B.8
# ---------------------------------------------------------------------------


def _horizontal_share_bars(
    ax: plt.Axes,
    labels: Sequence[str],
    counts: Sequence[int],
    colour: str,
    letter: str,
    title: str,
) -> None:
    counts_arr = np.asarray(counts, dtype=float)
    total = counts_arr.sum()
    shares = 100 * counts_arr / total if total else counts_arr
    y = np.arange(len(labels))[::-1]
    bars = ax.barh(y, shares, color=colour, alpha=0.78, height=0.64)
    for bar, share, count in zip(bars, shares, counts_arr.astype(int)):
        ax.text(bar.get_width() + 0.8, bar.get_y() + bar.get_height() / 2, f"{share:.1f}%\nn = {count:,}", va="center", fontsize=9.2)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, max(80, float(np.max(shares)) + 8))
    ax.set_xlabel("Share of trips (%)")
    _panel_title(ax, letter, title)
    ax.grid(axis="y", visible=False)
    ax.spines[["top", "right"]].set_visible(False)


def figure_b8(ds: AnalysisSource, output_dir: Path, dpi: int) -> Path:
    scenario = "C22_PTI"
    colour = CASE_COLOURS["C"]
    transitions = ds.scenario_csv(scenario, "mode_transitions_original_target_bus_trips.csv")
    origins = ds.scenario_csv(scenario, "drt_mode_origins.csv")
    trips = ds.scenario_csv(scenario, "trip_level_impacts.csv.gz")
    target = trips[_truthy(trips["baseline_target_line_trip"])].copy()

    transition_classes = {
        "DRT-containing": ["target_bus_to_DRT"],
        "Other PT": ["target_bus_to_other_PT"],
        "Car": ["target_bus_to_car"],
        "Active": ["target_bus_to_walk", "target_bus_to_bike"],
        "Ride or other": ["target_bus_to_other"],
    }
    dest_counts = [
        int(transitions.loc[transitions["transition_class"].isin(classes), "trips"].sum())
        for classes in transition_classes.values()
    ]
    origin_classes = {
        "Target route": ["target_bus_to_DRT"],
        "Other PT": ["other_PT_to_DRT"],
        "Car": ["car_to_DRT"],
        "Active": ["active_mode_to_DRT"],
        "Ride or other": ["other_mode_to_DRT"],
    }
    origin_counts = [
        int(origins.loc[origins["transition_class"].isin(classes), "trips"].sum())
        for classes in origin_classes.values()
    ]

    fig = plt.figure(figsize=(15.2, 8.95))
    gs = fig.add_gridspec(2, 6, left=0.075, right=0.99, bottom=0.11, top=0.88, hspace=0.47, wspace=0.40)
    ax_a = fig.add_subplot(gs[0, :3])
    ax_b = fig.add_subplot(gs[0, 3:])
    ax_c = fig.add_subplot(gs[1, :2])
    ax_d = fig.add_subplot(gs[1, 2:4])
    ax_e = fig.add_subplot(gs[1, 4:])
    _case_heading(fig, 0.075, 0.985, "C")

    _horizontal_share_bars(ax_a, list(transition_classes), dest_counts, colour, "a", "Destinations of B0 target-route trips")
    _horizontal_share_bars(ax_b, list(origin_classes), origin_counts, colour, "b", "B0 origins of DRT-containing trips")

    b0_wait = pd.to_numeric(target["b0_wait_sec"], errors="coerce") / 60
    scenario_wait = pd.to_numeric(target["scenario_wait_sec"], errors="coerce") / 60
    for values, label, line_colour, style in [
        (b0_wait, "B0", GREY, (0, (5, 3))),
        (scenario_wait, "C22-PTI", colour, "solid"),
    ]:
        x, y = _ecdf(values)
        ax_c.step(x, y, where="post", color=line_colour, linewidth=2.0, linestyle=style, label=label)
    ax_c.set_xlim(0, 70)
    ax_c.set_ylim(0, 1.02)
    ax_c.set_xlabel("Waiting (minutes)")
    ax_c.set_ylabel("Cumulative share")
    _panel_title(ax_c, "c", "Paired-journey waiting")
    ax_c.legend(loc="lower right")
    beyond_b0 = int((b0_wait > 70).sum())
    beyond_s = int((scenario_wait > 70).sum())
    ax_c.text(
        0.98,
        0.08,
        f">70 min: B0 n = {beyond_b0}; C22-PTI n = {beyond_s}",
        transform=ax_c.transAxes,
        ha="right",
        fontsize=8.2,
        bbox={"boxstyle": "round,pad=.2", "facecolor": "white", "edgecolor": "#CCD1D5"},
    )
    ax_c.spines[["top", "right"]].set_visible(False)

    valid_b0 = b0_wait[np.isfinite(b0_wait)].to_numpy(float)
    valid_s = scenario_wait[np.isfinite(scenario_wait)].to_numpy(float)
    level = {
        "Mean": [float(np.mean(valid_b0)), float(np.mean(valid_s))],
        "P95": [float(np.percentile(valid_b0, 95)), float(np.percentile(valid_s, 95))],
    }
    dispersion = {
        "Gini": [_gini(valid_b0), _gini(valid_s)],
        "CV": [float(np.std(valid_b0, ddof=1) / np.mean(valid_b0)), float(np.std(valid_s, ddof=1) / np.mean(valid_s))],
    }

    def grouped(ax: plt.Axes, values: dict[str, list[float]], letter: str, title: str, ylabel: str, fmt: str) -> None:
        names = list(values)
        x = np.arange(len(names))
        width = 0.34
        b0 = ax.bar(x - width / 2, [values[n][0] for n in names], width, color=GREY, label="B0")
        intervention = ax.bar(x + width / 2, [values[n][1] for n in names], width, color=colour, label="C22-PTI")
        for bar in [*b0, *intervention]:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.03 * max(ax.get_ylim()[1], 1), format(bar.get_height(), fmt), ha="center", va="bottom", fontsize=9)
        ax.set_xticks(x, names)
        ax.set_ylabel(ylabel)
        _panel_title(ax, letter, title)
        ax.grid(axis="x", visible=False)
        ax.spines[["top", "right"]].set_visible(False)

    grouped(ax_d, level, "d", "Mean and P95 waiting", "Minutes", ".1f")
    grouped(ax_e, dispersion, "e", "Relative dispersion", "Dispersion measure", ".2f")
    handles = [Patch(facecolor=GREY), Patch(facecolor=colour)]
    fig.legend(handles, ["B0", "C22-PTI"], loc="lower center", ncol=2, bbox_to_anchor=(0.68, 0.025))
    return _save(fig, output_dir, "B8", dpi)


# ---------------------------------------------------------------------------
# Figure B.9
# ---------------------------------------------------------------------------


def _temporal_line_panel(
    ax: plt.Axes,
    summary: pd.DataFrame,
    value_col: str,
    n_col: str,
    letter: str,
    title: str,
    ylabel: str,
    ylim: tuple[float, float],
    clip_low: float | None = None,
) -> None:
    x = np.arange(8)
    values = summary[value_col].to_numpy(float)
    counts = summary[n_col].to_numpy(int)
    robust = counts >= 10
    line_values = values.copy()
    if clip_low is not None:
        line_values = np.maximum(line_values, clip_low)
    ok = np.isfinite(line_values) & robust
    ax.plot(x[ok], line_values[ok], color=CASE_COLOURS["C"], linewidth=1.8)
    ax.scatter(x[ok], line_values[ok], s=45, color=CASE_COLOURS["C"], edgecolor="white", linewidth=0.6, zorder=4)
    weak = np.isfinite(line_values) & ~robust & (counts > 0)
    ax.scatter(x[weak], line_values[weak], s=38, color=CASE_COLOURS["C"], alpha=0.25, edgecolor="white", linewidth=0.5, zorder=4)
    if clip_low is not None:
        clipped = np.isfinite(values) & (values < clip_low)
        for i in np.flatnonzero(clipped):
            ax.scatter(i, clip_low + 0.25, marker="v", s=50, facecolor="white", edgecolor=CASE_COLOURS["C"], zorder=6)
            ax.text(i + 0.08, clip_low + 0.75, f"{values[i]:.1f} min", color=CASE_COLOURS["C"], fontsize=8.5)
    ax.axhline(0, color="#737980", linestyle=(0, (4, 4)), linewidth=1)
    _panel_title(ax, letter, title)
    ax.set_ylabel(ylabel)
    ax.set_ylim(*ylim)
    ax.set_xticks(x, [f"{label}\n\nn = {n}" for label, n in zip(summary["label"], counts)], rotation=28, ha="right")
    ax.set_xlabel("B0 departure period")
    ax.grid(axis="x", visible=False)
    ax.spines[["top", "right"]].set_visible(False)
    for tick, n in zip(ax.get_xticklabels(), counts):
        if n < 10:
            tick.set_color(mpl.colors.to_rgba(CASE_COLOURS["C"], 0.55))


def figure_b9(ds: AnalysisSource, output_dir: Path, dpi: int) -> Path:
    summary = _temporal_summary(ds, "C22_PTI")
    fig, axes = plt.subplots(1, 2, figsize=(14.8, 5.45))
    fig.subplots_adjust(left=0.07, right=0.99, bottom=0.22, top=0.78, wspace=0.20)
    _case_heading(fig, 0.07, 0.98, "C")
    _temporal_line_panel(
        axes[0], summary, "mean_delta_journey", "n", "a", "Paired target-route journey time",
        "Mean change (minutes)", (-10, 5), clip_low=-9.6,
    )
    _temporal_line_panel(
        axes[1], summary, "mean_drt_wait", "drt_n", "b", "Waiting on DRT-containing journeys",
        "Mean waiting (minutes)", (-2, 22), clip_low=None,
    )
    return _save(fig, output_dir, "B9", dpi)


FIGURE_FUNCTIONS: dict[str, Callable[[AnalysisSource, Path, int], Path]] = {
    "B1": figure_b1,
    "B2": figure_b2,
    "B3": figure_b3,
    "B4": figure_b4,
    "B6": figure_b6,
    "B7": figure_b7,
    "B8": figure_b8,
    "B9": figure_b9,
}


def _normalise_figure(value: str) -> str:
    key = value.upper().replace("FIGURE", "").replace(".", "").replace("_", "").strip()
    if key in {"ALL", "APPENDIX"}:
        return "ALL"
    if not key.startswith("B") and key.isdigit():
        key = "B" + key
    if key not in FIGURE_FUNCTIONS:
        choices = ", ".join(FIGURE_FUNCTIONS)
        raise argparse.ArgumentTypeError(f"Unknown appendix figure {value!r}; choose all or {choices}")
    return key


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--analysis-source",
        required=True,
        help="Extracted analysis_results directory, its parent, or ABC_analysis_results_01_04.tar.gz",
    )
    parser.add_argument("--output-dir", default="figures", help="Directory for generated PNG files")
    parser.add_argument(
        "--figures",
        nargs="+",
        type=_normalise_figure,
        default=["ALL"],
        metavar="B#",
        help="all (default), or one or more of: B1 B2 B3 B4 B6 B7 B8 B9",
    )
    parser.add_argument("--dpi", type=int, default=300, help="PNG resolution (default: 300)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    requested = list(FIGURE_FUNCTIONS) if "ALL" in args.figures else list(dict.fromkeys(args.figures))
    output_dir = Path(args.output_dir).expanduser().resolve()
    _set_style()
    print(f"Analysis source: {Path(args.analysis_source).expanduser().resolve()}")
    print(f"Output directory: {output_dir}")
    print(f"Figures: {', '.join(requested)}")
    with AnalysisSource(args.analysis_source) as ds:
        for key in requested:
            FIGURE_FUNCTIONS[key](ds, output_dir, args.dpi)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
