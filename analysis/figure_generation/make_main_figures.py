#!/usr/bin/env python3
"""Recreate the dissertation's main result figures from analysis outputs.

The generator accepts either the extracted ``analysis_results`` directory or
the original ``ABC_analysis_results_01_04.tar.gz`` archive.  All displayed
statistics are calculated from those inputs; the script contains labels and
scenario definitions, but no hard-coded result values.
"""

from __future__ import annotations

import argparse
from collections import OrderedDict
from dataclasses import dataclass
import gzip
from io import BytesIO
from pathlib import Path
from typing import Callable, Iterable

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter
import numpy as np
import pandas as pd

from data_access import AnalysisStore, bool_series
from plot_style import (
    B0,
    CASE,
    GRID,
    MODE,
    NAVY,
    PRICE,
    TEXT,
    ecdf,
    finish_axis,
    panel_title,
    save_figure,
)


STRUCTURAL = OrderedDict((s, c) for s, c in (
    ("A8_FM", "A"), ("B6_PTI", "B"), ("C22_PTI", "C")
))
FARES = OrderedDict((name, scenario) for name, scenario in (
    ("FM", "A8_FM"), ("SUB1", "A8_SUB1"), ("FL", "A8_FL"), ("FH", "A8_FH")
))
CASE_A_ALL = (
    "A4_FL", "A8_FL", "A12_FL", "A4_FH", "A8_FH", "A12_FH",
    "A8_FM", "A8_SUB1",
)
CASE_LINE = {"A": "890", "B": "435", "C": "X36"}
CASE_LABEL = {c: f"Case {c}\nLine {CASE_LINE[c]}" for c in "ABC"}
SCENARIO_DISPLAY = {
    "A4_FL": "A4-FL", "A8_FL": "A8-FL", "A12_FL": "A12-FL",
    "A4_FH": "A4-FH", "A8_FH": "A8-FH", "A12_FH": "A12-FH",
    "A8_FM": "A8-FM", "A8_SUB1": "A8-SUB1",
    "B6_PTI": "B6-PTI", "C22_PTI": "C22-PTI",
}

OUTPUT_NAMES = {
    "4.1": "Figure_4_1_baseline_demand_and_utilisation.png",
    "4.2": "Figure_4_2_passenger_utility_and_journey_time_v4_affected_travellers.png",
    "4.3": "Figure_4_3_waiting_and_request_service_v4_frozen.png",
    "4.4": "Figure_4_4_behavioural_adaptation.png",
    "4.5": "Figure_4_5_vehicle_resource_comparison.png",
    "4.6": "Figure_4_6_wider_road_network_effects.png",
    "4.7": "Figure_4_7_same_agent_utility_distributions.png",
    "4.8": "Figure_4_8_fleet_effects_FL_FH.png",
    "4.9": "Figure_4_9_fare_design_demand_pooling_retention.png",
    "4.10": "Figure_4_10_mode_response_fare_conditions.png",
    "4.11": "Figure_4_11_target_route_journey_time_and_utility.png",
    "4.12": "Figure_4_12_income_and_same_agent_utility_revised.png",
    "4.13": "Figure_4_13_B0_origins_of_DRT_containing_trips.png",
    "4.14": "Figure_4_14_distribution_of_paired_journey_waiting.png",
    "5.1": "Figure_5_1_context_and_replacement_outcomes_hybrid.png",
    "5.2": "Figure_5_2_supply_and_demand_responses.png",
    "5.3": "Figure_5_3_distributional_and_behavioural_evidence_revised.png",
}

RNG_SEED = 4711
MODE_ORDER = ("DRT", "Other PT", "Car", "Ride or other", "Active mode")
ORIGIN_ORDER = ("Target route", "Other PT", "Car", "Ride or other", "Active mode")


@dataclass(frozen=True)
class KPI:
    served: float
    wait_mean: float
    wait_p95: float
    total_vkt: float
    empty_vkt: float
    empty_share: float
    min_idle: float
    pooling: float
    sharing: float
    vkt_per_request: float


class FigureData:
    """Small, filtered views over :class:`AnalysisStore`.

    Person files contain the full 526,111-agent population.  They are streamed
    in chunks and filtered before caching so generating all figures does not
    retain ten population-sized frames in memory.
    """

    def __init__(self, store: AnalysisStore):
        self.store = store
        self._tables: dict[str, pd.DataFrame] = {}
        self._persons: dict[str, pd.DataFrame] = {}
        self._trips: dict[str, pd.DataFrame] = {}
        self._kpis: dict[str, KPI] = {}

    def table(self, relative: str) -> pd.DataFrame:
        if relative not in self._tables:
            self._tables[relative] = self.store.csv(relative, low_memory=False)
        return self._tables[relative].copy()

    @property
    def baseline(self) -> pd.DataFrame:
        return self.table("01_baseline/baseline_target_line_operational_summary.csv")

    @property
    def rq1(self) -> pd.DataFrame:
        return self.table("04_RQ_outputs/RQ1_context_suitability_A_B_C.csv")

    @property
    def rq2(self) -> pd.DataFrame:
        return self.table("04_RQ_outputs/RQ2_caseA_intervention_design.csv")

    @property
    def transitions(self) -> pd.DataFrame:
        return self.table("04_RQ_outputs/RQ3_original_bus_trip_mode_transitions.csv")

    @property
    def origins(self) -> pd.DataFrame:
        return self.table("04_RQ_outputs/RQ3_DRT_mode_origins.csv")

    @property
    def network(self) -> pd.DataFrame:
        return self.table("03_network/network_comparison_vs_B0.csv")

    def _read_gzip_chunks(
        self,
        relative: str,
        *,
        usecols: tuple[str, ...],
        keep: Callable[[pd.DataFrame], pd.Series],
    ) -> pd.DataFrame:
        raw = self.store.bytes(relative)
        selected: list[pd.DataFrame] = []
        with gzip.GzipFile(fileobj=BytesIO(raw)) as stream:
            reader = pd.read_csv(
                stream, usecols=list(usecols), chunksize=100_000, low_memory=False
            )
            for chunk in reader:
                mask = keep(chunk)
                if mask.any():
                    selected.append(chunk.loc[mask].copy())
        if not selected:
            return pd.DataFrame(columns=usecols)
        return pd.concat(selected, ignore_index=True)

    def target_persons(self, scenario: str) -> pd.DataFrame:
        if scenario not in self._persons:
            cols = (
                "person_id", "delta_score", "baseline_target_line_rider",
                "scenario_drt_user", "income", "income_group",
            )
            path = f"02_scenarios/{scenario}/person_level_impacts.csv.gz"
            frame = self._read_gzip_chunks(
                path, usecols=cols,
                keep=lambda x: bool_series(x["baseline_target_line_rider"]),
            )
            frame["delta_score"] = pd.to_numeric(frame["delta_score"], errors="coerce")
            frame["income"] = pd.to_numeric(frame["income"], errors="coerce")
            frame["scenario_drt_user"] = bool_series(frame["scenario_drt_user"])
            self._persons[scenario] = frame
        return self._persons[scenario].copy()

    def target_trips(self, scenario: str) -> pd.DataFrame:
        if scenario not in self._trips:
            cols = (
                "person_id", "b0_mode", "scenario_mode", "b0_wait_sec",
                "scenario_wait_sec", "delta_journey_sec", "scenario_drt_trip",
                "baseline_target_line_trip",
            )
            path = f"02_scenarios/{scenario}/trip_level_impacts.csv.gz"
            frame = self._read_gzip_chunks(
                path, usecols=cols,
                keep=lambda x: bool_series(x["baseline_target_line_trip"]),
            )
            for col in ("b0_wait_sec", "scenario_wait_sec", "delta_journey_sec"):
                frame[col] = pd.to_numeric(frame[col], errors="coerce")
            frame["scenario_drt_trip"] = bool_series(frame["scenario_drt_trip"])
            self._trips[scenario] = frame
        return self._trips[scenario].copy()

    def matrix_transitions(self, scenario: str) -> pd.DataFrame:
        return self.table(f"02_scenarios/{scenario}/mode_transitions_relevant.csv")

    def equity(self, scenario: str) -> pd.DataFrame:
        return self.table(f"02_scenarios/{scenario}/equity_utility_target_riders.csv")

    def kpi(self, scenario: str) -> KPI:
        if scenario not in self._kpis:
            frame = self.table(f"02_scenarios/{scenario}/drt_kpi_raw_final_window.csv")
            if frame.empty:
                raise ValueError(f"No final-window DRT KPI row for {scenario}")
            row = frame.iloc[0]

            def value(name: str, scale: float = 1.0) -> float:
                if name not in row or pd.isna(row[name]):
                    raise KeyError(f"{scenario}: missing required KPI {name}")
                return float(row[name]) / scale

            total = value("vehicle::totalDistance__mean", 1000)
            empty = value("vehicle::totalEmptyDistance__mean", 1000)
            served = value("customer::rides__mean")
            self._kpis[scenario] = KPI(
                served=served,
                wait_mean=value("customer::wait_average__mean", 60),
                wait_p95=value("customer::wait_p95__mean", 60),
                total_vkt=total,
                empty_vkt=empty,
                empty_share=empty / total,
                min_idle=value("vehicle::minCountIdleVehicles__mean"),
                pooling=value("sharing::poolingRate__mean"),
                sharing=value("sharing::sharingFactor__mean"),
                vkt_per_request=total / served,
            )
        return self._kpis[scenario]


