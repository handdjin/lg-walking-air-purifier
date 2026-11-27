# Fixed Patrol versus AI Policy: Evaluation Report

## 1. Purpose and Checklist Mapping

This evaluation compares the backend's AI-based Auto Mode with a fixed room-patrol policy under paired synthetic scenarios.

| Checklist item | Evidence |
| --- | --- |
| Define and record pollution and movement metrics | Sections 3–4; `per_room.csv`, `per_scenario.csv` |
| Compare multiple days/scenarios using tables | Sections 4–6; `summary.csv`, `paired_differences.csv` |
| Report unfavorable AI results and analyze limitations | Section 7 |

This evaluates operational air quality and movement, not model prediction MAE.

## 2. Experimental Conditions

- Result directory: `ai/evaluation_results/20261127_144240_871979/`
- Code: local copy with the D* Lite pathfinding update. It was not a git checkout, so `base_revision` is recorded as `local-copy-not-a-git-checkout`. `manifest.json` records SHA-256 hashes of every source file, the model, and the dataset configuration.
- Model: `ai/artifacts/uniform20_model.joblib` (eight inputs, including history features), SHA-256 `e90cb07f…46b83bf`
- scikit-learn version: `1.7.2`
- Event seed: `9100`
- Scenarios: nine virtual days, using day indices 0–8, run **consecutively** in one home per policy.
- Days 1–6 use the normal activity schedule.
- Days 7–9 use the late-dinner schedule.
- Each day lasts 24 virtual hours. `Simulator.next_day()` starts the next day and keeps up to 14 previous days of measurements.
- Each paired day uses the same map, event schedule, initial state, movement speed, sensing rules, and purification rules.
- Ground truth is available to the evaluator only, not to either policy as hidden current observations.

The manifest records that the evaluation event schedules do not duplicate the generated dataset schedules.

### Compared Policies

**Fixed patrol**

Use `fixed_patrol_tick()` in `simulation/compare_patrol.py`:

- Repeat living room → kitchen → bedroom.
- Depart every 20 virtual minutes.
- Include actual travel time and measurement-based purification.

**AI policy (backend Auto Mode)**

Use `AutoModePolicy` in `simulation/compare_patrol.py` with the saved forecasting model. It mirrors `initial_patrol()` and `auto_decision()` in `backend/main.py` without the database:

- Visit rooms that have not been measured today.
- Forecast room-level PM2.5 30 minutes ahead at 10-minute boundaries, using previous-day measurements for the history features.
- Score rooms as predicted PM2.5 minus travel minutes and move to the best room predicted at 20 or above (travel weight 1).
- Stay at least 10 minutes after each arrival before moving again.
- When no room qualifies and the purifier is not purifying, revisit the room with the oldest reading once it is 120 minutes old (180 minutes after day 7).
- Preserve an active movement route.
- Use the same measurement-based purification rules as fixed patrol.

A nine-day check with the real model confirmed that `AutoModePolicy` and the backend's `advance_simulation()` produced identical move, arrival, measurement, and purification histories every day.

Both policies start each day with the same state and initial living-room observation.
Their startup visit behavior differs as part of their policies.
Therefore, this is a comparison of complete policies, not an isolated causal test of forecasting alone.

The training generator's 10/20/30-minute arrival intervals are training-data settings.
They are not the fixed-departure baseline used here.

## 3. Metric Definitions

Use 1,440 minute-end ground-truth samples per room, corresponding to virtual minutes 1–1440.

| Metric | Definition | Unit |
| --- | --- | --- |
| Mean PM2.5 | Equally weighted average across rooms and sampled times | µg/m³ |
| Threshold room-minutes | Sum of room samples strictly above 20 | room-minutes |
| Excess PM2.5 room-minutes | Sum of `max(PM2.5 - 20, 0)` over sampled room-minutes | (µg/m³) × room-minutes |
| Travel distance | Actual grid cells traversed | cells |
| Completed trips | Recorded arrival events | trips |
| Movement requests | Recorded movement requests | requests |
| Moving time | Sum of virtual intervals in which movement occurred | minutes |
| Maximum observation age | Largest age of an existing observation in a day | minutes |
| Forecast moves | Moves chosen from forecasts (AI only) | moves |
| Stale revisits | Moves to re-measure the oldest reading (AI only) | moves |

The threshold is strictly `PM2.5 > 20`, not `>= 20`. It matches the purification start level `PURIFY_ON`.
It is an experimental setting, not a health standard.

Threshold duration and excess accumulation are one-minute approximations.
Room-minutes sum time across rooms and can exceed 1,440.
Without an occupancy model, they do not measure human exposure.

## 4. Aggregate Results

Values are means across the nine days.

| Metric | AI | Fixed patrol |
| --- | ---: | ---: |
| Mean PM2.5 | 10.8659 | 11.2674 |
| Threshold room-minutes | 120.2222 | 136.8889 |
| Excess PM2.5 room-minutes | 1086.7306 | 1765.3952 |
| Travel distance, cells | 271.5556 | 899 |
| Completed trips | 21.5556 | 71 |
| Movement requests | 21.5556 | 71 |
| Moving time, minutes | 45.2593 | 149.8333 |
| Maximum observation age, minutes | 279.1481 | 49.8333 |
| Forecast moves | 2.5556 | – |
| Stale revisits | 17.0000 | – |

