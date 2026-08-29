# MATSim DRT dissertation analysis pipeline

This directory contains the analysis code used to derive the dissertation's
baseline, scenario, network and research-question tables. It is intended to be
placed at `analysis/pipeline/` in the repository.

## Scope

The core sequence is:

1. `00_preflight.py` checks the formal MATSim outputs.
2. `01_build_baseline_cohorts.py` identifies the exact B0 target-line cohorts.
3. `02_analyse_scenarios.py` calculates scenario, traveller, trip, service,
   behavioural and equity results.
4. `03_analyse_network_events.py` calculates the secondary road-network results.
5. `04_build_rq_outputs.py` produces the RQ1, RQ2 and RQ3 tables.

The main analysis uses the 10% Open Berlin population, random seed 4711, 200
iterations and the final operational window of iterations 181-200.

## File status

- `00`-`06`, `common.py` and the test are preserved from the FINAL v5 source.
- `07_add_BC_incremental.py` reconstructs the recorded one-off process that
  added B6-PTI and C22-PTI to the completed Case A analysis. The original
  orchestration file was not retained. The reconstruction was checked against
  the actual `ABC_analysis_results_01_04` folder structure and QA columns.
- `07_representative_agent_dayplans.py`, `08_iteration_asset_inventory.py` and
  `09_extract_selected_agent_plan_trajectories.py` are supplementary Chapter 4
  and Appendix tools from FINAL v5.
- `05_make_figures.py` creates early diagnostic plots. It does **not** reproduce
  the final dissertation figures and is not called by `run_core_analysis.sh`.
- `06_optional_costs.py` is conditional and should not be used without sourced
  unit-cost assumptions.

The final dissertation figure-production code is maintained separately because
the published figures were subsequently selected, combined and revised.

## Manifest

`scenario_manifest.csv` records the actual CASA-server output paths recovered
from the successful final preflight report. All ten intervention scenarios are
marked ready because the archived analysis confirms that the formal runs
completed to iteration 200.

These paths document the original run but are machine-specific. A new user must
replace `output_dir` values with the locations of their own MATSim outputs.

## Full analysis

Install the Python dependencies and run from this directory:

```bash
pip install -r requirements.txt
bash run_core_analysis.sh
```

The expected output tree is:

```text
analysis_results/
  00_preflight/
  01_baseline/
  02_scenarios/
  03_network/
  04_RQ_outputs/
```

## Historical B/C incremental run

When Case A results already exist and only B6-PTI and C22-PTI need to be added:

```bash
python 07_add_BC_incremental.py \
  --manifest scenario_manifest.csv \
  --config analysis_config.json \
  --analysis-root analysis_results
```

The script performs B/C extraction in a staging directory, validates all 15
expected scenario products, preserves the Case A folders, merges the inventories
and network comparison, rebuilds the full RQ tables, writes
`BC_incremental_QA.csv` and `ABC_analysis_coverage.csv`, and creates
`ABC_analysis_results_01_04.tar.gz` by default.

If B/C folders already exist, the script stops. Use `--force` only for an
intentional rebuild. Pass `--archive ""` to skip archive creation.

## Tests

```bash
python tests/smoke_test.py
```

The smoke test uses synthetic MATSim-like inputs and does not require the CASA
server or the dissertation's full output archive.

## Derived results and large files

Raw MATSim outputs and the complete `ABC_analysis_results_01_04.tar.gz` are not
part of this pipeline directory. The archive is a derived-results snapshot, not
source code. If it exceeds GitHub's normal file-size limit, keep a documented
subset of final CSV tables in `derived_results/` and distribute the complete
archive through a release asset, research-data repository or other stable
storage instead of committing it to Git history.