def case_for_scenario(scenario: str) -> str:
    return scenario[0].upper()


def mode_label(value: object, *, ride_label: str = "Ride or other", active: bool = True) -> str:
    text = str(value)
    mapping = {
        "DRT_CONTAINING": "DRT", "TARGET_BUS": "Target route",
        "pt": "Other PT", "car": "Car", "ride": ride_label,
        "walk": "Active mode" if active else "Walk",
        "bike": "Active mode" if active else "Bike",
    }
    return mapping.get(text, text)


def origin_label(transition: object, *, ride_label: str = "Ride or other") -> str:
    mapping = {
        "target_bus_to_DRT": "Target route",
        "other_PT_to_DRT": "Other PT",
        "car_to_DRT": "Car",
        "other_mode_to_DRT": ride_label,
        "active_mode_to_DRT": "Active mode",
    }
    return mapping.get(str(transition), ride_label)


def finite(values: Iterable[float]) -> np.ndarray:
    array = np.asarray(list(values), dtype=float)
    return array[np.isfinite(array)]


def percentile(values: Iterable[float], q: float) -> float:
    clean = finite(values)
    return float(np.percentile(clean, q)) if clean.size else float("nan")


def _case_rows(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.assign(case=frame["case"].astype(str)).set_index("case").loc[list("ABC")].reset_index()


def _lighten(color: str, amount: float = 0.74) -> tuple[float, float, float]:
    import matplotlib.colors as mcolors

    rgb = np.asarray(mcolors.to_rgb(color))
    return tuple(rgb + (1.0 - rgb) * amount)


def _violin_box(
    ax: plt.Axes,
    groups: list[np.ndarray],
    colors: list[str],
    *,
    positions: np.ndarray | None = None,
    jitter: bool = False,
    width: float = 0.76,
) -> None:
    if positions is None:
        positions = np.arange(1, len(groups) + 1)
    parts = ax.violinplot(
        groups, positions=positions, widths=width, showmeans=False,
        showmedians=False, showextrema=False, bw_method=0.30,
    )
    for body, color in zip(parts["bodies"], colors):
        body.set_facecolor(color)
        body.set_edgecolor(TEXT)
        body.set_alpha(0.78)
        body.set_linewidth(0.8)
    box = ax.boxplot(
        groups, positions=positions, widths=width * 0.32, patch_artist=True,
        showfliers=False,
        medianprops={"color": TEXT, "linewidth": 1.5},
        boxprops={"facecolor": "white", "edgecolor": TEXT, "linewidth": 1.1},
        whiskerprops={"color": TEXT, "linewidth": 0.9},
        capprops={"color": TEXT, "linewidth": 0.9},
    )
    del box
    means = [np.mean(x) for x in groups]
    ax.scatter(positions, means, marker="D", s=34, facecolor="white", edgecolor=TEXT, zorder=5)
    if jitter:
        rng = np.random.default_rng(RNG_SEED)
        for pos, values, color in zip(positions, groups, colors):
            x = pos + rng.uniform(-width * 0.18, width * 0.18, len(values))
            ax.scatter(x, values, s=8, color=color, alpha=0.42, edgecolors="none", zorder=3)


def _post_mode(frame: pd.DataFrame, scenario: str, *, ride_label: str = "Ride or other") -> pd.Series:
    selected = frame[frame["scenario"] == scenario].copy()
    selected["display"] = selected["scenario_effective_mode"].map(
        lambda x: mode_label(x, ride_label=ride_label, active=True)
    )
    shares = selected.groupby("display", observed=True)["trips"].sum()
    shares = shares / shares.sum() * 100
    return shares.reindex(
        ["DRT", "Other PT", "Car", ride_label, "Active mode"], fill_value=0.0
    )


def _origin_mode(frame: pd.DataFrame, scenario: str, *, ride_label: str = "Ride or other") -> tuple[pd.Series, int]:
    selected = frame[frame["scenario"] == scenario].copy()
    selected["display"] = selected["transition_class"].map(
        lambda x: origin_label(x, ride_label=ride_label)
    )
    trips = selected.groupby("display", observed=True)["trips"].sum()
    total = int(trips.sum())
    shares = trips / total * 100
    return shares.reindex(
        ["Target route", "Other PT", "Car", ride_label, "Active mode"], fill_value=0.0
    ), total


def _stacked_horizontal(
    ax: plt.Axes,
    rows: list[pd.Series],
    labels: list[str],
    order: list[str],
    *,
    colors: dict[str, str],
    threshold: float = 4.0,
    height: float = 0.56,
) -> None:
    y = np.arange(len(rows))[::-1]
    left = np.zeros(len(rows))
    for key in order:
        values = np.asarray([float(row.get(key, 0.0)) for row in rows])
        bars = ax.barh(y, values, left=left, height=height, color=colors[key],
                       edgecolor="white", linewidth=0.8, label=key)
        for bar, value in zip(bars, values):
            if value >= threshold:
                cx = bar.get_x() + bar.get_width() / 2
                # White text on the two darkest fills.
                tc = "white" if key in {"Other PT", "Active mode", "Target route"} else TEXT
                ax.text(cx, bar.get_y() + bar.get_height() / 2, f"{value:.1f}",
                        ha="center", va="center", fontsize=8.2, color=tc,
                        fontweight="bold" if key in {"Other PT", "Target route"} else None)
        left += values
    ax.set_yticks(y, labels)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of trips (%)")
    finish_axis(ax, "x")


def _bar_values(ax: plt.Axes, bars, *, decimals: int = 1, suffix: str = "", fontsize: float = 8.2) -> None:
    span = max(ax.get_ylim()[1] - ax.get_ylim()[0], 1)
    for bar in bars:
        value = float(bar.get_height())
        ax.text(bar.get_x() + bar.get_width() / 2, value + span * 0.018,
                f"{value:.{decimals}f}{suffix}", ha="center", va="bottom", fontsize=fontsize)


def _hbar_values(ax: plt.Axes, bars, *, decimals: int = 1, suffix: str = "") -> None:
    span = max(ax.get_xlim()[1] - ax.get_xlim()[0], 1)
    for bar in bars:
        value = float(bar.get_width())
        ax.text(value + span * 0.014, bar.get_y() + bar.get_height() / 2,
                f"{value:.{decimals}f}{suffix}", ha="left", va="center", fontsize=8.2)


def make_4_1(data: FigureData, output: Path) -> None:
    base = _case_rows(data.baseline)
    metrics = (
        ("Boardings per departure", base["boardings"] / base["departures"], 2, ""),
        ("Distance-weighted occupancy", base["bus_distance_weighted_occupancy"], 2, ""),
        ("Empty bus VKT", 100 * base["bus_empty_vkt_share"], 1, "%"),
    )
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.8), sharey=True, constrained_layout=True)
    for idx, (ax, (title, values, decimals, suffix), letter) in enumerate(zip(axes, metrics, "abc")):
        y = np.arange(3)[::-1]
        bars = ax.barh(y, values, color=B0, height=0.48)
        ax.set_yticks(y)
        if idx == 0:
            ax.set_yticklabels([CASE_LABEL[c] for c in "ABC"])
        else:
            ax.tick_params(axis="y", labelleft=False)
        panel_title(ax, letter, title)
        ax.set_xlim(0, max(values) * 1.18)
        _hbar_values(ax, bars, decimals=decimals, suffix=suffix)
        finish_axis(ax, "x")
    save_figure(fig, output)


