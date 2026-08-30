# Data dictionary

All files are comma-separated UTF-8 text. Missing values are represented by empty fields. Shares and rates are stored as fractions from 0 to 1 unless a column name states otherwise. Time and distance units are stated in column names wherever applicable.

## `baseline/`

| File | Description |
|---|---|
| `baseline_target_line_operational_summary.csv` | Removed-route departures, vehicle kilometres, passenger kilometres, boardings, occupancy, and related operational measures by case. |
| `target_trip_match_quality.csv` | Aggregate match counts and match rates for baseline target-line journeys. |

## `scenarios/`

The scenario subfolders contain the same recurring aggregate files.

| File | Description |
|---|---|
| `convergence.csv` | Change between the two final iteration windows for selected diagnostics. |
| `drt_adoption_summary.csv` | Legacy DRT adoption output. The archived journey-key count and share are doubled and must not be treated as unique journeys; see the README. |
| `drt_kpi_canonical.csv` | Legacy canonical DRT summary of final-window means. The archived idle fields are invalid fleet-size placeholders, and `drt_occupied_vkt_km` is mislabeled passenger-distance rather than occupied vehicle distance; see the README. |
| `drt_kpi_raw_final_window.csv` | Aggregated raw DRT outputs for iterations 181–200. |
| `drt_mode_origins.csv` | Baseline main modes of DRT-containing intervention journeys. |
| `equity_group_definitions.csv` | Income-group reference and cut points. |
| `equity_target_trip_behaviour.csv` | Group-level target-route retention, car switching, journey-time, and waiting outcomes. |
| `equity_utility_target_riders.csv` | Group-level utility-change summaries for affected travellers. |
| `mode_transitions_original_target_bus_trips.csv` | Final modes of original target-route journeys. |
| `mode_transitions_relevant.csv` | Aggregate mode-transition matrix for the relevant comparison cohort. |
| `system_main_mode_share.csv` | Whole-system main-mode counts and shares. |
| `time_of_day_trip_impacts.csv` | Hourly aggregate journey-time and waiting outcomes. |
| `trip_outcome_summary.csv` | Journey-time, waiting-time, departure-shift, and distance summaries by cohort. |
| `utility_summary.csv` | Utility-change distribution summaries by cohort. |

The `scenarios/` root also contains:

| File | Description |
|---|---|
| `analysis_inventory.csv` | Scenario-level counts of affected people, target journeys, DRT users, and matched rows. |
| `B0_convergence.csv` | Baseline convergence diagnostics. |
| `B0_system_mode_share.csv` | Baseline whole-system main-mode counts and shares. |

## `network/`

| File | Description |
|---|---|
| `B0_network_summary.csv` | Baseline daily road-network totals. |
| `B0_network_by_hour.csv` | Baseline road-network totals by hour. |
| `<scenario>/network_summary.csv` | Daily network totals for A8-FM, B6-PTI, or C22-PTI. The B/C `drt_regex_*` zeros reflect an ID-detection limitation; see the README. |
| `<scenario>/network_by_hour.csv` | Hourly network totals for A8-FM, B6-PTI, or C22-PTI. |
| `network_comparison_vs_B0.csv` | Absolute and relative network changes against B0. |

## `rq_outputs/`

| File | Description |
|---|---|
| `RQ1_context_suitability_A_B_C.csv` | Integrated comparison of A8-FM, B6-PTI, and C22-PTI. |
| `RQ2_caseA_intervention_design.csv` | Integrated comparison of the eight Case A service designs. |
| `RQ2_fleet_sensitivity_FL.csv` | Case A fleet comparison under FL pricing. |
| `RQ2_fleet_sensitivity_FH.csv` | Case A fleet comparison under FH pricing. |
| `RQ2_pricing_chain_8veh_FM_SUB1_FL_FH.csv` | Eight-vehicle pricing comparison. |
| `RQ3_original_bus_trip_mode_transitions.csv` | Aggregate final-mode outcomes for original target-route journeys. |
| `RQ3_DRT_mode_origins.csv` | Aggregate baseline origins of DRT-containing journeys. |
| `RQ3_equity_utility.csv` | Utility outcomes by income, age, gender, and car availability. |
| `RQ3_equity_mode_and_journey.csv` | Mode and journey outcomes by equity group. |
| `RQ3_time_of_day_impacts.csv` | Time-of-day summaries across scenarios. |
| `all_scenario_summary.csv` | Wide integrated summary for all formal intervention scenarios. |
| `integrated_stakeholder_evidence_matrix.csv` | Compact evidence matrix used in cross-metric interpretation. |
| `ABC_analysis_coverage.csv` | Availability flags for the final A/B/C analysis components. |
| `BC_incremental_QA.csv` | Quality-assurance counts and checks for the incremental B/C analysis. |
| `data_availability_matrix.csv` | Scenario-level availability of network outputs. |
