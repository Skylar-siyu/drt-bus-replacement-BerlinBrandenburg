#!/usr/bin/env python3
"""Create Figure 3.1: Berlin–Brandenburg DRT case-study maps.

The script uses the original analytical inputs rather than values digitised from
the finished PNG:

* OpenStreetMap/Geofabrik vector layers for the background;
* the MATSim transit schedule and network for routes and stops; and
* the three frozen service-area shapefiles supplied with the analysis.

All analytical geometry is handled in EPSG:25832.  Only the final figure is a
raster image.  The three local panels use the same 18 x 22 km map scale.
"""

from __future__ import annotations

import argparse
import gzip
import math
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from shapely.geometry import LineString, box


CRS = "EPSG:25832"
CASE_COLOURS = {"A": "#24A3A6", "B": "#8878D4", "C": "#FF8357"}
ROUTE_COLOUR = "#F25B24"
HUB_COLOUR = "#7B1FA2"

SERVICE_AREA_STEMS = {
    # Repository filenames are listed first.  The second name is accepted so
    # the original spatial_context.zip can be used without renaming files.
    "A": ("caseA_890", "bernau_core_final"),
    "B": ("caseB_435", "caseB_435_exact_final"),
    "C": ("caseC_X36", "caseC_X36_replacement_area"),
}
LINE_TOKENS = {"A": "890", "B": "435", "C": "X36"}
TARGET_TRANSIT_LINE_IDS = {
    "A": "890---22435",
    "B": "435---31682",
    "C": "X36---34541",
}
LOCAL_TITLES = {
    "A": "(b) Case A: Line 890 · Bernau",
    "B": "(c) Case B: Line 435 · Fürstenwalde–Storkow",
    "C": "(d) Case C: Line X36 · Spandau–Hennigsdorf",
}

# Frozen rail-interchange coordinates used by the cartographic specification.
RAIL_HUBS = {
    "A": [(810_543.76, 5_846_200.04)],
    "B": [(835_837.29, 5_800_505.44), (844_577.16, 5_813_882.81)],
    "C": [(784_545.64, 5_840_263.81), (784_627.76, 5_828_820.88)],
}

# The regional extent is fixed for consistent comparison. Local views are
# calculated from the service-area polygon centroids below.
OVERVIEW_EXTENT = (730_000.0, 900_000.0, 5_790_000.0, 5_877_000.0)
LOCAL_WIDTH_M = 18_000.0
LOCAL_HEIGHT_M = 22_000.0


def open_maybe_gzip(path: Path):
    return gzip.open(path, "rb") if path.suffix == ".gz" else path.open("rb")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def prepare_spatial_context(path: Path, work: Path) -> Path:
    """Return a directory containing the frozen service-area shapefiles."""
    if path.is_dir():
        return path
    if not zipfile.is_zipfile(path):
        raise ValueError(f"Expected a directory or ZIP archive: {path}")
    out = work / "spatial_context"
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as zf:
        zf.extractall(out)
    return out


def find_file(root: Path, stem_or_name, suffix: str | None = None) -> Path:
    names = (stem_or_name,) if isinstance(stem_or_name, str) else tuple(stem_or_name)
    wanted = {str(name).lower() for name in names}
    candidates = sorted(p for p in root.rglob("*") if p.is_file())
    for p in candidates:
        if suffix and p.suffix.lower() != suffix.lower():
            continue
        if p.stem.lower() in wanted or p.name.lower() in wanted:
            return p
    raise FileNotFoundError(f"Could not find any of {names!r} under {root}")


def read_service_areas(root: Path) -> dict[str, gpd.GeoDataFrame]:
    result = {}
    for case, stems in SERVICE_AREA_STEMS.items():
        shp = find_file(root, stems, ".shp")
        gdf = gpd.read_file(shp)
        if gdf.crs is None:
            gdf = gdf.set_crs(CRS)
        else:
            gdf = gdf.to_crs(CRS)
        result[case] = gdf.dissolve()
    return result