def make_4_2(data: FigureData, output: Path) -> None:
    scenarios = list(STRUCTURAL)
    persons = [finite(data.target_persons(s)["delta_score"]) for s in scenarios]
    trips = [finite(data.target_trips(s)["delta_journey_sec"] / 60) for s in scenarios]
    colors = [CASE[c] for c in "ABC"]
    fig, axes = plt.subplots(1, 2, figsize=(14, 7.2), constrained_layout=True)
    specs = (
        (axes[0], persons, "a", "Whole-day utility for affected travellers",
         "Same-agent utility change", (-35, 10), "lower"),
        (axes[1], trips, "b", "Journey time for B0 target-route trips",
         "Change in total journey time (min)", (-110, 70), "faster"),
    )
    for ax, groups, letter, title, ylabel, ylim, outcome in specs:
        _violin_box(ax, groups, colors)
        ax.axhline(0, color=TEXT, lw=1, ls=(0, (3, 3)))
        ax.set_ylim(*ylim)
        ax.set_ylabel(ylabel)
        ax.set_xticks(
            np.arange(1, 4),
            [f"{CASE_LABEL[c]}\nn = {len(g):,}" for c, g in zip("ABC", groups)],
        )
        panel_title(ax, letter, title)
        finish_axis(ax, "y")
        for pos, group, color in zip(range(1, 4), groups, colors):
            mean = np.mean(group)
            share = np.mean(group < 0) * 100
            ax.text(pos, 1.02, f"Mean {mean:+.2f}\n{share:.1f}% {outcome}",
                    transform=ax.get_xaxis_transform(), ha="center", va="bottom",
                    color=color, fontsize=9.2)
            below = int(np.sum(group < ylim[0]))
            above = int(np.sum(group > ylim[1]))
            if below:
                ax.text(pos, ylim[0] + (ylim[1] - ylim[0]) * .02,
                        f"{below} below range", ha="center", va="bottom", fontsize=8.3)
            if above:
                ax.text(pos, ylim[1] - (ylim[1] - ylim[0]) * .02,
                        f"{above} above range", ha="center", va="top", fontsize=8.3)
    save_figure(fig, output)


def _wait_table(ax: plt.Axes, b0: np.ndarray, scenario: np.ndarray, color: str) -> None:
    rows = [
        ["B0", f"{np.mean(b0):.2f}", f"{percentile(b0, 95):.2f}"],
        ["Replacement", f"{np.mean(scenario):.2f}", f"{percentile(scenario, 95):.2f}"],
    ]
    table = ax.table(
        cellText=rows, colLabels=["", "Mean", "P95"], colWidths=[.42, .18, .18],
        bbox=[.48, .055, .48, .245], cellLoc="right",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(7.8)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#CDD2D7")
        cell.set_linewidth(.55)
        cell.set_facecolor("white")
        if r == 0 or c == 0:
            cell.get_text().set_fontweight("bold")
        if r == 2:
            cell.get_text().set_color(color)


def make_4_3(data: FigureData, output: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12.8, 9.5), constrained_layout=True)
    for ax, (scenario, case), letter in zip(axes.flat[:3], STRUCTURAL.items(), "abc"):
        trips = data.target_trips(scenario)
        b0 = finite(trips["b0_wait_sec"] / 60)
        rep = finite(trips["scenario_wait_sec"] / 60)
        ecdf(ax, b0, label="B0", color=B0, linestyle="-")
        ecdf(ax, rep, label="Replacement", color=CASE[case], linestyle="-")
        ax.set_xlim(-1.5, 70)
        ax.set_ylim(0, 1.01)
        ax.set_xlabel("Total waiting within journey (min)")
        ax.set_ylabel("Cumulative share")
        panel_title(ax, letter, f"Journey waiting in Case {case} Line {CASE_LINE[case]}")
        _wait_table(ax, b0, rep, CASE[case])
        finish_axis(ax, "both")
    ax = axes[1, 1]
    means = [data.kpi(s).wait_mean for s in STRUCTURAL]
    p95s = [data.kpi(s).wait_p95 for s in STRUCTURAL]
    x = np.arange(3)
    width = .32
    b1 = ax.bar(x - width / 2, means, width, color=[CASE[c] for c in "ABC"], label="Mean")
    b2 = ax.bar(x + width / 2, p95s, width, facecolor="white",
                edgecolor=[CASE[c] for c in "ABC"], linewidth=1.6, hatch="///", label="P95")
    _bar_values(ax, b1, decimals=2)
    _bar_values(ax, b2, decimals=2)
    ax.set_xticks(x, [CASE_LABEL[c] for c in "ABC"])
    ax.set_ylabel("Request waiting (min)")
    panel_title(ax, "d", "DRT request waiting across cases")
    ax.legend(loc="upper left", ncol=2)
    finish_axis(ax, "y")
    save_figure(fig, output)


def _matrix_array(data: FigureData, scenario: str) -> tuple[np.ndarray, list[str], list[str]]:
    frame = data.matrix_transitions(scenario).copy()
    frame["b0"] = frame["b0_effective_mode"].map(lambda x: mode_label(x, active=False))
    frame["post"] = frame["scenario_effective_mode"].map(lambda x: mode_label(x, active=False))
    rows = ["Target route", "Other PT", "Car", "Ride or other", "Walk", "Bike"]
    cols = ["DRT", "Other PT", "Car", "Ride or other", "Walk", "Bike"]
    grouped = frame.groupby(["b0", "post"], observed=True)["trips"].sum().unstack(fill_value=0)
    matrix = grouped.reindex(index=rows, columns=cols, fill_value=0).astype(float)
    totals = matrix.sum(axis=1).replace(0, np.nan)
    matrix = matrix.div(totals, axis=0).fillna(0) * 100
    return matrix.to_numpy(), rows, cols