AI lowered mean PM2.5, threshold duration, and excess accumulation while traveling about 70% less than fixed patrol.
However, most AI moves were stale-reading revisits (17.0 per day) rather than forecast-driven moves (2.6 per day), and its readings became much older.

## 5. Day-Level Results

Threshold values are room-minutes above 20.

| Day | Schedule | AI | Fixed patrol | Lower duration | AI forecast moves | AI stale revisits |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| 1 | Normal | 221 | 145 | Fixed patrol | 1 | 13 |
| 2 | Normal | 119 | 108 | Fixed patrol | 3 | 12 |
| 3 | Normal | 118 | 138 | AI | 3 | 20 |
| 4 | Normal | 75 | 83 | AI | 3 | 21 |
| 5 | Normal | 63 | 131 | AI | 3 | 20 |
| 6 | Normal | 99 | 179 | AI | 2 | 20 |
| 7 | Late dinner | 67 | 140 | AI | 3 | 21 |
| 8 | Late dinner | 194 | 161 | Fixed patrol | 3 | 13 |
| 9 | Late dinner | 126 | 147 | AI | 2 | 13 |

AI had shorter threshold duration on six days and longer duration on three.

AI was worse on days 1, 2, and 8.
Days 1 and 2 have little or no measurement history, and from day 8 the stale-reading limit rises from 120 to 180 minutes, which reduced revisits from about 20 to 13 per day.
These are descriptive observations from a small number of days, not isolated causal effects.

## 6. Room-Level Results

Values are means across the nine days.

| Room | AI mean PM2.5 | Fixed mean PM2.5 | AI minutes above 20 | Fixed minutes above 20 |
| --- | ---: | ---: | ---: | ---: |
| Living room | 10.7052 | 10.6007 | 20.44 | 17.33 |
| Kitchen | 11.0000 | 12.6384 | 64.00 | 97.33 |
| Bedroom | 10.8924 | 10.5631 | 35.78 | 22.22 |

The overall improvement came from the kitchen, where cooking produces the largest pollution.
In the living room and bedroom, AI had slightly higher concentrations and longer threshold duration than fixed patrol.

A lower daily mean does not imply shorter high-pollution duration in every room.
The indicators summarize different aspects of the concentration trajectory.

## 7. Limitations and Possible Explanations

### Contribution of forecasts

AI made only 2.6 forecast-driven moves per day. The other 17 moves came from the stale-reading revisit, which works like a slower patrol.
This evaluation does not separate the effect of forecasts from the effect of revisits. A follow-up could compare Auto Mode with and without forecasts, or with a 120-minute fixed patrol.

### Stale observations

The maximum observation age averaged 279 minutes, compared with 49.83 minutes under fixed patrol.
Revisits run only when no room qualifies and the purifier is not purifying, so readings can grow older than the 120- or 180-minute limit.
Less frequent re-measurement is consistent with the longer threshold duration in the living room and bedroom.

### Difference from training conditions

The recorded maximum measurement age in training was 60 minutes.
Autonomous operation reached much older observations.

The model was also trained under reference patrol/purification conditions.
Different autonomous actions change the future concentrations being predicted.

These are plausible contributors to the observed limitations.
The evaluation does not isolate their causal effects.

### Experimental scope

- Nine consecutive synthetic days in one home provide descriptive evidence.
- No statistical significance or real-home effectiveness is established.
- Startup visit behavior differs between the complete policies.
- This evaluation does not replace separate prediction-MAE evaluation.

If model or policy settings are changed using these results, use new held-out scenarios for a fresh final evaluation.

## 8. Reproduction and Output Files

From the project root of a git checkout:

```bash
python -m ai.evaluate_policies
```

The script records `git rev-parse HEAD`, so it stops in a folder that is not a git repository.

When `backend/main.py` Auto Mode rules change, update `AutoModePolicy` in `simulation/compare_patrol.py` to match before rerunning.

Preserve the source code, saved model, model metadata, dataset configuration, and evaluation files.

Each execution creates a new timestamped directory.

| File | Purpose |
| --- | --- |
| `manifest.json` | Scenario settings, versions, model and source hashes |
| `scenarios.json` | Exact event schedules and maps |
| `per_scenario.csv` | 18 day-policy result rows |
| `per_room.csv` | 54 day-policy-room result rows |
| `minute_records.csv` | 25,920 rows, each containing three room concentrations |
| `summary.csv` | Mean results for each policy |
| `paired_differences.csv` | Nine paired AI-minus-fixed comparisons |
| `REPORT.md` | Automatically generated summary |

## 9. Conclusion

Over nine consecutive synthetic days, the backend's Auto Mode lowered mean PM2.5, threshold duration, and excess pollution accumulation compared with the 20-minute fixed-departure patrol, while traveling about 70% less.

The improvement came mainly from the kitchen, and most AI moves were stale-reading revisits rather than forecast-driven moves. The living room and bedroom fared slightly worse, and readings became much older than in training.
Further work should separate the contribution of forecasts from that of revisits and address the difference between training conditions and autonomous operation.
