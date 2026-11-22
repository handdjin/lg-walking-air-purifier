# Fixed Patrol versus AI Policy: Evaluation Report

## 1. Purpose and Checklist Mapping

This evaluation compares an AI-based destination policy with a fixed room-patrol policy under paired synthetic scenarios.

| Checklist item | Evidence |
| --- | --- |
| Define and record pollution and movement metrics | Sections 3–4; `per_room.csv`, `per_scenario.csv` |
| Compare multiple days/scenarios using tables | Sections 4–6; `summary.csv`, `paired_differences.csv` |
| Report unfavorable AI results and analyze limitations | Section 7 |

This evaluates operational air quality and movement, not model prediction MAE.

## 2. Experimental Conditions

- Result directory: `ai/evaluation_results/20261122_191230_447472/`
- Base repository revision: `c598cd37ea613576f02ac3336128e65acea4e919`
- scikit-learn version: `1.7.2`
- Event seed: `9100`
- Scenarios: nine independent virtual days, using day indices 0–8.
- Scenarios 1–6 use the normal activity schedule.
- Scenarios 7–9 use the late-dinner schedule.
- Each run lasts 24 virtual hours.
- Each paired run uses the same map, event schedule, initial state, movement speed, sensing rules, and purification rules.
- Ground truth is available to the evaluator only, not to either policy as hidden current observations.

The manifest records that the complete evaluation event schedules do not duplicate the existing 60-day dataset schedules.

### Compared Policies

**Fixed patrol**

Use Part B's implementation in `simulation/compare_patrol.py`:

- Repeat living room → kitchen → bedroom.
- Depart every 20 virtual minutes.
- Include actual travel time and measurement-based purification.

**AI policy**

Use Part B's `ai_tick()` with the saved forecasting model:

- Collect initial observations through patrol.
- Forecast room-level PM2.5 30 minutes ahead at 10-minute boundaries.
- Select destinations using predicted pollution and travel time.
- Use threshold 35 and travel weight 1.
- Preserve an active movement route.
- Use the same measurement-based purification rules as fixed patrol.

Both policies start with the same state and initial living-room observation.
Their startup visit behavior differs as part of their policies.
Therefore, this is a comparison of complete policies, not an isolated causal test of forecasting alone.

The training generator's 10/20/30-minute arrival intervals are training-data settings.
They are not the fixed-departure baseline used here.

## 3. Metric Definitions

Use 1,440 minute-end ground-truth samples per room, corresponding to virtual minutes 1–1440.

| Metric | Definition | Unit |
| --- | --- | --- |
| Mean PM2.5 | Equally weighted average across rooms and sampled times | µg/m³ |
| Threshold room-minutes | Sum of room samples strictly above 35 | room-minutes |
| Excess PM2.5 room-minutes | Sum of `max(PM2.5 - 35, 0)` over sampled room-minutes | (µg/m³) × room-minutes |
| Travel distance | Actual grid cells traversed | cells |
| Completed trips | Recorded arrival events | trips |
| Movement requests | Recorded movement requests | requests |
| Moving time | Sum of virtual intervals in which movement occurred | minutes |
| Maximum observation age | Largest age of an existing observation in a run | minutes |

The threshold is strictly `PM2.5 > 35`, not `>= 35`.
It is an experimental setting, not a health standard.

Threshold duration and excess accumulation are one-minute approximations.
Room-minutes sum time across rooms and can exceed 1,440.
Without an occupancy model, they do not measure human exposure.

## 4. Aggregate Results

Values are means across the nine scenarios.

| Metric | AI | Fixed patrol |
| --- | ---: | ---: |
| Mean PM2.5 | 11.5155 | 11.8004 |
| Threshold room-minutes | 55.8889 | 54.6667 |
| Excess PM2.5 room-minutes | 585.6076 | 573.0689 |
| Travel distance, cells | 40 | 899 |
| Completed trips | 3 | 71 |
| Movement requests | 3 | 71 |
| Moving time, minutes | 6.6667 | 149.8333 |
| Maximum observation age, minutes | 1440.0000 | 49.8333 |

