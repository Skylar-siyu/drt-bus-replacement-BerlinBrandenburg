#!/usr/bin/env python3
"""Create Figure B.5: residential-cell utility variation in Cases A and B.

Inputs
------
* ``ABC_analysis_results_01_04.tar.gz`` (or the extracted
  ``RQ3_spatial_person_impacts.csv.gz``);
* the three frozen service-area shapefiles in ``spatial/``;
* the MATSim baseline transit schedule and network; and
* the Geofabrik Brandenburg (mit Berlin) free-shapefile extract.

The mapped sample contains baseline target-line riders whose home coordinate is
inside the frozen service-area polygon or its 1.8 km focus buffer. Their
``delta_score`` values are aggregated to a globally aligned grid of regular
1 km² flat-top hexagons in EPSG:25832.
"""

from __future__ import annotations

import argparse
import gzip
import math
import tarfile
import tempfile
from pathlib import Path

import geopandas as gpd
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon as MplPolygon
from shapely.geometry import Polygon

if __package__:  # e.g. ``python -m analysis.figures.maps.make_figure_B5``.
    from . import make_figure_3_1 as map31
else:  # Direct script execution from any working directory.
    import make_figure_3_1 as map31


CRS = "EPSG:25832"
FOCUS_BUFFER_M = 1_800.0
HEX_AREA_M2 = 1_000_000.0
HEX_SIDE_M = math.sqrt(2.0 * HEX_AREA_M2 / (3.0 * math.sqrt(3.0)))
HEX_DX = 1.5 * HEX_SIDE_M
HEX_DY = math.sqrt(3.0) * HEX_SIDE_M
VMIN, VMAX = -25.0, 5.0
LOCAL_WIDTH_M = 18_000.0
LOCAL_HEIGHT_M = 22_000.0

UTILITY_CMAP = LinearSegmentedColormap.from_list(
    "same_agent_utility",
    ["#B6533E", "#D9826E", "#F0BDAE", "#F3EEE9", "#A9D6C4"],
)
NORM = Normalize(VMIN, VMAX, clip=True)
NAVY = "#003B64"

CASES = {
    "A": {"scenario": "A8_FM", "line": "890", "expected_n": 45, "letter": "a"},
    "B": {"scenario": "B6_PTI", "line": "435", "expected_n": 30, "letter": "b"},
}

ANALYSIS_MEMBER = "analysis_results/04_RQ_outputs/RQ3_spatial_person_impacts.csv.gz"
ANALYSIS_COLUMNS = [
    "scenario", "delta_score", "baseline_target_line_rider", "home_x", "home_y",
]


def parse_boolean(series: pd.Series, column: str) -> pd.Series:
    """Parse CSV Boolean values without treating the string ``False`` as true."""
    normalized = series.astype("string").str.strip().str.lower()
    values = {
        "true": True, "t": True, "1": True, "yes": True, "y": True,
        "false": False, "f": False, "0": False, "no": False, "n": False,
        "": False,
    }
    unknown = series.notna() & ~normalized.isin(values)
    if unknown.any():
        examples = sorted(normalized[unknown].dropna().unique().tolist())[:5]
        raise ValueError(f"Unrecognised Boolean values in {column}: {examples}")
    return normalized.map(values).fillna(False).astype(bool)


