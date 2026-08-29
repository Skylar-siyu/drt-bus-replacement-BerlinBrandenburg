# Map figure reproduction code

This folder contains the reproduction scripts for three dissertation maps:

- `make_figure_3_1.py` — Figure 3.1, the regional overview and three case maps;
- `make_figure_B5.py` — Figure B.5, residential-cell utility in Cases A and B;
- `make_figure_B10.py` — Figure B.10, residential-cell utility in Case C.

Keep the three scripts together. B.5 and B.10 reuse mapping and hexagon
functions from the other files. The imports support both direct script execution
and Python package execution. Default `spatial/` and `figures/` paths are resolved
from the repository root when it can be detected, so commands do not depend on
the terminal's current working directory. Explicit paths remain recommended.

## Python dependencies

Python 3.10 or newer is recommended. The map scripts require:

```text
geopandas >= 0.14
matplotlib >= 3.8
numpy >= 1.26
pandas >= 2.1
Pillow >= 10.0
pyogrio >= 0.7
shapely >= 2.0
```

GeoPandas also installs the CRS and vector-I/O dependencies needed to read and
reproject the map layers.

## Repository inputs

The service-area shapefiles are expected under `spatial/`:

```text
caseA_890.shp
caseB_435.shp
caseC_X36.shp
```

Each `.shp` must remain beside its `.dbf`, `.shx`, `.prj` and `.cpg` files. The
original stems `bernau_core_final`, `caseB_435_exact_final` and
`caseC_X36_replacement_area` are also accepted. All analytical geometry is
handled in EPSG:25832.

B.5 and B.10 accept either:

1. the full `ABC_analysis_results_01_04.tar.gz` archive;
2. the extracted `RQ3_spatial_person_impacts.csv.gz`; or
3. the GitHub-sized `spatial_target_riders.csv.gz` file.

The direct CSV.GZ input needs only these columns:

```text
scenario,delta_score,baseline_target_line_rider,home_x,home_y
```

Boolean values may be written as `true`/`false`, `1`/`0`, `yes`/`no`, or
`y`/`n`, without case sensitivity.

## External inputs

The following large or externally licensed inputs are not included in this
folder:

- the extracted Geofabrik Brandenburg (mit Berlin) free-shapefile package used
  for the OSM land-use, water, building, road and railway layers;
- a Berlin administrative-boundary vector for Figure 3.1;
- the MATSim baseline transit schedule
  `B0-10pct-it0-200-t16.output_transitSchedule.xml.gz`;
- the MATSim baseline network
  `B0-10pct-it0-200-t16.output_network.xml.gz`.

The frozen transit-line identifiers are `890---22435`, `435---31682` and
`X36---34541`. The supplied final maps used a Geofabrik extract dated
22 August 2026 and the map note identifies the transit schedule as dated
19 November 2024. Using a later OSM extract may change the background.

Because these exact external inputs are not present in the supplied archive,
the scripts could be syntax-checked and their analytical input schema verified,
but the maps could not be regenerated and compared pixel-for-pixel in the
current workspace. The scripts should be treated as map reproduction code. The
delivered B.5 and B.10 PNGs also have smaller pixel dimensions than the scripts'
default 300 dpi canvases, which indicates a later resizing/export step.

## Commands

The examples below assume this folder is stored at `analysis/figure_generation/maps/` and
the commands are run from the repository root.

### Figure 3.1

```bash
python analysis/figure_generation/maps/make_figure_3_1.py \
  --osm-dir environment/geofabrik_brandenburg \
  --berlin-boundary environment/berlin_boundary.geojson \
  --spatial-context spatial \
  --transit-schedule scenario_setup/B0-10pct-it0-200-t16.output_transitSchedule.xml.gz \
  --network scenario_setup/B0-10pct-it0-200-t16.output_network.xml.gz \
  --output figures/Figure_3_1_Berlin_DRT_cases.png
```

### Figure B.5

```bash
python analysis/figure_generation/maps/make_figure_B5.py \
  --analysis-source derived_results/figure_inputs/spatial_target_riders.csv.gz \
  --spatial-context spatial \
  --osm-dir environment/geofabrik_brandenburg \
  --transit-schedule scenario_setup/B0-10pct-it0-200-t16.output_transitSchedule.xml.gz \
  --network scenario_setup/B0-10pct-it0-200-t16.output_network.xml.gz \
  --output figures/Figure_B5_residential_cell_utility_map.png
```

### Figure B.10

```bash
python analysis/figure_generation/maps/make_figure_B10.py \
  --analysis-source derived_results/figure_inputs/spatial_target_riders.csv.gz \
  --spatial-context spatial \
  --osm-dir environment/geofabrik_brandenburg \
  --transit-schedule scenario_setup/B0-10pct-it0-200-t16.output_transitSchedule.xml.gz \
  --network scenario_setup/B0-10pct-it0-200-t16.output_network.xml.gz \
  --output figures/Figure_B10_residential_cell_utility_case_C.png
```

## Sample-size QA

Strict QA is enabled by default. With the frozen service areas and the 1.8 km
focus buffer, the scripts require mapped samples of 45 for Case A, 30 for Case
B and 681 for Case C. A mismatch stops execution because it commonly indicates
the wrong result file, service-area geometry or CRS.

For diagnostic work, pass `--no-strict` to B.5 or B.10. The script will print a
warning and continue with the available sample.

## Attribution

Background data © OpenStreetMap contributors, distributed by Geofabrik under
the Open Database License. The generated source notes record the frozen extract
date and EPSG:25832 CRS.