def _draw_heatmap(ax: plt.Axes, matrix: np.ndarray, rows: list[str], cols: list[str], color: str) -> None:
    cmap = LinearSegmentedColormap.from_list("case", ["#FFFFFF", color])
    ax.imshow(matrix, cmap=cmap, vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(np.arange(len(cols)), [x.replace(" ", "\n") for x in cols])
    ax.set_yticks(np.arange(len(rows)), rows)
    ax.set_xlabel("Post-replacement mode")
    ax.set_ylabel("B0 mode")
    ax.set_xticks(np.arange(-.5, len(cols), 1), minor=True)
    ax.set_yticks(np.arange(-.5, len(rows), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.1)
    ax.tick_params(which="minor", bottom=False, left=False)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = matrix[i, j]
            if value >= .5:
                ax.text(j, i, f"{value:.0f}", ha="center", va="center",
                        color="white" if value >= 74 else TEXT, fontsize=7.5)
    ax.spines[:].set_visible(False)


def make_4_4(data: FigureData, output: Path) -> None:
    fig = plt.figure(figsize=(14.5, 9.2), constrained_layout=True)
    gs = fig.add_gridspec(2, 3, height_ratios=[.72, 1.12])
    top = fig.add_subplot(gs[0, :])
    rows = [_post_mode(data.transitions, s) for s in STRUCTURAL]
    colors = {key: MODE[key] for key in MODE_ORDER}
    _stacked_horizontal(top, rows, [CASE_LABEL[c] for c in "ABC"], list(MODE_ORDER), colors=colors)
    top.set_xlabel("Share of B0 target-route trips (%)")
    panel_title(top, "a", "Post-replacement modes of B0 target-route trips")
    top.legend(ncol=5, loc="upper center", bbox_to_anchor=(.5, -.22), columnspacing=1.1,
               handlelength=1.0)
    for idx, ((scenario, case), letter) in enumerate(zip(STRUCTURAL.items(), "bcd")):
        ax = fig.add_subplot(gs[1, idx])
        matrix, rlabels, clabels = _matrix_array(data, scenario)
        _draw_heatmap(ax, matrix, rlabels, clabels, CASE[case])
        panel_title(ax, letter, f"Case {case} Line {CASE_LINE[case]}")
    save_figure(fig, output)


def make_4_5(data: FigureData, output: Path) -> None:
    fig = plt.figure(figsize=(14, 9), constrained_layout=True)
    gs = fig.add_gridspec(2, 3, height_ratios=[.88, 1.12])
    ax = fig.add_subplot(gs[0, :])
    base = _case_rows(data.baseline).set_index("case")
    y: list[float] = []
    values: list[float] = []
    bar_colors: list[str] = []
    for idx, (scenario, case) in enumerate(STRUCTURAL.items()):
        centre = (2 - idx) * 2.35
        bus = float(base.loc[case, "bus_vkt_km"])
        drt = data.kpi(scenario).total_vkt
        y.extend([centre + .36, centre - .36])
        values.extend([bus, drt])
        bar_colors.extend([B0, CASE[case]])
    bars = ax.barh(y, values, height=.62, color=bar_colors)
    ax.set_yticks([4.7, 2.35, 0], [CASE_LABEL[c] for c in "ABC"])
    ax.set_xlabel("Average daily vehicle kilometres (km)")
    panel_title(ax, "a", "Service-level vehicle movement")
    ax.set_xlim(0, max(values) * 1.15)
    for idx, (scenario, case) in enumerate(STRUCTURAL.items()):
        bus_bar, drt_bar = bars[idx * 2], bars[idx * 2 + 1]
        bus, drt = bus_bar.get_width(), drt_bar.get_width()
        for bar, name in ((bus_bar, "Removed bus"), (drt_bar, "DRT")):
            ax.text(max(bar.get_width() * .02, 18), bar.get_y() + bar.get_height() / 2,
                    name, color="white", fontweight="bold", ha="left", va="center", fontsize=8.2)
        ax.text(bus + max(values) * .012, bus_bar.get_y() + bus_bar.get_height()/2,
                f"{bus:,.0f} km", va="center", fontsize=8.2)
        ax.text(drt + max(values) * .012, drt_bar.get_y() + drt_bar.get_height()/2,
                f"{drt:,.0f} km   {100*drt/bus:.1f}%", va="center", fontsize=8.2)
    finish_axis(ax, "x")

    metrics = (
        ("b", "Empty DRT VKT", [100 * data.kpi(s).empty_share for s in STRUCTURAL],
         "Share of DRT VKT (%)", 1, "%"),
        ("c", "Pooled rides", [100 * data.kpi(s).pooling for s in STRUCTURAL],
         "Share of served requests (%)", 1, "%"),
        ("d", "Sharing factor", [data.kpi(s).sharing for s in STRUCTURAL],
         "Sharing factor", 2, ""),
    )
    for idx, (letter, title, vals, xlabel, decimals, suffix) in enumerate(metrics):
        ax = fig.add_subplot(gs[1, idx])
        yy = np.arange(3)[::-1]
        bars = ax.barh(yy, vals, color=[CASE[c] for c in "ABC"], height=.48)
        ax.set_yticks(yy, [CASE_LABEL[c] for c in "ABC"])
        ax.set_xlim(0, max(vals) * 1.17)
        ax.set_xlabel(xlabel)
        panel_title(ax, letter, title)
        _hbar_values(ax, bars, decimals=decimals, suffix=suffix)
        finish_axis(ax, "x")
    save_figure(fig, output)


def make_4_6(data: FigureData, output: Path) -> None:
    network = _case_rows(data.network)
    metrics = (
        ("Road VKT", "relative_delta_road_vkt_km"),
        ("Road travel time", "relative_delta_road_travel_time_h"),
        ("Network delay", "relative_delta_road_delay_h"),
    )
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.2), sharey=True, constrained_layout=True)
    all_values = np.concatenate([100 * network[col].to_numpy(float) for _, col in metrics])
    limit = max(abs(all_values.min()), abs(all_values.max())) * 1.36
    for idx, (ax, (title, col), letter) in enumerate(zip(axes, metrics, "abc")):
        vals = 100 * network[col].to_numpy(float)
        y = np.arange(3)[::-1]
        bars = ax.barh(y, vals, color=[CASE[c] for c in "ABC"], height=.48)
        ax.axvline(0, color=TEXT, ls=(0, (3, 3)), lw=.9)
        ax.set_xlim(-limit, limit)
        ax.set_yticks(y)
        if idx == 0:
            ax.set_yticklabels([CASE_LABEL[c] for c in "ABC"])
        else:
            ax.tick_params(axis="y", labelleft=False)
        ax.set_xlabel("Daily change from B0 (%)")
        panel_title(ax, letter, title)
        for bar, value in zip(bars, vals):
            offset = limit * .035
            ax.text(value + (offset if value >= 0 else -offset), bar.get_y()+bar.get_height()/2,
                    f"{value:+.3f}%", va="center", ha="left" if value >= 0 else "right", fontsize=8.1)
        finish_axis(ax, "x")
    save_figure(fig, output)


def _fare_for_scenario(scenario: str) -> str:
    if scenario.endswith("_FL"):
        return "FL"
    if scenario.endswith("_FH"):
        return "FH"
    if scenario == "A8_FM":
        return "FM"
    if scenario == "A8_SUB1":
        return "SUB1"
    raise ValueError(f"No fare family for {scenario}")


def make_4_7(data: FigureData, output: Path) -> None:
    groups = [finite(data.target_persons(s)["delta_score"]) for s in CASE_A_ALL]
    fare_groups = [_fare_for_scenario(s) for s in CASE_A_ALL]
    colors = [PRICE[f] for f in fare_groups]
    fig, ax = plt.subplots(figsize=(14, 5.3), constrained_layout=True)
    _violin_box(ax, groups, colors, jitter=True, width=.72)
    ax.axhline(0, color=TEXT, ls=(0, (3, 3)), lw=.9)
    ax.set_xticks(np.arange(1, 9), [SCENARIO_DISPLAY[s] for s in CASE_A_ALL])
    ax.set_ylabel("Same-agent utility change")
    ax.set_ylim(-45, 14)
    fig.suptitle("Case A  Line 890", x=.01, ha="left", color=NAVY,
                 fontweight="bold", fontsize=11)
    for pos, values in enumerate(groups, 1):
        ax.text(pos + .10, np.mean(values), f"{np.mean(values):+.2f}",
                va="center", fontsize=8.0)
    handles = [Patch(facecolor=PRICE[x], alpha=.72, label=x) for x in ("FM", "SUB1", "FL", "FH")]
    legend = ax.legend(handles=handles, title="Pricing condition", ncol=4,
                       loc="upper right", bbox_to_anchor=(1, 1.08), columnspacing=1.0)
    legend.get_title().set_fontweight("bold")
    finish_axis(ax, "y")
    save_figure(fig, output)


def _fleet_records(data: FigureData) -> pd.DataFrame:
    rows: list[dict[str, float | str]] = []
    rq2 = data.rq2.set_index("scenario")
    for fare in ("FL", "FH"):
        for fleet in (4, 8, 12):
            scenario = f"A{fleet}_{fare}"
            kpi = data.kpi(scenario)
            rows.append({
                "scenario": scenario,
                "fare": fare,
                "fleet": fleet,
                "median_utility": float(rq2.loc[scenario, "target_riders::median_delta_score"]),
                "wait_mean": kpi.wait_mean,
                "wait_p95": kpi.wait_p95,
                "min_idle": kpi.min_idle,
                "vkt_per_request": kpi.vkt_per_request,
            })
    return pd.DataFrame(rows)


