"""Shared visual language for the dissertation figures."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import PercentFormatter

CASE = {"A": "#1FA7A6", "B": "#8B7FD6", "C": "#FF8A5B"}
PRICE = {"FM": "#1FA7A6", "SUB1": "#F6C587", "FL": "#6C2E7B", "FH": "#E75480"}
MODE = {
    "DRT": "#1FA7A6",
    "Target route": "#6C2E7B",
    "Other PT": "#0D3B66",
    "Car": "#FF8A5B",
    "Ride or other": "#8B7FD6",
    "Car passenger": "#8B7FD6",
    "Active mode": "#3B4044",
}
B0 = "#3B4044"
TEXT = "#3B4044"
NAVY = "#0D3B66"
GRID = "#E5E8EB"


def apply_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.5,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.labelsize": 9.5,
            "xtick.labelsize": 8.7,
            "ytick.labelsize": 8.7,
            "text.color": TEXT,
            "axes.labelcolor": TEXT,
            "xtick.color": TEXT,
            "ytick.color": TEXT,
            "axes.edgecolor": "#9AA0A6",
            "axes.linewidth": 0.7,
            "axes.grid": False,
            "grid.color": GRID,
            "grid.linewidth": 0.65,
            "legend.frameon": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def finish_axis(ax: plt.Axes, grid: str | None = "y") -> None:
    ax.spines[["top", "right"]].set_visible(False)
    if grid:
        ax.grid(True, axis=grid, zorder=0)
    ax.set_axisbelow(True)


def panel_title(ax: plt.Axes, letter: str, title: str) -> None:
    ax.set_title(f"{letter}  {title}", loc="left", fontweight="bold", pad=8)


def case_header(fig: plt.Figure, text: str, y: float = 0.995) -> None:
    fig.text(0.01, y, text, color=NAVY, weight="bold", size=11, va="top")


def annotate_bars(
    ax: plt.Axes,
    bars,
    fmt: str = ".1f",
    suffix: str = "",
    horizontal: bool = False,
    pad_fraction: float = 0.015,
) -> None:
    if horizontal:
        span = np.diff(ax.get_xlim())[0] or 1
        for bar in bars:
            value = bar.get_width()
            ax.text(
                value + np.sign(value or 1) * span * pad_fraction,
                bar.get_y() + bar.get_height() / 2,
                f"{value:{fmt}}{suffix}",
                ha="left" if value >= 0 else "right",
                va="center",
                fontsize=8.5,
            )
    else:
        span = np.diff(ax.get_ylim())[0] or 1
        for bar in bars:
            value = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value + np.sign(value or 1) * span * pad_fraction,
                f"{value:{fmt}}{suffix}",
                ha="center",
                va="bottom" if value >= 0 else "top",
                fontsize=8.5,
            )


def ecdf(ax: plt.Axes, values, *, label: str, color: str, linestyle: str = "-") -> None:
    clean = np.asarray(values, dtype=float)
    clean = np.sort(clean[np.isfinite(clean)])
    if clean.size == 0:
        return
    y = np.arange(1, clean.size + 1) / clean.size
    ax.step(clean, y, where="post", label=label, color=color, lw=1.8, ls=linestyle)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))


def save_figure(fig: plt.Figure, output: str | Path, *, dpi: int = 300) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    return path


apply_style()
