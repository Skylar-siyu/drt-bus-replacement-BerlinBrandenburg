# Derived results

This directory contains the public, aggregate outputs used to audit the dissertation findings. The CSV files were copied without numerical modification from the final analysis archive, `ABC_analysis_results_01_04.tar.gz`.

## Contents

- `baseline/`: aggregate baseline operations and target-journey match quality.
- `scenarios/`: aggregate outputs for the ten formal intervention scenarios, plus the B0 convergence and mode-share summaries.
- `network/`: aggregate daily and hourly road-network outputs for B0, A8-FM, B6-PTI, and C22-PTI.
- `rq_outputs/`: research-question tables and quality-assurance summaries used for reporting.
- `DATA_DICTIONARY.md`: descriptions of the recurring output files and units.
- `SHA256SUMS`: checksums for integrity verification.

Scenario names use underscores in filenames and folders (`A8_FM`) and hyphens in the dissertation (`A8-FM`).

| Scenario | Role in the dissertation |
|---|---|
| A4-FL, A8-FL, A12-FL | Case A fleet sensitivity, FL pricing |
| A4-FH, A8-FH, A12-FH | Case A fleet sensitivity, FH pricing |
| A8-FM | Case A principal structural scenario |
| A8-SUB1 | Case A surcharge sensitivity |
| B6-PTI | Case B structural comparison |
| C22-PTI | Case C high-demand boundary comparison |

## Provenance

- Canonical source archive: `ABC_analysis_results_01_04.tar.gz`
- Source SHA-256: `a611c08d3c873c86b73268ff5aee64fb0fe44183b00f4e27e0c5df97b675fb73`
- Population sample: 10%
- MATSim random seed: 4711
- Simulation iterations: 200
- Final analysis window: iterations 181–200
- Intervention treatment: public-transport integrated, with zero additional DRT surcharge unless the scenario name denotes a pricing sensitivity

The files retain unrounded machine-readable values. Reported dissertation values may be rounded for presentation. Some internal column names use `target_riders`; the final dissertation uses `affected travellers`. The underlying cohort definition is unchanged.

## Important count note

Case C contains 1,833 baseline target-line trips, of which 1,832 have a paired intervention trip in the final comparison. The aggregate comparison metrics use the 1,832 matched trips. This difference is recorded in `rq_outputs/BC_incremental_QA.csv` and is not a data-processing error.

## Deliberate exclusions

This public folder excludes all person-level, trip-level, boarding-level, and spatial-person records, including:

- `person_level_impacts.csv.gz`
- `trip_level_impacts.csv.gz`
- `RQ3_spatial_person_impacts.csv.gz`
- baseline person, trip, boarding, and boarding-match files
- `_cache/` contents
- preflight files containing local execution metadata

These exclusions prevent publication of agent identifiers and detailed spatial records and keep the repository lightweight. The full 473 MiB archive should remain in secure local storage and should not be committed to GitHub.

The records describe synthetic MATSim simulation agents, not observed human participants. Some equity and transition aggregates contain small cell counts; they are retained because they summarize synthetic agents and contain no direct identifiers or coordinates.

Because individual observations are excluded, distribution plots that require raw person- or trip-level values cannot be recreated from this public folder alone. The aggregate tables are sufficient to audit reported counts, means, quantiles, transition shares, DRT KPIs, equity-group summaries, and network changes.

Person-level Pearson correlations and the Case C `-553.91` utility-outlier sensitivity check also require the secure local archive and cannot be recomputed from this public aggregate package.

## Known field limitations

- Canonical DRT service, waiting, and vehicle-distance values are means across iterations 181–200, not single-iteration integer totals. Decimal served-request counts are expected for this reason.
- In `drt_adoption_summary.csv`, `drt_containing_trip_keys` and `drt_containing_trip_share` are doubled by the archived key-building procedure and do not represent unique DRT-containing journeys. For the final selected journey count, use the `scenario_drt_containing_trips` row in `trip_outcome_summary.csv`, or sum the scenario's `drt` and `pt_w_drt_used` rows in `system_main_mode_share.csv`.
- In every scenario's `drt_kpi_canonical.csv`, the fields `min_idle_vehicles` and `mean_idle_vehicles` were incorrectly populated with the nominal fleet size by the archived extraction pipeline. The same two inherited columns in the wide RQ tables must not be used as idle-capacity evidence. For the final-window minimum idle/spare-capacity measure, use `vehicle::minCountIdleVehicles__mean` and `vehicle::minShareIdleVehicles__mean` in `drt_kpi_raw_final_window.csv`.
- The field `drt_occupied_vkt_km` is mislabeled in the archived canonical and wide RQ outputs: it contains passenger-distance travelled in kilometres, not occupied vehicle kilometres. Do not interpret it as vehicle distance. When occupied vehicle kilometres are needed, calculate `drt_total_vkt_km - drt_empty_vkt_km`.
- In the B6-PTI and C22-PTI network summaries, fields beginning `drt_regex_` are zero because the vehicle-ID regular expression did not detect those scenarios' DRT vehicle names. Zero in these fields does not mean that no DRT vehicles operated. Use the total network comparison fields for road-network effects and the DRT KPI tables for DRT vehicle kilometres.

The source CSV values are preserved rather than silently corrected so that the public files remain traceable to the archived analysis outputs.