def load_analysis_rows(source: Path, scenarios: set[str]) -> pd.DataFrame:
    """Read the full analysis archive or a GitHub-sized filtered CSV.GZ."""

    def collect(reader) -> pd.DataFrame:
        pieces = []
        for chunk in reader:
            keep = (
                chunk["scenario"].isin(scenarios)
                & parse_boolean(
                    chunk["baseline_target_line_rider"], "baseline_target_line_rider"
                )
            )
            if keep.any():
                pieces.append(chunk.loc[keep].copy())
        if not pieces:
            raise RuntimeError(f"No baseline target-line riders found for {sorted(scenarios)}")
        return pd.concat(pieces, ignore_index=True)

    if tarfile.is_tarfile(source):
        with tarfile.open(source, "r:*") as archive:
            try:
                member = archive.getmember(ANALYSIS_MEMBER)
            except KeyError as exc:
                raise FileNotFoundError(f"{ANALYSIS_MEMBER} is not present in {source}") from exc
            raw = archive.extractfile(member)
            if raw is None:
                raise FileNotFoundError(f"Could not read {ANALYSIS_MEMBER} from {source}")
            with gzip.GzipFile(fileobj=raw) as stream:
                reader = pd.read_csv(
                    stream, usecols=ANALYSIS_COLUMNS, chunksize=500_000,
                    dtype={"scenario": "string"},
                )
                return collect(reader)

    reader = pd.read_csv(
        source, compression="infer", usecols=ANALYSIS_COLUMNS, chunksize=500_000,
        dtype={"scenario": "string"},
    )
    return collect(reader)


def select_case(data: pd.DataFrame, scenario: str, service_polygon) -> gpd.GeoDataFrame:
    selected = data[data["scenario"] == scenario].copy()
    selected["home_x"] = pd.to_numeric(selected["home_x"], errors="coerce")
    selected["home_y"] = pd.to_numeric(selected["home_y"], errors="coerce")
    selected["delta_score"] = pd.to_numeric(selected["delta_score"], errors="coerce")
    selected = selected.dropna(subset=["home_x", "home_y", "delta_score"])
    selected = gpd.GeoDataFrame(
        selected,
        geometry=gpd.points_from_xy(selected["home_x"], selected["home_y"]),
        crs=CRS,
    )
    focus = service_polygon.buffer(FOCUS_BUFFER_M)
    return selected[selected.geometry.apply(focus.covers)].copy()


def hex_polygon(cx: float, cy: float) -> Polygon:
    # Neighbouring columns are 1.5*s apart and alternate columns are shifted
    # vertically by sqrt(3)*s/2, so adjacent cells share complete edges.
    return Polygon([
        (cx + HEX_SIDE_M * math.cos(k * math.pi / 3.0),
         cy + HEX_SIDE_M * math.sin(k * math.pi / 3.0))
        for k in range(6)
    ])


def aggregate_hexagons(data: gpd.GeoDataFrame):
    points = list(data.geometry)
    if not points:
        return []

    minx = min(p.x for p in points) - HEX_SIDE_M
    maxx = max(p.x for p in points) + HEX_SIDE_M
    miny = min(p.y for p in points) - HEX_SIDE_M
    maxy = max(p.y for p in points) + HEX_SIDE_M
    q0 = math.floor(minx / HEX_DX) - 1
    q1 = math.ceil(maxx / HEX_DX) + 1

    grid = []
    for q in range(q0, q1 + 1):
        cx = q * HEX_DX
        offset = 0.5 * HEX_DY if q % 2 else 0.0
        r0 = math.floor((miny - offset) / HEX_DY) - 1
        r1 = math.ceil((maxy - offset) / HEX_DY) + 1
        for r in range(r0, r1 + 1):
            cy = r * HEX_DY + offset
            grid.append((q, r, cx, cy, hex_polygon(cx, cy)))

    buckets: dict[tuple[int, int], list[float]] = {}
    for point, delta in zip(points, data["delta_score"].to_numpy(float)):
        for q, r, _, _, cell in grid:
            if cell.covers(point):
                buckets.setdefault((q, r), []).append(float(delta))
                break
        else:
            raise RuntimeError(f"No hexagon found for residential point {point.wkt}")

    geometry = {(q, r): (cx, cy, cell) for q, r, cx, cy, cell in grid}
    return [
        {
            "cx": geometry[key][0], "cy": geometry[key][1],
            "polygon": geometry[key][2], "n": len(values),
            "mean": float(np.mean(values)),
        }
        for key, values in sorted(buckets.items())
    ]


