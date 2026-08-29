#!/usr/bin/env bash
set -euo pipefail

python 00_preflight.py --manifest scenario_manifest.csv --config analysis_config.json
python 01_build_baseline_cohorts.py --manifest scenario_manifest.csv --config analysis_config.json
python 02_analyse_scenarios.py --manifest scenario_manifest.csv --config analysis_config.json
python 03_analyse_network_events.py --manifest scenario_manifest.csv --config analysis_config.json
python 04_build_rq_outputs.py --manifest scenario_manifest.csv
python 05_make_figures.py

echo
echo "Core dissertation analysis complete."
echo "Optional: fill sourced values in optional_cost_assumptions.csv and run 06_optional_costs.py."
