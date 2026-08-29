# Dissertation Framework Freeze — Final Analysis Version

## Working title
**Evaluating Demand-Responsive Transport as a Fixed-Route Bus Replacement Intervention: An Agent-Based Analysis of Context, Service Design and Distributional Effects in Greater Berlin**

## Research aim
This dissertation develops and tests a context-sensitive, agent-based framework for evaluating DRT as a fixed-route bus replacement intervention, examining how route conditions and service design affect passenger welfare, operational efficiency, behavioural adaptation and the distribution of impacts across travellers and the wider transport system.

## Frozen research questions

### RQ1 — Context and intervention suitability
**How does the effectiveness of DRT as a fixed-route bus replacement intervention vary across route and demand contexts characterised by demand intensity, fixed-route utilisation and passenger-flow structure, and what does this imply about the conditions under which DRT is more or less suitable?**

Primary comparison:
- B0 target service 890 -> A8-FM
- B0 target service 435 -> B6-PTI
- B0 target service X36 -> C22-PTI

A and C are the main conceptual contrast. B is a low-demand structural robustness case, not a third independent regime.

### RQ2 — Intervention design and mechanisms
**Within a context where DRT replacement is plausible, how do DRT service configuration and policy design—particularly fleet provision and fare structure, under calibrated vehicle capacity, operating hours and service constraints—shape the trade-offs between passenger welfare, service reliability, resource efficiency and system performance, and through what operational and behavioural mechanisms do these effects arise?**

Experimentally varied factors:
- Fleet provision: 4 / 8 / 12 in Case A
- Pricing / monetary treatment: FL / FH; at 8 vehicles FM / SUB1 / FL / FH

Calibrated or controlled design conditions, not independently identified causal effects:
- Vehicle capacity
- Operating hours
- Service area
- Maximum waiting / service constraints
- Vehicle type / operating configuration

Do not claim an independent capacity effect without a capacity sensitivity experiment.

### RQ3 — Behaviour, heterogeneity and equity
**How are the welfare and behavioural impacts of the DRT replacement intervention distributed across individual travellers, socio-demographic groups, modes, space and time, and to what extent do aggregate improvements conceal unequal burdens or unintended behavioural responses?**

Primary units of analysis:
- Same agent across B0 and intervention
- Same baseline target-bus trip across B0 and intervention
- Scenario DRT-containing trips and their B0 source mode
- Baseline target-line rider cohorts

## Frozen conceptual chain
**Route/demand context -> DRT intervention design -> service/operational response -> agent utility and behavioural adaptation -> system/distributional outcomes**

Socio-demographic and spatial heterogeneity condition the final distribution of impacts.

## Frozen evaluation dimensions

### 1. Passenger welfare and service quality — CORE
- Same-agent delta score / utility
- Better / worse / unchanged shares
- Journey-time change for matched trips
- Waiting time, P90/P95, maximum
- Rejection / reliability
- Service inequality: CV/Gini where appropriate

### 2. Operational and resource efficiency — CORE
- Served DRT requests / rides
- Fleet and capacity (design descriptors)
- Occupancy / sharing / pooling
- Idle vehicle availability
- Vehicle-hours where available
- Total DRT VKT
- Empty DRT VKT and empty-VKT share
- DRT VKT per served request
- DRT VKT relative to removed target-bus VKT where comparable

### 3. System and behavioural effects — CORE + SECONDARY
Core:
- Main-mode shares
- Exact trip-level mode transitions
- Original target bus -> DRT / other PT / car / walk / bike
- Car / active mode / other PT -> DRT
- Time-of-day behavioural/service effects

Secondary:
- Network road VKT
- Network delay / congestion proxy

### 4. Equity and distribution — CORE
- Utility distribution among baseline target-line riders
- Income, age, gender/sex, car availability and other reliable attributes when present
- Group-specific DRT adoption and journey-time changes
- Service inequality
- Spatial distribution of winners/losers using B0 home coordinates

### 5. Stakeholder/policy synthesis — SYNTHESIS, NOT AN ARBITRARY SCORE
- Passenger perspective
- Operator/resource perspective
- Public-authority/fiscal implications
- Network/system perspective
- Environmental implications
- Equity perspective

No arbitrary weighted composite suitability score will be constructed.

## Metric priority

### Mandatory core analysis
Utility, waiting, journey time, rejection/reliability, DRT demand, occupancy/pooling, idle availability, total/empty VKT, exact mode transitions, demographic equity, spatial winner/loser distribution.

### Secondary analysis
Network road VKT, network delay/congestion, time-of-day profiles, wait-time CV/Gini.

### Conditional analysis
- Direct emissions only if MATSim emission events are present.
- Monetised operator/government costs only if explicit defensible unit-cost assumptions are supplied.
- Otherwise VKT, vehicle-hours and fleet are reported as resource/fiscal implications rather than invented monetary precision.

## Interpretation rules that must not change after seeing results
1. B0 is the common counterfactual baseline and also the source of target-line cohorts.
2. RQ1 compares intervention effects relative to each case's own incumbent target bus, not raw A/B/C fleet numbers.
3. A8-FM, B6 and C22 form the cleanest structural comparison because the monetary treatment is aligned.
4. FL/FH versus B0 is a combined policy effect, not a pure DRT-technology effect.
5. Fleet and pricing are experimentally varied in Case A; capacity and operating conditions are calibrated controls.
6. Case C is not required to be worse. A favourable C result challenges/refines the framework; it does not invalidate the experiment.
7. Metrics will not be dropped or substituted ex post because their direction is inconvenient.
8. MATSim iterations are iterative/day-to-day behavioural adaptation toward a stable solution, not calendar-year long-term behaviour change.
9. Because the current model does not endogenously relocate activities/residences, analyse spatial distribution of affected OD demand and agents rather than claiming long-term OD/location-choice change.
10. Results chapters report evidence; the integrated judgement and literature comparison belong primarily in Discussion.
