# Air Quality Simulation and AI Dataset Specification

This document defines the shared rules for Data and AI part and Air Quality Simulation part.


## 1. Air Quality Update Rules

### Common settings

| Item | Specification |
| --- | --- |
| Rooms | `living_room`, `kitchen`, `bedroom` |
| Concentration unit | µg/m³ |
| Time unit | Virtual minutes |
| Environment update interval | 1 minute |
| Ground-truth recording interval | 10 minutes |
| AI sample interval | 10 minutes, after the initial patrol and subject to label availability |
| Daily initialization | Start in the living room at 00:00; initialize all room concentrations to 10 and clear observation state |

### Pollution events

| Room | Daily event | Start-time range | Duration | Increase per active minute |
| --- | --- | --- | --- | --- |
| Kitchen | Breakfast cooking, once | 07:00–09:00 | 10–20 minutes | 3 |
| Kitchen | Dinner cooking, once | 18:00–20:00 | 10–20 minutes | 3 |
| Living room | Cleaning, once | 13:00–17:00 | 5–10 minutes | 2 |
| Bedroom | Bedding arrangement, once | 07:00–10:00 | 5–10 minutes | 2 |

- Randomly select each start time and duration within its range at minute resolution.
- Events are active from the start time up to, but not including, the end time.
- Apply the same scheduling rules on all weekdays.
- Exclude inter-room pollution transfer, ventilation, and outdoor air inflow in the first version.

### Concentration update

Apply the following order every minute:

**Pollution increase → natural decay → purification**

```text
C = previous concentration
E = pollution increase during the current minute

C1 = C + E
C2 = C1 - max(C1 - 10, 0) * 0.01

If purification is active:
    next_concentration = max(5, C2 * 0.95)
Otherwise:
    next_concentration = C2
```

Natural decay also applies during pollution events. Concentrations at or below 10 do not decrease through natural decay and are not raised back to 10.

Calculate a 10-minute change by applying the one-minute update ten times with the appropriate conditions for each minute.

### Purification control

- Turn purification on when the measured concentration is at least 35.
- Turn it off when a new measurement during purification is at most 15.
- Between 15 and 35, retain the existing on/off state.
- Purification affects only the occupied room and stops affecting that room when the purifier leaves.
- Do not purify during movement.
- Do not delay scheduled visits because purification is active.

These values are experimental assumptions, not product specifications or health standards.

## 2. Prediction Time and Target Time

One dataset row represents one prediction for one room, 30 minutes ahead.

| Field | Definition | Example |
| --- | --- | --- |
| Prediction reference time | Current time when the prediction is made | 18:30 |
| Last measurement time | Most recent measurement time for the target room, available by the reference time | 18:10 |
| Measurement age | Reference time minus last measurement time | 20 minutes |
| Target time | Reference time plus 30 minutes | 19:00 |
| Target concentration | Simulator ground truth for the target room at the target time | Room concentration at 19:00 |

- Calculate the target time from the reference time, not the last measurement time.
- Create one row per room at each eligible reference time, giving three rows when all rooms are eligible.
- Use each room's latest available observation; the rooms are not measured simultaneously.
- If a measurement occurs at the reference time, update the observation before constructing the input.
- The label includes the effects of the predefined patrol and measurement-based purification policy. No additional AI-driven proactive rerouting is applied during this reference scenario.
- Exclude rows whose target time falls on the following day because each day is initialized independently.

## 3. Model Input Features and Label

| Input feature | Meaning |
| --- | --- |
| `room_id` | Target room |
| `hour` | Hour of the prediction reference time |
| `minute` | Minute of the prediction reference time |
| `last_measured_pm25` | Latest observed PM2.5 for the target room |
| `minutes_since_measurement` | Minutes since that observation |

Exclude weekday from the first model because the pollution rules do not vary by weekday.

Store the label separately as:

| Label | Meaning |
| --- | --- |
| `target_pm25_30min` | Ground-truth PM2.5 for the target room 30 minutes after the reference time |

Execution IDs, day numbers, reference times, and target times may be stored as metadata. Keep them separate from the selected model inputs; derive `hour` and `minute` from the reference time.

### Prohibited inputs

Do not provide the model with:

- Unobserved current ground-truth concentrations.
- Measurements obtained after the reference time.
- Future ground-truth concentrations, including the label.
- The exact future pollution-event schedule.
- Future random visit decisions unavailable at prediction time.

The simulator's knowledge must not be treated as information available to the purifier.

## 4. Separate Ground Truth and Observation Records

This separation prevents hidden simulator information from entering the model inputs.

### Ground truth: `ground_truth.csv`