def _annotated_line(
    ax: plt.Axes,
    x: np.ndarray,
    y: np.ndarray,
    *,
    color: str,
    label: str | None = None,
    marker: str = "o",
    linestyle: str = "-",
    decimals: int = 2,
) -> None:
    ax.plot(x, y, color=color, marker=marker, ls=linestyle, lw=1.6, ms=5, label=label)
    for xx, yy in zip(x, y):
        if marker == "s":
            xoffset, offset, va = 0, 7, "bottom"
        elif label == "FH":
            xoffset, offset, va = 9, -9, "top"
        else:
            xoffset, offset, va = -9, 7, "bottom"
        ax.annotate(
            f"{yy:.{decimals}f}", (xx, yy), xytext=(xoffset, offset),
            textcoords="offset points", color=color, ha="center", va=va, fontsize=7.7,
        )


def make_4_8(data: FigureData, output: Path) -> None:
    fleet = _fleet_records(data)
    fig, axes = plt.subplots(2, 2, figsize=(12.5, 8.2), constrained_layout=True)
    panels = (
        (axes[0, 0], "a", "Median same-agent utility", "median_utility", "Utility change"),
        (axes[1, 0], "c", "Minimum idle fleet", "min_idle", "Vehicles"),
        (axes[1, 1], "d", "VKT per served request", "vkt_per_request", "Kilometres"),
    )
    for ax, letter, title, metric, ylabel in panels:
        for fare in ("FL", "FH"):
            selected = fleet[fleet["fare"] == fare].sort_values("fleet")
            _annotated_line(ax, selected["fleet"].to_numpy(), selected[metric].to_numpy(float),
                            color=PRICE[fare], label=fare)
        ax.set_xticks([4, 8, 12])
        ax.set_xlabel("Fleet size")
        ax.set_ylabel(ylabel)
        panel_title(ax, letter, title)
        ax.margins(y=.15)
        finish_axis(ax, "y")

    ax = axes[0, 1]
    for fare in ("FL", "FH"):
        selected = fleet[fleet["fare"] == fare].sort_values("fleet")
        x = selected["fleet"].to_numpy()
        _annotated_line(ax, x, selected["wait_mean"].to_numpy(float),
                        color=PRICE[fare], label=fare, marker="o", linestyle="-")
        _annotated_line(ax, x, selected["wait_p95"].to_numpy(float),
                        color=PRICE[fare], marker="s", linestyle=(0, (4, 3)))
    ax.set_xticks([4, 8, 12])
    ax.set_xlabel("Fleet size")
    ax.set_ylabel("Minutes")
    panel_title(ax, "b", "DRT request waiting")
    ax.margins(y=.15)
    metric_handles = [
        Line2D([0], [0], color=TEXT, marker="o", label="Mean"),
        Line2D([0], [0], color=TEXT, marker="s", ls=(0, (4, 3)), label="P95"),
    ]
    ax.legend(handles=metric_handles, loc="upper center", bbox_to_anchor=(.55, .96), ncol=2)
    finish_axis(ax, "y")
    fig.suptitle("Case A  Line 890", x=.01, ha="left", color=NAVY,
                 fontweight="bold", fontsize=11)
    fare_handles = [Line2D([0], [0], color=PRICE[x], marker="o", label=x) for x in ("FL", "FH")]
    fig.legend(handles=fare_handles, title="Pricing condition", ncol=2,
               loc="upper right", bbox_to_anchor=(.99, 1.01))
    save_figure(fig, output)


def _fare_records(data: FigureData) -> pd.DataFrame:
    rows: list[dict[str, float | str]] = []
    transition = data.transitions
    for fare, scenario in FARES.items():
        kpi = data.kpi(scenario)
        post = _post_mode(transition, scenario)
        rows.append({
            "fare": fare,
            "scenario": scenario,
            "served": kpi.served,
            "pooling": 100 * kpi.pooling,
            "retention": float(post["DRT"]),
        })
    return pd.DataFrame(rows)


def _draw_demand_panel(ax: plt.Axes, data: FigureData, *, letter: str = "a") -> None:
    fares = _fare_records(data)
    x = np.arange(4)
    bars = ax.bar(x, fares["served"], color=[PRICE[x] for x in fares["fare"]], width=.58)
    ax.set_xticks(x, fares["fare"])
    ax.set_ylabel("Served requests per day")
    panel_title(ax, letter, "Realised DRT demand")
    _bar_values(ax, bars, decimals=2)
    finish_axis(ax, "y")


def _draw_pool_retention(ax: plt.Axes, data: FigureData, *, letter: str = "b") -> None:
    fares = _fare_records(data)
    x = np.arange(4)
    width = .32
    bars1 = ax.bar(x - width/2, fares["pooling"], width,
                   color=[PRICE[x] for x in fares["fare"]], label="Pooled rides")
    bars2 = ax.bar(x + width/2, fares["retention"], width, facecolor="white",
                   edgecolor=[PRICE[x] for x in fares["fare"]], linewidth=1.6,
                   label="Target-route retention")
    _bar_values(ax, bars1, decimals=1)
    _bar_values(ax, bars2, decimals=1)
    ax.set_xticks(x, fares["fare"])
    ax.set_ylabel("Share (%)")
    panel_title(ax, letter, "Pooling and target-route retention")
    ax.legend(loc="upper right")
    finish_axis(ax, "y")


def make_4_9(data: FigureData, output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), constrained_layout=True)
    _draw_demand_panel(axes[0], data, letter="a")
    _draw_pool_retention(axes[1], data, letter="b")
    fig.suptitle("Case A  Line 890", x=.01, ha="left", color=NAVY,
                 fontweight="bold", fontsize=11)
    save_figure(fig, output)


def make_4_10(data: FigureData, output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.2), constrained_layout=False)
    fig.subplots_adjust(left=.07, right=.985, top=.80, bottom=.24, wspace=.24)
    ride = "Car passenger"
    post_rows = [_post_mode(data.transitions, scenario, ride_label=ride) for scenario in FARES.values()]
    post_order = ["DRT", "Other PT", "Car", ride, "Active mode"]
    post_colors = {key: MODE[key] for key in post_order}
    _stacked_horizontal(axes[0], post_rows, list(FARES), post_order, colors=post_colors)
    cohort_n = int(data.transitions.loc[data.transitions["scenario"] == "A8_FM", "trips"].sum())
    panel_title(axes[0], "a", f"Post-replacement modes of {cohort_n} B0 target-route trips")

    origins: list[pd.Series] = []
    origin_labels: list[str] = []
    for fare, scenario in FARES.items():
        shares, count = _origin_mode(data.origins, scenario, ride_label=ride)
        origins.append(shares)
        origin_labels.append(f"{fare}  n={count}")
    origin_order = ["Target route", "Other PT", "Car", ride, "Active mode"]
    origin_colors = {key: MODE[key] for key in origin_order}
    _stacked_horizontal(axes[1], origins, origin_labels, origin_order, colors=origin_colors)
    panel_title(axes[1], "b", "B0 modes of DRT-containing trips")
    axes[0].set_xlabel("")
    axes[1].set_xlabel("")
    fig.supxlabel("Share of trips (%)", y=.145)
    handles = [Patch(facecolor=MODE[key], label=key) for key in
               ["DRT", "Target route", "Other PT", "Car", ride, "Active mode"]]
    fig.legend(handles=handles, ncol=6, loc="lower center", bbox_to_anchor=(.5, .035))
    fig.suptitle("Case A  Line 890", x=.01, ha="left", color=NAVY,
                 fontweight="bold", fontsize=11)
    save_figure(fig, output)