def find_osm_layer(root: Path, token: str, required: bool = True) -> Path | None:
    matches = [
        p for p in root.rglob("*.shp")
        if token.lower() in p.stem.lower() and "free" in p.stem.lower()
    ]
    if not matches:
        matches = [p for p in root.rglob("*.shp") if token.lower() in p.stem.lower()]
    if matches:
        return sorted(matches)[0]
    if required:
        raise FileNotFoundError(f"No OSM layer containing {token!r} found under {root}")
    return None


def read_vector_window(path: Path, extent) -> gpd.GeoDataFrame:
    """Read only the part of a large Geofabrik shapefile needed by the map."""
    sample = gpd.read_file(path, rows=1)
    source_crs = sample.crs
    xmin, xmax, ymin, ymax = extent
    query = gpd.GeoSeries([box(xmin, ymin, xmax, ymax)], crs=CRS)
    if source_crs is not None:
        query = query.to_crs(source_crs)
    bbox = tuple(query.total_bounds)
    gdf = gpd.read_file(path, bbox=bbox)
    return gdf.set_crs(CRS) if gdf.crs is None else gdf.to_crs(CRS)


def read_osm_layers(root: Path, extent=OVERVIEW_EXTENT,
                    buildings_extent=None) -> dict[str, gpd.GeoDataFrame | None]:
    tokens = {
        "landuse": "landuse_a",
        "water": "water_a",
        "buildings": "buildings_a",
        "roads": "roads",
        "railways": "railways",
    }
    layers: dict[str, gpd.GeoDataFrame | None] = {}
    for key, token in tokens.items():
        path = find_osm_layer(root, token, required=key not in {"buildings", "roads"})
        if path is None:
            layers[key] = None
            continue
        layer_extent = buildings_extent if key == "buildings" and buildings_extent else extent
        layers[key] = read_vector_window(path, layer_extent)
    return layers


