#!/usr/bin/env bash
set -euo pipefail

python 00_preflight.py --manifest scenario_manifest.csv --config analysis_config.json --strict
python 01_build_baseline_cohorts.py --manifest scenario_manifest.csv --config analysis_config.json
python 02_analyse_scenarios.py --manifest scenario_manifest.csv --config analysis_config.json
python 03_analyse_network_events.py --manifest scenario_manifest.csv --config analysis_config.json
python 04_build_rq_outputs.py --manifest scenario_manifest.csv

echo
echo "Core analysis and RQ tables complete."
echo "05_make_figures.py contains diagnostic plots only; final dissertation figures are rebuilt separately."