def _person_journey(data: FigureData, scenario: str) -> tuple[pd.DataFrame, float]:
    persons = data.target_persons(scenario)[["person_id", "delta_score"]]
    trips = data.target_trips(scenario)
    summary = trips.groupby("person_id", observed=True).agg(
        mean_journey=("delta_journey_sec", lambda x: pd.to_numeric(x, errors="coerce").mean() / 60),
        used_drt=("scenario_drt_trip", "max"),
    ).reset_index()
    merged = persons.merge(summary, on="person_id", how="inner").dropna(subset=["mean_journey", "delta_score"])
    faster_share = float(np.mean(pd.to_numeric(trips["delta_journey_sec"], errors="coerce") < 0))
    return merged, faster_share


def _regression_line(ax: plt.Axes, x: np.ndarray, y: np.ndarray, *, color: str = TEXT) -> float:
    good = np.isfinite(x) & np.isfinite(y)
    x, y = x[good], y[good]
    if len(x) < 2 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    slope, intercept = np.polyfit(x, y, 1)
    grid = np.linspace(x.min(), x.max(), 100)
    ax.plot(grid, slope * grid + intercept, color=color, lw=1.1, alpha=.8)
    return float(np.corrcoef(x, y)[0, 1])


def make_4_11(data: FigureData, output: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.3), sharex=True, sharey=True, constrained_layout=True)
    for ax, ((fare, scenario), letter) in zip(axes.flat, zip(FARES.items(), "abcd")):
        frame, faster = _person_journey(data, scenario)
        no = frame[~bool_series(frame["used_drt"])]
        yes = frame[bool_series(frame["used_drt"])]
        ax.scatter(no["mean_journey"], no["delta_score"], s=18, color="#777777", alpha=.55,
                   label="No DRT on paired journey")
        ax.scatter(yes["mean_journey"], yes["delta_score"], s=28, marker="^", color="#777777",
                   alpha=.62, label="Used DRT on paired journey")
        ax.axhline(0, color=TEXT, ls=(0, (3, 3)), lw=.8)
        ax.axvline(0, color=TEXT, ls=(0, (3, 3)), lw=.8)
        r = _regression_line(ax, frame["mean_journey"].to_numpy(float), frame["delta_score"].to_numpy(float))
        quadrant = int(((frame["mean_journey"] < 0) & (frame["delta_score"] < 0)).sum())
        panel_title(ax, letter, fare)
        ax.text(.02, .96,
                f"Paired trips faster {100*faster:.1f}%\nPearson r {r:.2f}\n"
                f"Faster journey and lower utility {quadrant}/{len(frame)}",
                transform=ax.transAxes, ha="left", va="top", fontsize=7.8)
        finish_axis(ax, "both")
    axes[1, 0].set_xlabel("Mean paired target-route journey-time change (min)")
    axes[1, 1].set_xlabel("Mean paired target-route journey-time change (min)")
    axes[0, 0].set_ylabel("Whole-day same-agent utility change")
    axes[1, 0].set_ylabel("Whole-day same-agent utility change")
    axes[0, 0].legend(loc="lower left", fontsize=7.4)
    fig.suptitle("Case A  Line 890", x=.01, ha="left", color=NAVY,
                 fontweight="bold", fontsize=11)
    save_figure(fig, output)


def make_4_12(data: FigureData, output: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 8), sharey=True, constrained_layout=True)
    group_order = ("low", "middle", "high")
    for col, ((scenario, case), letters) in enumerate(zip(list(STRUCTURAL.items())[:2], (("a", "c"), ("b", "d")))):
        people = data.target_persons(scenario)
        income = people[(people["income"] > 0) & people["income"].notna() & people["delta_score"].notna()].copy()
        ax = axes[0, col]
        ax.scatter(income["income"], income["delta_score"], color=CASE[case], s=17, alpha=.55)
        ax.axhline(0, color=TEXT, ls=(0, (3, 3)), lw=.8)
        r = _regression_line(ax, income["income"].to_numpy(float), income["delta_score"].to_numpy(float), color=CASE[case])
        ax.set_title(
            f"Case {case}  Line {CASE_LINE[case]}\n\n{letters[0]}  Monthly income and same-agent utility",
            loc="left", fontweight="bold", pad=8,
        )
        ax.set_xlabel("Monthly income attribute")
        if col == 0:
            ax.set_ylabel("Same-agent utility change")
        ax.text(.02, .96, f"Pearson r = {r:.2f}\nn = {len(income):,}", transform=ax.transAxes,
                ha="left", va="top", fontsize=8.0)
        finish_axis(ax, "both")

        ax = axes[1, col]
        groups = [finite(income.loc[income["income_group"].astype(str).str.lower() == group, "delta_score"])
                  for group in group_order]
        _violin_box(ax, groups, [CASE[case]] * 3, jitter=True, width=.72)
        ax.axhline(0, color=TEXT, ls=(0, (3, 3)), lw=.8)
        ax.set_xticks(np.arange(1, 4),
                      [f"{g.title()}\nn = {len(v)}" for g, v in zip(group_order, groups)])
        panel_title(ax, letters[1], "Same-agent utility by income group")
        if col == 0:
            ax.set_ylabel("Same-agent utility change")
        finish_axis(ax, "y")
    save_figure(fig, output)


def _draw_origins_ab(
    ax: plt.Axes,
    data: FigureData,
    *,
    ride_label: str,
    letter: str | None = None,
    title: str | None = None,
) -> None:
    scenarios = ("A8_FM", "B6_PTI")
    rows: list[pd.Series] = []
    labels: list[str] = []
    for scenario, case in zip(scenarios, "AB"):
        shares, count = _origin_mode(data.origins, scenario, ride_label=ride_label)
        rows.append(shares)
        labels.append(f"{CASE_LABEL[case]}\n n = {count}")
    order = ["Target route", "Other PT", "Car", ride_label, "Active mode"]
    colors = {key: MODE[key] for key in order}
    _stacked_horizontal(ax, rows, labels, order, colors=colors, threshold=3.8)
    ax.set_xlabel("Share of DRT-containing trips (%)")
    if letter and title:
        panel_title(ax, letter, title)


def make_4_13(data: FigureData, output: Path) -> None:
    fig, ax = plt.subplots(figsize=(12.5, 4.0), constrained_layout=True)
    _draw_origins_ab(ax, data, ride_label="Ride or other")
    order = ["Target route", "Other PT", "Car", "Ride or other", "Active mode"]
    ax.legend(handles=[Patch(facecolor=MODE[x], label=x) for x in order], ncol=5,
              loc="upper center", bbox_to_anchor=(.5, -.20))
    save_figure(fig, output)


def _wait_summary(data: FigureData, scenario: str) -> dict[str, float]:
    trips = data.target_trips(scenario)
    b0 = finite(trips["b0_wait_sec"] / 60)
    rep = finite(trips["scenario_wait_sec"] / 60)

    def gini(values: np.ndarray) -> float:
        x = np.sort(values[np.isfinite(values)])
        if len(x) == 0 or np.sum(x) == 0:
            return float("nan")
        index = np.arange(1, len(x) + 1)
        return float((2 * np.sum(index * x) / (len(x) * np.sum(x))) - (len(x) + 1) / len(x))

    def cv(values: np.ndarray) -> float:
        return float(np.std(values, ddof=1) / np.mean(values)) if len(values) > 1 and np.mean(values) else float("nan")

    return {
        "b0_mean": float(np.mean(b0)), "rep_mean": float(np.mean(rep)),
        "b0_p95": percentile(b0, 95), "rep_p95": percentile(rep, 95),
        "b0_gini": gini(b0), "rep_gini": gini(rep),
        "b0_cv": cv(b0), "rep_cv": cv(rep),
    }