def read_berlin_boundary(path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    gdf = gdf.set_crs(CRS) if gdf.crs is None else gdf.to_crs(CRS)
    return gdf.dissolve()


def parse_target_routes(schedule_path: Path):
    """Read target route link IDs and stop coordinates from MATSim schedule."""
    with open_maybe_gzip(schedule_path) as fh:
        root = ET.parse(fh).getroot()

    stops: dict[str, tuple[float, float]] = {}
    for elem in root.iter():
        if local_name(elem.tag) == "stopFacility":
            stops[elem.attrib["id"]] = (float(elem.attrib["x"]), float(elem.attrib["y"]))

    output: dict[str, dict[str, list]] = {}
    for case, token in LINE_TOKENS.items():
        candidates = []
        for line in (e for e in root.iter() if local_name(e.tag) == "transitLine"):
            line_id = line.attrib.get("id", "")
            if line_id != TARGET_TRANSIT_LINE_IDS[case]:
                continue
            for route in (e for e in line if local_name(e.tag) == "transitRoute"):
                stop_refs = [
                    s.attrib.get("refId") for e in route.iter()
                    if local_name(e.tag) == "routeProfile"
                    for s in e if local_name(s.tag) == "stop"
                ]
                link_refs = [
                    e.attrib.get("refId") for parent in route.iter()
                    if local_name(parent.tag) == "route"
                    for e in parent if local_name(e.tag) == "link"
                ]
                stop_refs = [x for x in stop_refs if x in stops]
                link_refs = [x for x in link_refs if x]
                if stop_refs:
                    candidates.append((len(link_refs), stop_refs, link_refs))
        if not candidates:
            raise RuntimeError(
                f"MATSim transit line {TARGET_TRANSIT_LINE_IDS[case]!r} "
                f"(target line {token}) was not found"
            )
        _, stop_refs, link_refs = max(candidates, key=lambda x: (x[0], len(x[1])))
        output[case] = {
            "stop_refs": stop_refs,
            "stops": [stops[x] for x in stop_refs],
            "link_refs": link_refs,
        }
    return output


def parse_network_links(network_path: Path, wanted: set[str]):
    """Read only links required by the three target routes."""
    nodes: dict[str, tuple[float, float]] = {}
    links: dict[str, tuple[str, str]] = {}
    with open_maybe_gzip(network_path) as fh:
        for _, elem in ET.iterparse(fh, events=("end",)):
            name = local_name(elem.tag)
            if name == "node":
                nodes[elem.attrib["id"]] = (float(elem.attrib["x"]), float(elem.attrib["y"]))
            elif name == "link" and elem.attrib.get("id") in wanted:
                links[elem.attrib["id"]] = (elem.attrib["from"], elem.attrib["to"])
            elem.clear()
    return nodes, links


def route_geometry(route, nodes, links):
    segments = []
    for link_id in route["link_refs"]:
        if link_id not in links:
            continue
        a, b = links[link_id]
        if a in nodes and b in nodes:
            segments.append(LineString([nodes[a], nodes[b]]))
    if not segments:
        # Transparent fallback for schedules without network-route link lists.
        return LineString(route["stops"])
    series = gpd.GeoSeries(segments, crs=CRS)
    return series.union_all() if hasattr(series, "union_all") else series.unary_union


def clip_to_extent(gdf: gpd.GeoDataFrame | None, extent):
    if gdf is None or gdf.empty:
        return gdf
    xmin, xmax, ymin, ymax = extent
    return gdf.cx[xmin:xmax, ymin:ymax]


def draw_basemap(ax, layers, extent, *, local: bool):
    ax.set_facecolor("#FBFAF7")
    land = clip_to_extent(layers["landuse"], extent)
    if land is not None and not land.empty:
        if "fclass" in land.columns:
            fclass = land["fclass"].astype(str).str.lower()
            green = land[fclass.isin({
                "forest", "park", "grass", "meadow", "nature_reserve", "heath",
                "scrub", "orchard", "farm", "farmland", "recreation_ground",
            })]
            built = land[fclass.isin({"residential", "commercial", "industrial", "retail"})]
        else:
            green = land
            built = land.iloc[0:0]
        if not green.empty:
            green.plot(ax=ax, color="#DDEBD8", edgecolor="none", zorder=0)
        if not built.empty:
            built.plot(ax=ax, color="#ECE9E1", edgecolor="none", zorder=0.2)

    water = clip_to_extent(layers["water"], extent)
    if water is not None and not water.empty:
        water.plot(ax=ax, color="#CBE4F1", edgecolor="#B9D8E6", linewidth=0.25, zorder=0.4)

    buildings = clip_to_extent(layers.get("buildings"), extent)
    if local and buildings is not None and not buildings.empty:
        buildings.plot(ax=ax, color="#DED9CE", edgecolor="none", alpha=0.65, zorder=0.5)

    roads = clip_to_extent(layers.get("roads"), extent)
    if roads is not None and not roads.empty:
        if "fclass" in roads.columns:
            fclass = roads["fclass"].astype(str).str.lower()
            major = roads[fclass.str.contains("motorway|trunk|primary|secondary", regex=True)]
            minor = roads.drop(major.index)
        else:
            major = roads
            minor = roads.iloc[0:0]
        if local and not minor.empty:
            minor.plot(ax=ax, color="#D6D5D1", linewidth=0.20, alpha=0.65, zorder=0.7)
        if not major.empty:
            major.plot(ax=ax, color="#C4C6C5", linewidth=0.45 if local else 0.25, zorder=0.8)

    rail = clip_to_extent(layers["railways"], extent)
    if rail is not None and not rail.empty:
        rail.plot(ax=ax, color="#777F82", linewidth=0.65 if local else 0.32, alpha=0.85, zorder=1)


def draw_scale_bar(ax, length_km=6):
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    x0 = xmin + 0.04 * (xmax - xmin)
    y0 = ymin + 0.035 * (ymax - ymin)
    segments = 4 if length_km >= 10 else 3
    seg = (length_km * 1000) / segments
    for i in range(segments):
        ax.plot([x0 + i * seg, x0 + (i + 1) * seg], [y0, y0],
                color="#202020" if i % 2 == 0 else "white", lw=5,
                solid_capstyle="butt", zorder=20)
    labels = np.linspace(0, length_km, segments + 1)
    for i, value in enumerate(labels):
        label = f"{value:g}"
        ax.text(x0 + i * seg, y0 + 0.012 * (ymax - ymin), str(label),
                ha="center", va="bottom", fontsize=7, color="#333333", zorder=20)
    ax.text(x0 + segments * seg + 0.008 * (xmax - xmin), y0 + 0.012 * (ymax - ymin),
            "km", ha="left", va="bottom", fontsize=7, color="#333333", zorder=20)


def style_map_axes(ax, extent, title):
    xmin, xmax, ymin, ymax = extent
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#A9B0B3")
        spine.set_linewidth(0.8)
    ax.text(0.012, 0.985, title, transform=ax.transAxes, ha="left", va="top",
            fontsize=11.2, fontweight="bold", color="#2F3437",
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.82, pad=2.0), zorder=30)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--osm-dir", type=Path, required=True,
                        help="Extracted Geofabrik Brandenburg (mit Berlin) shapefile directory")
    parser.add_argument("--berlin-boundary", type=Path, required=True,
                        help="Berlin administrative-boundary vector file")
    parser.add_argument("--spatial-context", type=Path, required=True,
                        help="spatial_context directory or ZIP")
    parser.add_argument("--transit-schedule", type=Path, required=True)
    parser.add_argument("--network", type=Path, required=True)
    parser.add_argument("--output", type=Path,
                        default=Path("Figure_3_1_Berlin_DRT_cases.png"))
    parser.add_argument("--dpi", type=int, default=300)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="figure31_") as td:
        context_root = prepare_spatial_context(args.spatial_context, Path(td))
        service = read_service_areas(context_root)
        service_bounds = np.vstack([g.total_bounds for g in service.values()])
        buildings_extent = (
            float(service_bounds[:, 0].min() - 12_000),
            float(service_bounds[:, 2].max() + 12_000),
            float(service_bounds[:, 1].min() - 12_000),
            float(service_bounds[:, 3].max() + 12_000),
        )
        layers = read_osm_layers(args.osm_dir, OVERVIEW_EXTENT, buildings_extent)
        berlin = read_berlin_boundary(args.berlin_boundary)
        routes = parse_target_routes(args.transit_schedule)
        wanted = {x for r in routes.values() for x in r["link_refs"]}
        nodes, links = parse_network_links(args.network, wanted)
        route_geoms = {c: route_geometry(r, nodes, links) for c, r in routes.items()}

        fig = plt.figure(figsize=(16, 15.3), facecolor="white")
        gs = fig.add_gridspec(2, 3, height_ratios=[1.13, 1.0], hspace=0.018, wspace=0.012,
                              left=0.025, right=0.985, top=0.985, bottom=0.105)
        ax_over = fig.add_subplot(gs[0, :])
        local_axes = {case: fig.add_subplot(gs[1, i]) for i, case in enumerate("ABC")}

        draw_basemap(ax_over, layers, OVERVIEW_EXTENT, local=False)
        berlin.boundary.plot(ax=ax_over, color="#4E5B5E", linewidth=1.0, zorder=4)
        for case in "ABC":
            geom = service[case].geometry.iloc[0]
            minx, miny, maxx, maxy = geom.bounds
            pad = 1_000.0
            ax_over.add_patch(Rectangle((minx - pad, miny - pad), maxx - minx + 2 * pad,
                                        maxy - miny + 2 * pad, fill=False,
                                        edgecolor=ROUTE_COLOUR, linewidth=1.2,
                                        linestyle=(0, (4, 3)), zorder=10))
            gpd.GeoSeries([route_geoms[case]], crs=CRS).plot(
                ax=ax_over, color=ROUTE_COLOUR, linewidth=1.0, zorder=9)
            midpoint = route_geoms[case].interpolate(0.5, normalized=True)
            ax_over.text(midpoint.x, midpoint.y, case, ha="center", va="center",
                         fontsize=12, fontweight="bold", color="white",
                         bbox=dict(boxstyle="square,pad=0.18", facecolor=ROUTE_COLOUR,
                                   edgecolor="none"), zorder=12)

        style_map_axes(ax_over, OVERVIEW_EXTENT, "(a) Berlin–Brandenburg regional overview")
        ax_over.text(0.43, 0.43, "Berlin", transform=ax_over.transAxes,
                     fontsize=8.5, color="#3D4143", zorder=12)
        ax_over.text(0.89, 0.90, "Brandenburg", transform=ax_over.transAxes,
                     fontsize=8.5, color="#646A6C", zorder=12)
        ax_over.annotate("N", xy=(0.968, 0.932), xytext=(0.968, 0.965),
                         xycoords="axes fraction", textcoords="axes fraction",
                         ha="center", va="bottom", fontsize=9,
                         arrowprops=dict(arrowstyle="-|>", color="#2B3032", lw=1.0))
        draw_scale_bar(ax_over, 20)

        for case, ax in local_axes.items():
            centroid = service[case].geometry.iloc[0].centroid
            extent = (centroid.x - LOCAL_WIDTH_M / 2, centroid.x + LOCAL_WIDTH_M / 2,
                      centroid.y - LOCAL_HEIGHT_M / 2, centroid.y + LOCAL_HEIGHT_M / 2)
            draw_basemap(ax, layers, extent, local=True)
            service[case].boundary.plot(ax=ax, color="#222222", linewidth=1.25,
                                        linestyle=(0, (4, 3)), zorder=8)
            gpd.GeoSeries([route_geoms[case]], crs=CRS).plot(
                ax=ax, color=ROUTE_COLOUR, linewidth=1.6, zorder=10)
            sx, sy = zip(*routes[case]["stops"])
            ax.scatter(sx, sy, s=13, facecolor="white", edgecolor=ROUTE_COLOUR,
                       linewidth=1.0, zorder=11)
            hx, hy = zip(*RAIL_HUBS[case])
            ax.scatter(hx, hy, s=30, c=HUB_COLOUR, edgecolor="white", linewidth=0.7,
                       zorder=12)
            style_map_axes(ax, extent, LOCAL_TITLES[case])
            draw_scale_bar(ax, 6)

        legend = [
            Patch(facecolor="#DDEBD8", edgecolor="none", label="Green / open land"),
            Patch(facecolor="#ECE9E1", edgecolor="none", label="Built-up / buildings"),
            Patch(facecolor="#CBE4F1", edgecolor="none", label="Water"),
            Line2D([0], [0], color="#777F82", lw=1.0, label="Rail network"),
            Line2D([0], [0], color="#222222", lw=1.2, ls=(0, (4, 3)), label="DRT service area"),
            Line2D([0], [0], color=ROUTE_COLOUR, lw=1.8, label="Target bus route"),
            Line2D([0], [0], marker="o", color="none", markerfacecolor="white",
                   markeredgecolor=ROUTE_COLOUR, markeredgewidth=1.2, label="Bus stop"),
            Line2D([0], [0], marker="o", color="none", markerfacecolor=HUB_COLOUR,
                   markeredgecolor="white", label="Rail interchange"),
        ]
        fig.legend(handles=legend, loc="lower center", bbox_to_anchor=(0.5, 0.047),
                   ncol=8, frameon=False, fontsize=8.7, handlelength=2.3,
                   columnspacing=1.25, handletextpad=0.45)
        fig.text(0.5, 0.026,
                 "Background © OpenStreetMap contributors (Geofabrik extract, 22 Aug 2026); "
                 "transit schedule dated 19 Nov 2024.",
                 ha="center", va="center", fontsize=7.3, color="#7A8286")

        args.output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.output, dpi=args.dpi, facecolor="white")
        plt.close(fig)
        print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