AI produced lower average concentration and less movement.
However, its average threshold duration and excess accumulation were higher.
The results do not establish overall AI superiority.

## 5. Scenario-Level Threshold Results

Values are room-minutes above 35.

| Scenario | Schedule | AI | Fixed patrol | Lower duration |
| --- | --- | ---: | ---: | --- |
| 1 | Normal | 30 | 49 | AI |
| 2 | Normal | 30 | 30 | Tie |
| 3 | Normal | 58 | 66 | AI |
| 4 | Normal | 72 | 50 | Fixed patrol |
| 5 | Normal | 24 | 65 | AI |
| 6 | Normal | 75 | 57 | Fixed patrol |
| 7 | Late dinner | 94 | 67 | Fixed patrol |
| 8 | Late dinner | 62 | 51 | Fixed patrol |
| 9 | Late dinner | 58 | 57 | Fixed patrol |

AI had shorter threshold duration in three scenarios, longer duration in five, and equal duration in one.

All three late-dinner scenarios had longer threshold duration under AI.
This is a descriptive finding from three cases, not proof that every shifted schedule will behave similarly.

## 6. Room-Level Results

Values are means across the nine scenarios.

| Room | AI mean PM2.5 | Fixed mean PM2.5 | AI minutes above 35 | Fixed minutes above 35 |
| --- | ---: | ---: | ---: | ---: |
| Living room | 10.9868 | 10.9868 | 0 | 0 |
| Kitchen | 12.4444 | 13.2994 | 55.8889 | 54.6667 |
| Bedroom | 11.1151 | 11.1151 | 0 | 0 |

Living-room and bedroom concentrations never exceeded 35 in these runs.
Threshold-duration differences therefore came from the kitchen.

A lower daily mean does not imply shorter high-pollution duration.
The indicators summarize different aspects of the concentration trajectory.

## 7. Limitations and Possible Explanations

### Stale observations

AI completed only three trips per day.
Its maximum observation age reached 1,440 minutes, compared with 49.83 minutes under fixed patrol.

Reduced travel is therefore not automatically a benefit: it can accompany insufficient reinspection.

### Difference from training conditions

The recorded maximum measurement age in training was 60 minutes.
Autonomous operation reached much older observations.

The model was also trained under reference patrol/purification conditions.
Different autonomous actions change the future concentrations being predicted.

These are plausible contributors to the observed limitations.
The evaluation does not isolate their causal effects.

### Threshold coverage

Only the kitchen crossed 35 in these scenarios.
Results should not be presented as demonstrating equivalent high-pollution handling across all three rooms.

### Experimental scope

- Nine synthetic scenarios provide descriptive evidence.
- No statistical significance or real-home effectiveness is established.
- Startup visit behavior differs between the complete policies.
- This evaluation does not replace separate prediction-MAE evaluation.

A future policy could investigate periodic reinspection when observations become stale.
If model or policy settings are changed using these results, use new held-out scenarios for a fresh final evaluation.

## 8. Reproduction and Output Files

From the project root:

```bash
python -m ai.evaluate_policies
```

Preserve the source code, saved model, model metadata, dataset configuration, and evaluation files.

Each execution creates a new timestamped directory.

| File | Purpose |
| --- | --- |
| `manifest.json` | Scenario settings, versions, model and source hashes |
| `scenarios.json` | Exact event schedules and maps |
| `per_scenario.csv` | 18 scenario-policy result rows |
| `per_room.csv` | 54 scenario-policy-room result rows |
| `minute_records.csv` | 25,920 rows, each containing three room concentrations |
| `summary.csv` | Mean results for each policy |
| `paired_differences.csv` | Nine paired AI-minus-fixed comparisons |
| `REPORT.md` | Automatically generated summary |

The reported means and threshold counts were independently recalculated from the uploaded minute records and matched.
The supplied evaluation script's hash matched the manifest.

## 9. Conclusion

Under these nine synthetic scenarios, the AI policy reduced average PM2.5 and movement compared with the 20-minute fixed-departure patrol, but did not reduce threshold duration or excess pollution accumulation on average.

Further work should address observation freshness and the difference between training conditions and autonomous operation.