def _draw_wait_bars(ax: plt.Axes, data: FigureData, *, letter: str = "c", title: str = "Mean and upper-tail waiting") -> None:
    a = _wait_summary(data, "A8_FM")
    b = _wait_summary(data, "B6_PTI")
    labels = ["A mean", "A P95", "B mean", "B P95"]
    b0_values = [a["b0_mean"], a["b0_p95"], b["b0_mean"], b["b0_p95"]]
    rep_values = [a["rep_mean"], a["rep_p95"], b["rep_mean"], b["rep_p95"]]
    x = np.arange(4)
    width = .34
    bars0 = ax.bar(x - width/2, b0_values, width, color=B0, label="B0")
    colors = [CASE["A"], CASE["A"], CASE["B"], CASE["B"]]
    bars1 = ax.bar(x + width/2, rep_values, width, color=colors, label="Replacement")
    _bar_values(ax, bars0, decimals=1)
    _bar_values(ax, bars1, decimals=1)
    ax.set_xticks(x, labels)
    ax.set_ylabel("Minutes")
    panel_title(ax, letter, title)
    finish_axis(ax, "y")


def _draw_dispersion(ax: plt.Axes, data: FigureData, *, letter: str = "d", title: str = "Relative dispersion") -> None:
    a = _wait_summary(data, "A8_FM")
    b = _wait_summary(data, "B6_PTI")
    labels = ["A Gini", "A CV", "B Gini", "B CV"]
    b0_values = [a["b0_gini"], a["b0_cv"], b["b0_gini"], b["b0_cv"]]
    rep_values = [a["rep_gini"], a["rep_cv"], b["rep_gini"], b["rep_cv"]]
    x = np.arange(4)
    width = .34
    bars0 = ax.bar(x - width/2, b0_values, width, color=B0, label="B0")
    colors = [CASE["A"], CASE["A"], CASE["B"], CASE["B"]]
    bars1 = ax.bar(x + width/2, rep_values, width, color=colors, label="Replacement")
    _bar_values(ax, bars0, decimals=2)
    _bar_values(ax, bars1, decimals=2)
    ax.set_xticks(x, labels)
    ax.set_ylabel("Dispersion measure")
    panel_title(ax, letter, title)
    finish_axis(ax, "y")


def make_4_14(data: FigureData, output: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12.8, 7.8), constrained_layout=True)
    for ax, scenario, case, letter in zip(axes[0], ("A8_FM", "B6_PTI"), "AB", "ab"):
        trips = data.target_trips(scenario)
        ecdf(ax, trips["b0_wait_sec"] / 60, label="B0", color=B0, linestyle=(0, (4, 3)))
        ecdf(ax, trips["scenario_wait_sec"] / 60, label=SCENARIO_DISPLAY[scenario],
             color=CASE[case], linestyle="-")
        ax.set_xlim(0, 70)
        ax.set_ylim(0, 1.02)
        ax.set_xlabel("Paired-journey waiting time in minutes")
        ax.set_ylabel("Cumulative share")
        panel_title(ax, letter, "Paired-journey waiting")
        ax.legend(loc="lower right")
        finish_axis(ax, "both")
        ax.text(0, 1.13, f"Case {case}  Line {CASE_LINE[case]}", transform=ax.transAxes,
                color=NAVY, fontweight="bold", fontsize=10.5, ha="left", va="bottom")
    _draw_wait_bars(axes[1, 0], data)
    _draw_dispersion(axes[1, 1], data)
    handles = [Patch(facecolor=B0, label="B0"), Patch(facecolor=CASE["A"], label="A8-FM"),
               Patch(facecolor=CASE["B"], label="B6-PTI")]
    fig.legend(handles=handles, ncol=3, loc="lower center", bbox_to_anchor=(.5, -.02))
    save_figure(fig, output)


def make_5_1(data: FigureData, output: Path) -> None:
    fig = plt.figure(figsize=(13.8, 9.8), constrained_layout=True)
    outer = fig.add_gridspec(2, 2, width_ratios=[1.08, 1], height_ratios=[1, 1.05])
    base = _case_rows(data.baseline)
    cases = list("ABC")

    # a. Three baseline descriptors.
    gs_a = outer[0, 0].subgridspec(1, 3)
    baseline_specs = (
        ("Boardings per\ndeparture", base["boardings"] / base["departures"], 2, ""),
        ("Distance-weighted\noccupancy", base["bus_distance_weighted_occupancy"], 2, ""),
        ("Empty bus VKT", 100 * base["bus_empty_vkt_share"], 1, "%"),
    )
    for idx, (title, values, decimals, suffix) in enumerate(baseline_specs):
        ax = fig.add_subplot(gs_a[0, idx])
        y = np.arange(3)[::-1]
        bars = ax.barh(y, values, color=[CASE[c] for c in cases], height=.48)
        ax.set_yticks(y, [CASE_LABEL[c] for c in cases] if idx == 0 else [])
        ax.set_title(title, loc="left", fontsize=9.0, fontweight="bold", pad=6)
        if idx == 0:
            ax.text(0, 1.16, "a  Baseline demand and fixed-route utilisation",
                    transform=ax.transAxes, fontweight="bold", fontsize=10.4, ha="left")
        ax.set_xlim(0, max(values) * 1.18)
        _hbar_values(ax, bars, decimals=decimals, suffix=suffix)
        finish_axis(ax, "x")

    # b. Passenger outcomes.
    rq1 = _case_rows(data.rq1)
    gs_b = outer[0, 1].subgridspec(1, 2)
    passenger_specs = (
        ("Affected travellers with\nlower same-agent utility", 100 * rq1["target_riders::share_worse"],
         "Share of affected travellers (%)"),
        ("Paired target-route\njourneys faster", 100 * rq1["target_trips::share_journey_time_improved"],
         "Share of paired journeys (%)"),
    )
    for idx, (title, values, xlabel) in enumerate(passenger_specs):
        ax = fig.add_subplot(gs_b[0, idx])
        y = np.arange(3)[::-1]
        bars = ax.barh(y, values, color=[CASE[c] for c in cases], height=.48)
        ax.set_yticks(y, [CASE_LABEL[c] for c in cases] if idx == 0 else [])
        ax.set_title(title, loc="left", fontsize=9.0, fontweight="bold", pad=6)
        if idx == 0:
            ax.text(0, 1.16, "b  Passenger outcomes", transform=ax.transAxes,
                    fontweight="bold", fontsize=10.4, ha="left")
        ax.set_xlim(0, 100)
        ax.set_xlabel(xlabel, fontsize=8.0)
        _hbar_values(ax, bars, decimals=1, suffix="%")
        finish_axis(ax, "x")

    # c. Structural adaptation.
    ax = fig.add_subplot(outer[1, 0])
    post = [_post_mode(data.transitions, s) for s in STRUCTURAL]
    _stacked_horizontal(ax, post, [CASE_LABEL[c] for c in cases], list(MODE_ORDER),
                        colors={key: MODE[key] for key in MODE_ORDER})
    ax.set_xlabel("Share of B0 target-route trips (%)")
    panel_title(ax, "c", "Post-replacement modes of B0 target-route trips")
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(.5, -.17), fontsize=7.4)

    # d. Resource outcomes.
    gs_d = outer[1, 1].subgridspec(1, 2)
    resource_specs = (
        ("Service-level vehicle\nmovement",
         100 * rq1["resource::DRT_VKT_to_removed_bus_VKT_ratio"],
         "DRT VKT relative to removed-service VKT (%)", 125, True),
        ("Pooled rides", [100 * data.kpi(s).pooling for s in STRUCTURAL],
         "Share of served requests (%)", 100, False),
    )
    for idx, (title, values, xlabel, xmax, parity) in enumerate(resource_specs):
        ax = fig.add_subplot(gs_d[0, idx])
        y = np.arange(3)[::-1]
        bars = ax.barh(y, values, color=[CASE[c] for c in cases], height=.48)
        ax.set_yticks(y, [CASE_LABEL[c] for c in cases] if idx == 0 else [])
        ax.set_title(title, loc="left", fontsize=9.0, fontweight="bold", pad=6)
        if idx == 0:
            ax.text(0, 1.16, "d  Vehicle-resource outcomes", transform=ax.transAxes,
                    fontweight="bold", fontsize=10.4, ha="left")
        if parity:
            ax.axvline(100, color="#7A8086", ls=(0, (3, 3)), lw=.9)
        ax.set_xlim(0, xmax)
        ax.set_xlabel(xlabel, fontsize=7.8)
        _hbar_values(ax, bars, decimals=1, suffix="%")
        finish_axis(ax, "x")
    save_figure(fig, output)