| Column | Meaning | Example |
| --- | --- | --- |
| `run_id` | Simulation execution identifier | `run_001` |
| `scenario_day` | Virtual day number within the 60-day dataset | `8` |
| `timestamp` | Virtual time of the ground-truth state | `18:30` |
| `room_id` | Room identifier | `kitchen` |
| `true_pm25` | Ground-truth concentration | `40` |

Use this record to construct labels and evaluate results.

### Observations: `observations.csv`

| Column | Meaning | Example |
| --- | --- | --- |
| `run_id` | Simulation execution identifier | `run_001` |
| `scenario_day` | Virtual day number | `8` |
| `measured_at` | Virtual measurement time | `18:30` |
| `room_id` | Measured room | `kitchen` |
| `measured_pm25` | Observed concentration | `40` |

Use this record to construct model inputs and control measurement-based purification.

### Measurement rules

- Measure immediately on arrival.
- While remaining in the same room, measure again every 10 minutes after the last measurement.
- Record only one measurement for the same room and time if arrival and periodic measurement triggers overlap.
- For other rooms, retain the last measurement and its time without refreshing them from hidden ground truth.

The first version adds no sensor error. Therefore, a measurement equals the ground-truth concentration for that room at that instant. However, observation records contain only actual measurements, not all room states.

The proposed filenames and column names should be confirmed by A and B before implementation.

## 5. Rooms Without an Initial Measurement

- Keep an unmeasured room's latest value and measurement time missing.
- Represent missing values as empty CSV fields and interpret them as missing when loading the file.
- Do not replace missing values with zero.
- Begin constructing AI samples only after all three rooms have been measured at least once that day.
- Apply this rule to training, validation, and test data.

Measurements are recorded from the start of the patrol. Only AI sample construction waits for completion of the initial patrol.

### Basic-patrol example

| Time | Observation recorded | AI sample construction |
| --- | --- | --- |
| 00:00 | Living room | Not yet: kitchen and bedroom remain unmeasured |
| 00:10 | Kitchen | Not yet: bedroom remains unmeasured |
| 00:20 | Bedroom | Begin constructing room-level samples |

At 00:20, measurement ages are 20 minutes for the living room, 10 for the kitchen, and 0 for the bedroom. All three targets refer to 00:50.

At the start of each day, initialize ground-truth concentrations to 10 and clear observation state. Then perform the immediate living-room measurement at 00:00. Initializing a room's concentration does not count as measuring it.

## 6. Training, Validation, and Test Split

Generate 60 virtual days, then assign records to the following subsets.

### Patrol schedule

Repeat the room order:

**Living room → kitchen → bedroom**

Repeat daily patterns:

**Day 1: basic → Day 2: slow → Day 3: irregular → repeat**

| Pattern | Interval until arrival at the next room | Total days |
| --- | --- | --- |
| Basic | 10 minutes | 20 |
| Slow | 20 minutes | 20 |
| Irregular | Randomly select 10, 20, or 30 minutes for each interval | 20 |

These intervals are not travel time alone. The initial generator simplifies movement as a room change at the arrival time.

### Data allocation

| Subset | Virtual days | Days per patrol pattern | Purpose |
| --- | --- | --- | --- |
| Training | 1–42 | 14 each | Learn input–label relationships |
| Validation | 43–51 | 3 each | Select model settings |
| Final test | 52–60 | 3 each | Evaluate the selected model |

- Train one model using training samples from all three patrol patterns.
- Keep all records from one day in the same subset; do not randomly split rows.
- Exclude samples before the initial patrol is complete or whose targets cross the daily boundary.
- Do not use final-test data for training or model selection.
- On selected test days, change an activity pattern to evaluate robustness, such as moving dinner cooking to 20:00–22:00.
- Record the selected dates and changes before inspecting model training results.

The planned ground-truth table contains:

**60 days × 144 recording times per day × 3 rooms = 25,920 rows.**

This is neither the number of sensor observations nor the final number of AI samples.

## 7. Shared Air Quality Interface

### Proposed interface

```python
step_pm25(current_pm25, event_increase, purifying)
```

| Parameter or output | Meaning |
| --- | --- |
| `current_pm25` | Concentration before the update |
| `event_increase` | Pollution increase for the current minute |
| `purifying` | Whether purification is active in that room for the current minute |
| Return value | Concentration one minute later, calculated using Section 1 |

- Implement the function once and reuse it in both components.
- Apply it ten times to calculate a 10-minute change.
- Share event-generation, sensing, purification-control, and initialization rules.
- Use separate random seeds for pollution events and irregular visits. A seed makes random selections reproducible.
- Record the rules, seeds, and scenario version.
- When actual movement is integrated, measure at actual arrival times and exclude purification during travel. Regenerate data if necessary.
