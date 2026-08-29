# Dissertation figure-generation pipeline

This folder reconstructs the dissertation figures from the frozen
`analysis_results` outputs.  It is designed to live at:

```text
drt-bus-replacement-BerlinBrandenburg/
└── analysis/
    └── figure_generation/   ← this folder
```

The large analysis archive is **an input, not a GitHub file**.  Keep
`ABC_analysis_results_01_04.tar.gz` on a local drive and pass its path on the
command line.  The same commands also accept an already extracted
`analysis_results/` directory.

## What is included

| Code | Figures |
|---|---|
| `make_main_figures.py` | 4.1–4.14 and 5.1–5.3 |
| `make_appendix_figures.py` | B.1–B.4 and B.6–B.9 |
| `maps/make_figure_3_1.py` | 3.1 |
| `maps/make_figure_B5.py` | B.5 |
| `maps/make_figure_B10.py` | B.10 |
| `make_all_figures.py` | runs the complete pipeline |
| `FIGURE_MANIFEST.csv` | figure-to-input provenance table |
| `PROVENANCE.md` | supplied-package hashes and validation record |

Shared data access and styling are in `data_access.py` and `plot_style.py`.
No final numbers are typed into the plotting code: values are read or derived
from the supplied analytical outputs.  Frozen sample counts and representative
person identifiers are used only as QA/provenance checks.

## Install

Python 3.10 or newer is recommended.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
python -m pip install -r analysis/figure_generation/requirements.txt
```

GeoPandas and its companions are required only for Figures 3.1, B.5 and B.10.

## Generate all non-spatial figures

Run this command from the repository root, changing the input path to the file
on your computer:

```bash
python analysis/figure_generation/validate_analysis_source.py \
  --analysis-source "/path/to/ABC_analysis_results_01_04.tar.gz"
```

If every check prints `OK`, generate the figures:

```bash
python analysis/figure_generation/make_all_figures.py \
  --analysis-source "/path/to/ABC_analysis_results_01_04.tar.gz" \
  --output-dir figures
```

This writes Figures 4.1–4.14, 5.1–5.3, B.1–B.4 and B.6–B.9.  The input archive
is read in place and does not need to be copied into the repository.

An extracted directory works too:

```bash
python analysis/figure_generation/make_all_figures.py \
  --analysis-source "/path/to/analysis_results" \
  --output-dir figures
```

## Generate selected figures

```bash
# One main figure
python analysis/figure_generation/make_main_figures.py \
  --analysis-source "/path/to/ABC_analysis_results_01_04.tar.gz" \
  --output-dir figures \
  --figures 4.2

# Several appendix figures
python analysis/figure_generation/make_appendix_figures.py \
  --analysis-source "/path/to/ABC_analysis_results_01_04.tar.gz" \
  --output-dir figures \
  --figures B.1 B.3 B.8
```

Use `--figures all` to run every figure owned by that script.

## Maps: Figures 3.1, B.5 and B.10

The map code is included, but the analysis archive alone is not sufficient.
Exact reproduction also requires:

- the frozen service-area shapefile bundles in the repository `spatial/` folder;
- the Geofabrik Brandenburg-with-Berlin OSM vector extract used for the maps;
- a Berlin administrative-boundary vector (Figure 3.1);
- the B0 MATSim transit schedule and network XML files.

Those external files were not supplied in the final figure package, so the map
scripts were syntax- and input-schema-checked but could not be run end to end in
this reconstruction.  Full commands and provenance limitations are documented
in [`maps/README.md`](maps/README.md).

When all external inputs are available:

```bash
python analysis/figure_generation/make_all_figures.py \
  --analysis-source "/path/to/ABC_analysis_results_01_04.tar.gz" \
  --output-dir figures \
  --include-maps \
  --spatial-context spatial \
  --osm-dir "/path/to/geofabrik_brandenburg" \
  --berlin-boundary "/path/to/berlin_boundary.geojson" \
  --transit-schedule "/path/to/B0.output_transitSchedule.xml.gz" \
  --network "/path/to/B0.output_network.xml.gz"
```

### Optional small map input

The complete `RQ3_spatial_person_impacts.csv.gz` member is about 182 MB.  To
create a small, identifier-free subset for the three frozen map scenarios:

```bash
python analysis/figure_generation/prepare_spatial_figure_input.py \
  --analysis-source "/path/to/ABC_analysis_results_01_04.tar.gz" \
  --output derived_results/figure_inputs/spatial_target_riders.csv.gz
```

The resulting file contains 1,304 target-rider rows and is small enough for
GitHub.  Whether to publish synthetic home coordinates is a project decision;
the full local archive remains the safest default.

## Reproducibility notes

- `ressultfinal.zip` contained 27 PNGs and omitted Figure B.1.  B.1 is rebuilt
  from its final dissertation caption and method: hourly road VKT, travel time
  and delay differences for A8-FM, B6-PTI and C22-PTI, divided by the respective
  daily B0 totals.  The code retains model records after hour 24.
- Figure B.2 uses the four representative person IDs frozen in the submitted
  figure and reconstructs their B0/A8-FM daily trip sequences from
  `trip_level_impacts.csv.gz`.  A deterministic fallback is provided if a
  future archive omits an ID.
- Figure B.6 uses the rail-hub coordinates recoverable from the frozen map
  code.  These reproduce the sample sizes, correlations and total Case B DRT
  users, but redistribute two users between Case B distance quartiles: the
  reconstructed Q2/Q3 shares are 58.3%/27.3%, while the supplied final PNG
  shows 50.0%/36.4%.  This indicates that the final export used a slightly
  different, unavailable hub-coordinate or distance-binning version.
- Figures B.5 and B.10 retain the validated mapped samples (A=45, B=30, C=681)
  as strict QA checks.  `--no-strict` changes a mismatch to a warning.
- The three supplied map scripts were produced after the final PNG export and
  are therefore described as **reproduction code**, not independently verified
  original source.  The B.5 and B.10 final PNGs also appear to have been resized
  after plotting.
- Small visual differences can arise from Matplotlib/Seaborn versions, font
  rasterisation, and a different OSM extract.  The calculations, scenario
  filters and figure structure are frozen in code.

## Upload this folder with the GitHub website

1. Extract the delivered ZIP on your computer.
2. Open the repository's `analysis/` folder on GitHub.
3. Choose **Add file → Upload files**.  Do not use **Create new file**.
4. Drag the whole `figure_generation` folder onto the upload page.
5. Check that GitHub shows paths beginning with
   `figure_generation/`, add a commit message, and choose **Commit changes**.

The folder contains only small source and documentation files; it does not
contain the large analysis archive or generated PNGs.

## Validation

```bash
python -m compileall -q analysis/figure_generation
pytest -q analysis/figure_generation/tests
python analysis/figure_generation/validate_figure_outputs.py \
  --figure-dir figures
```

Before publication, compare newly generated PNGs with the submitted figures
and record package versions together with the external map-input checksums.