def _draw_fleet_metric(
    ax: plt.Axes,
    fleet: pd.DataFrame,
    *,
    metric: str,
    letter: str,
    title: str,
    ylabel: str,
) -> None:
    for fare, marker in (("FL", "o"), ("FH", "s")):
        selected = fleet[fleet["fare"] == fare].sort_values("fleet")
        _annotated_line(ax, selected["fleet"].to_numpy(), selected[metric].to_numpy(float),
                        color=PRICE[fare], label=fare, marker=marker)
    ax.set_xticks([4, 8, 12])
    ax.set_xlabel("Fleet size")
    ax.set_ylabel(ylabel)
    panel_title(ax, letter, title)
    ax.margins(y=.15)
    finish_axis(ax, "y")


def make_5_2(data: FigureData, output: Path) -> None:
    fleet = _fleet_records(data)
    fig, axes = plt.subplots(2, 3, figsize=(14.5, 8.8), constrained_layout=True)

    ax = axes[0, 0]
    for fare, marker in (("FL", "o"), ("FH", "s")):
        selected = fleet[fleet["fare"] == fare].sort_values("fleet")
        _annotated_line(ax, selected["fleet"].to_numpy(), selected["wait_mean"].to_numpy(float),
                        color=PRICE[fare], label=fare, marker=marker)
        _annotated_line(ax, selected["fleet"].to_numpy(), selected["wait_p95"].to_numpy(float),
                        color=PRICE[fare], marker=marker, linestyle=(0, (4, 3)))
    ax.set_xticks([4, 8, 12])
    ax.set_xlabel("Fleet size")
    ax.set_ylabel("Minutes")
    panel_title(ax, "a", "Request waiting")
    ax.margins(y=.15)
    ax.legend(loc="lower left", ncol=2, fontsize=7.0)
    finish_axis(ax, "y")

    _draw_fleet_metric(axes[0, 1], fleet, metric="min_idle", letter="b",
                       title="Minimum idle fleet", ylabel="Vehicles")
    _draw_fleet_metric(axes[0, 2], fleet, metric="vkt_per_request", letter="c",
                       title="VKT per served request", ylabel="Kilometres")
    _draw_demand_panel(axes[1, 0], data, letter="d")
    axes[1, 0].set_xlabel("Fare condition")
    _draw_pool_retention(axes[1, 1], data, letter="e")
    axes[1, 1].set_xlabel("Fare condition")

    ax = axes[1, 2]
    ride = "Car passenger"
    rows, labels = [], []
    for fare, scenario in FARES.items():
        shares, count = _origin_mode(data.origins, scenario, ride_label=ride)
        rows.append(shares)
        labels.append(f"{fare}  n={count}")
    order = ["Target route", "Other PT", "Car", ride, "Active mode"]
    _stacked_horizontal(ax, rows, labels, order, colors={key: MODE[key] for key in order})
    panel_title(ax, "f", "B0 origins of DRT-containing trips")
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(.5, -.19), fontsize=6.7)
    save_figure(fig, output)


def _draw_exposure_income(ax: plt.Axes, data: FigureData) -> None:
    rq1 = data.rq1.set_index("scenario")
    categories = ("Population-\nwide", "Affected\ncohort", "Low\nincome", "Middle\nincome", "High\nincome")
    values: dict[str, list[float]] = {"A": [], "B": []}
    for scenario, case in (("A8_FM", "A"), ("B6_PTI", "B")):
        people = data.target_persons(scenario)
        groups = people.groupby(people["income_group"].astype(str).str.lower(), observed=True)["delta_score"].mean()
        values[case] = [
            float(rq1.loc[scenario, "all_agents::mean_delta_score"]),
            float(rq1.loc[scenario, "target_riders::mean_delta_score"]),
            float(groups.get("low", np.nan)), float(groups.get("middle", np.nan)),
            float(groups.get("high", np.nan)),
        ]
    x = np.arange(len(categories))
    width = .34
    bars_a = ax.bar(x - width/2, values["A"], width, color=CASE["A"], label="Case A  Line 890")
    bars_b = ax.bar(x + width/2, values["B"], width, color=CASE["B"], label="Case B  Line 435")
    ax.axhline(0, color=TEXT, ls=(0, (3, 3)), lw=.8)
    ax.axvline(1.5, color=GRID, ls=(0, (3, 3)), lw=.9)
    ax.set_xticks(x, categories)
    ax.set_ylabel("Mean same-agent utility change")
    panel_title(ax, "a", "Exposure and income-group utility")
    ax.legend(loc="lower right", fontsize=7.6)
    finish_axis(ax, "y")
    for bars in (bars_a, bars_b):
        for bar in bars:
            value = bar.get_height()
            ax.text(bar.get_x()+bar.get_width()/2, value + (.22 if value >= 0 else -.22),
                    f"{value:.2f}", ha="center", va="bottom" if value >= 0 else "top", fontsize=7.6)


def make_5_3(data: FigureData, output: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 7.8), constrained_layout=True)
    _draw_exposure_income(axes[0, 0], data)
    _draw_origins_ab(axes[0, 1], data, ride_label="Car passenger", letter="b",
                     title="B0 origins of DRT-containing trips")
    order = ["Target route", "Other PT", "Car", "Car passenger", "Active mode"]
    axes[0, 1].legend(handles=[Patch(facecolor=MODE[x], label=x) for x in order],
                      ncol=5, loc="upper center", bbox_to_anchor=(.5, -.16), fontsize=6.7)
    _draw_wait_bars(axes[1, 0], data, letter="c", title="Mean and upper-tail waiting")
    _draw_dispersion(axes[1, 1], data, letter="d", title="Relative waiting dispersion")
    handles = [Patch(facecolor=B0, label="B0"), Patch(facecolor=CASE["A"], label="A8-FM"),
               Patch(facecolor=CASE["B"], label="B6-PTI")]
    axes[1, 0].legend(handles=handles, ncol=3, loc="upper left", fontsize=7.5)
    save_figure(fig, output)


FIGURE_FUNCTIONS: dict[str, Callable[[FigureData, Path], None]] = {
    "4.1": make_4_1, "4.2": make_4_2, "4.3": make_4_3, "4.4": make_4_4,
    "4.5": make_4_5, "4.6": make_4_6, "4.7": make_4_7, "4.8": make_4_8,
    "4.9": make_4_9, "4.10": make_4_10, "4.11": make_4_11,
    "4.12": make_4_12, "4.13": make_4_13, "4.14": make_4_14,
    "5.1": make_5_1, "5.2": make_5_2, "5.3": make_5_3,
}


def parse_figures(value: str) -> list[str]:
    if value.strip().lower() == "all":
        return list(FIGURE_FUNCTIONS)
    requested = [part.strip() for part in value.split(",") if part.strip()]
    unknown = [item for item in requested if item not in FIGURE_FUNCTIONS]
    if unknown:
        valid = ", ".join(FIGURE_FUNCTIONS)
        raise argparse.ArgumentTypeError(
            f"Unknown figure(s): {', '.join(unknown)}. Valid identifiers: {valid}, or all"
        )
    if not requested:
        raise argparse.ArgumentTypeError("--figures must not be empty")
    return requested


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--analysis-source", required=True,
        help="Extracted analysis_results directory or ABC_analysis_results_01_04.tar.gz",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for generated PNG files")
    parser.add_argument(
        "--figures", default="all",
        help="all, or a comma-separated list such as 4.1,4.2,5.1",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        requested = parse_figures(args.figures)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    with AnalysisStore(args.analysis_source) as store:
        data = FigureData(store)
        for identifier in requested:
            output = output_dir / OUTPUT_NAMES[identifier]
            print(f"Generating Figure {identifier}: {output.name}", flush=True)
            FIGURE_FUNCTIONS[identifier](data, output)
    print(f"Generated {len(requested)} figure(s) in {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