def local_extent(service_polygon):
    centre = service_polygon.centroid
    return (
        centre.x - LOCAL_WIDTH_M / 2, centre.x + LOCAL_WIDTH_M / 2,
        centre.y - LOCAL_HEIGHT_M / 2, centre.y + LOCAL_HEIGHT_M / 2,
    )


def draw_hexagons(ax, cells):
    for cell in cells:
        vertices = np.asarray(cell["polygon"].exterior.coords[:-1])
        ax.add_patch(MplPolygon(
            vertices, closed=True, facecolor=UTILITY_CMAP(NORM(cell["mean"])),
            edgecolor="white", linewidth=2.1, alpha=0.96, zorder=10,
        ))
        colour = "white" if cell["mean"] <= -17 else "#273238"
        ax.text(
            cell["cx"], cell["cy"], str(cell["n"]),
            ha="center", va="center", fontsize=11, fontweight="bold",
            color=colour, zorder=14,
        )


def draw_case_overlay(ax, case, service, route, stops):
    service.boundary.plot(
        ax=ax, color="#222222", linewidth=1.35,
        linestyle=(0, (4, 3)), zorder=11,
    )
    gpd.GeoSeries([route], crs=CRS).plot(
        ax=ax, color=map31.ROUTE_COLOUR, linewidth=2.0, zorder=12,
    )
    sx, sy = zip(*stops)
    ax.scatter(
        sx, sy, s=22, facecolor="white", edgecolor=map31.ROUTE_COLOUR,
        linewidth=1.3, zorder=13,
    )
    hx, hy = zip(*map31.RAIL_HUBS[case])
    ax.scatter(
        hx, hy, s=54, marker="D", c=map31.HUB_COLOUR,
        edgecolor="white", linewidth=0.9, zorder=15,
    )


