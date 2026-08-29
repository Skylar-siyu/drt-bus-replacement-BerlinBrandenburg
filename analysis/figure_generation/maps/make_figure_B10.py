#!/usr/bin/env python3
"""Create Figure B.10: residential-cell utility variation in Case C.

The figure uses scenario C22_PTI from the RQ3 spatial person-level output. The
sample is restricted to baseline target-line riders whose homes fall inside
the frozen Case C service area or its 1.8 km focus buffer. Utility change is
aggregated to the same 1 km² EPSG:25832 hexagon grid used by Figure B.5.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

if __package__:  # Package imports.
    from . import make_figure_3_1 as map31
    from . import make_figure_B5 as figure_b5
else:  # Direct script execution from any working directory.
    import make_figure_3_1 as map31
    import make_figure_B5 as figure_b5


CRS = "EPSG:25832"
SCENARIO = "C22_PTI"
EXPECTED_N = 681
MAP_EXTENT = (775_750.0, 793_750.0, 5_823_500.0, 5_845_500.0)


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
                                 "Figure_B10_residential_cell_utility_case_C.png"))
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument(
        "--no-strict", action="store_true",
        help="Warn instead of failing when the mapped sample size differs from 681",
    )
    args = parser.parse_args()

    analysis = figure_b5.load_analysis_rows(args.analysis_source, {SCENARIO})

    with tempfile.TemporaryDirectory(prefix="figureB10_") as temp_dir:
        spatial_root = map31.prepare_spatial_context(args.spatial_context, Path(temp_dir))
        service = map31.read_service_areas(spatial_root)["C"]
        service_polygon = service.geometry.iloc[0]
        sample = figure_b5.select_case(analysis, SCENARIO, service_polygon)
        if len(sample) != EXPECTED_N:
            message = (
                f"Case C: n={len(sample)}; expected {EXPECTED_N} for the frozen "
                "service area and 1.8 km focus buffer"
            )
            if not args.no_strict:
                raise RuntimeError(message)
            print(f"WARNING: {message}")
        cells = figure_b5.aggregate_hexagons(sample)

        layers = map31.read_osm_layers(args.osm_dir, MAP_EXTENT, MAP_EXTENT)
        routes = map31.parse_target_routes(args.transit_schedule)
        wanted = set(routes["C"]["link_refs"])
        nodes, links = map31.parse_network_links(args.network, wanted)
        route = map31.route_geometry(routes["C"], nodes, links)

        fig = plt.figure(figsize=(8.2, 11.25), facecolor="white")
        ax = fig.add_axes([0.073, 0.172, 0.757, 0.748])
        map31.draw_basemap(ax, layers, MAP_EXTENT, local=True)
        figure_b5.draw_hexagons(ax, cells)
        figure_b5.draw_case_overlay(ax, "C", service, route, routes["C"]["stops"])
        figure_b5.style_map(ax, MAP_EXTENT)
        map31.draw_scale_bar(ax, 6)

        fig.text(
            0.006, 0.988, "Case C  Line X36", ha="left", va="top",
            fontsize=19, fontweight="bold", color=figure_b5.NAVY,
        )
        fig.text(
            0.006, 0.948, "Local same-agent utility", ha="left", va="top",
            fontsize=15.5, fontweight="bold", color="#34393C",
        )
        fig.text(
            0.822, 0.948, f"n = {len(sample)}", ha="right", va="top",
            fontsize=14, color="#626B70",
        )

        legend = [
            Line2D([0], [0], color="#777F82", lw=2, label="Rail network"),
            Line2D([0], [0], color="#202020", lw=2, ls=(0, (5, 4)),
                   label="DRT service area"),
            Line2D([0], [0], color=map31.ROUTE_COLOUR, lw=3,
                   label="Target bus route"),
            Line2D([0], [0], marker="o", color="none", markerfacecolor="white",
                   markeredgecolor=map31.ROUTE_COLOUR, markeredgewidth=1.8,
                   markersize=7, label="Bus stop"),
            Line2D([0], [0], marker="D", color="none",
                   markerfacecolor=map31.HUB_COLOUR, markeredgecolor="white",
                   markersize=7, label="Rail hub"),
        ]
        fig.legend(
            handles=legend, loc="lower center", bbox_to_anchor=(0.45, 0.132),
            ncol=5, frameon=False, fontsize=9.3, handlelength=2.0,
            columnspacing=1.0, handletextpad=0.42,
        )
        fig.text(
            0.45, 0.104,
            "Numbers report affected travellers in each 1 km² residential hexagon",
            ha="center", va="center", fontsize=10.7, color="#626B70",
        )

        cax = fig.add_axes([0.188, 0.044, 0.525, 0.018])
        colourbar = mpl.colorbar.ColorbarBase(
            cax, cmap=figure_b5.UTILITY_CMAP, norm=figure_b5.NORM,
            orientation="horizontal", ticks=[-25, -20, -15, -10, -5, 0, 5],
        )
        colourbar.ax.tick_params(labelsize=9.5, colors="#4D565B")
        colourbar.outline.set_edgecolor("#8F989C")
        fig.text(
            0.45, 0.068, "Hexagon mean same-agent utility change",
            ha="center", va="bottom", fontsize=12.2, color="#30373A",
        )
        fig.text(
            0.45, 0.012,
            "Background © OpenStreetMap contributors (Geofabrik extract, 22 Aug 2026) · "
            "CRS: EPSG 25832",
            ha="center", va="center", fontsize=7.8, color="#7A8286",
        )

        args.output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.output, dpi=args.dpi, facecolor="white")
        plt.close(fig)
        print(f"Saved {args.output} | Case C n={len(sample)}, occupied hexagons={len(cells)}")


if __name__ == "__main__":
    main()