def style_map(ax, extent):
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#9DA7AB")
        spine.set_linewidth(0.8)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-source", type=Path, required=True,
                        help=("Analysis tar.gz, extracted RQ3_spatial_person_impacts.csv.gz, "
                              "or filtered spatial_target_riders.csv.gz"))
    parser.add_argument("--spatial-context", type=Path,
                        default=map31.REPO_ROOT / "spatial",
                        help="Repository spatial directory or spatial_context.zip")
    parser.add_argument("--osm-dir", type=Path, required=True,
                        help="Extracted Geofabrik Brandenburg free-shapefile directory")
    parser.add_argument("--transit-schedule", type=Path, required=True)
    parser.add_argument("--network", type=Path, required=True)
    parser.add_argument("--output", type=Path,
                        default=(map31.REPO_ROOT / "figures" /
                                 "Figure_B5_residential_cell_utility_map.png"))
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument(
        "--no-strict", action="store_true",
        help="Warn instead of failing when mapped sample sizes differ from 45 and 30",
    )
    args = parser.parse_args()

    analysis = load_analysis_rows(args.analysis_source, {x["scenario"] for x in CASES.values()})

    with tempfile.TemporaryDirectory(prefix="figureB5_") as temp_dir:
        spatial_root = map31.prepare_spatial_context(args.spatial_context, Path(temp_dir))
        all_service = map31.read_service_areas(spatial_root)
        service = {case: all_service[case] for case in CASES}
        extents = {case: local_extent(service[case].geometry.iloc[0]) for case in CASES}
        combined_extent = (
            min(x[0] for x in extents.values()), max(x[1] for x in extents.values()),
            min(x[2] for x in extents.values()), max(x[3] for x in extents.values()),
        )
        layers = map31.read_osm_layers(args.osm_dir, combined_extent, combined_extent)
        routes = map31.parse_target_routes(args.transit_schedule)
        wanted = {link for case in CASES for link in routes[case]["link_refs"]}
        nodes, links = map31.parse_network_links(args.network, wanted)
        route_geoms = {case: map31.route_geometry(routes[case], nodes, links) for case in CASES}

        samples, cells = {}, {}
        for case, spec in CASES.items():
            polygon = service[case].geometry.iloc[0]
            samples[case] = select_case(analysis, spec["scenario"], polygon)
            if len(samples[case]) != spec["expected_n"]:
                message = (
                    f"Case {case}: n={len(samples[case])}; expected {spec['expected_n']} "
                    "for the frozen service area and 1.8 km focus buffer"
                )
                if not args.no_strict:
                    raise RuntimeError(message)
                print(f"WARNING: {message}")
            cells[case] = aggregate_hexagons(samples[case])

        fig = plt.figure(figsize=(16, 12), facecolor="white")
        axes = {
            "A": fig.add_axes([0.022, 0.305, 0.400, 0.610]),
            "B": fig.add_axes([0.510, 0.305, 0.400, 0.610]),
        }

        for case, ax in axes.items():
            extent = extents[case]
            map31.draw_basemap(ax, layers, extent, local=True)
            draw_hexagons(ax, cells[case])
            draw_case_overlay(ax, case, service[case], route_geoms[case], routes[case]["stops"])
            style_map(ax, extent)
            map31.draw_scale_bar(ax, 6)

            x0 = 0.006 if case == "A" else 0.492
            spec = CASES[case]
            fig.text(
                x0, 0.982, f"Case {case}  Line {spec['line']}",
                ha="left", va="top", fontsize=22, fontweight="bold", color=NAVY,
            )
            fig.text(
                x0 + 0.022, 0.946, f"{spec['letter']}  Local same-agent utility",
                ha="left", va="top", fontsize=18, fontweight="bold", color="#34393C",
            )
            fig.text(
                x0 + 0.365, 0.945, f"n = {len(samples[case])}",
                ha="right", va="top", fontsize=16, color="#626B70",
            )

        legend = [
            Line2D([0], [0], color="#777F82", lw=2, label="Rail network"),
            Line2D([0], [0], color="#202020", lw=2, ls=(0, (5, 4)), label="DRT service area"),
            Line2D([0], [0], color=map31.ROUTE_COLOUR, lw=3, label="Target bus route"),
            Line2D([0], [0], marker="o", color="none", markerfacecolor="white",
                   markeredgecolor=map31.ROUTE_COLOUR, markeredgewidth=1.8,
                   markersize=8, label="Bus stop"),
            Line2D([0], [0], marker="D", color="none", markerfacecolor=map31.HUB_COLOUR,
                   markeredgecolor="white", markersize=8, label="Rail hub"),
        ]
        fig.legend(
            handles=legend, loc="lower center", bbox_to_anchor=(0.5, 0.245),
            ncol=5, frameon=False, fontsize=14, handlelength=2.1,
            columnspacing=1.3, handletextpad=0.45,
        )
        fig.text(
            0.5, 0.205,
            "Numbers report affected travellers in each 1 km² residential hexagon",
            ha="center", va="center", fontsize=15, color="#626B70",
        )

        cax = fig.add_axes([0.245, 0.095, 0.410, 0.025])
        colourbar = mpl.colorbar.ColorbarBase(
            cax, cmap=UTILITY_CMAP, norm=NORM, orientation="horizontal",
            ticks=[-25, -20, -15, -10, -5, 0, 5],
        )
        colourbar.ax.tick_params(labelsize=12, colors="#4D565B")
        colourbar.outline.set_edgecolor("#8F989C")
        fig.text(
            0.45, 0.128, "Hexagon mean same-agent utility change",
            ha="center", va="bottom", fontsize=16, color="#30373A",
        )
        fig.text(
            0.5, 0.035,
            "Background © OpenStreetMap contributors (Geofabrik extract, 22 Aug 2026) · "
            "CRS: EPSG 25832",
            ha="center", va="center", fontsize=11.5, color="#7A8286",
        )

        args.output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.output, dpi=args.dpi, facecolor="white")
        plt.close(fig)
        print(
            f"Saved {args.output} | Case A n={len(samples['A'])}, "
            f"Case B n={len(samples['B'])}"
        )


if __name__ == "__main__":
    main()
