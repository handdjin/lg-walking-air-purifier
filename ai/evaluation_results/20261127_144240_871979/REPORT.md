# Paired Policy Evaluation

Nine new synthetic scenarios: six normal and three late-dinner days.

Values are means per scenario.

| Metric | AI | Fixed patrol | AI minus fixed |
| --- | ---: | ---: | ---: |
| mean_pm25 | 10.8659 | 11.2674 | -0.4015 |
| room_minutes_above_threshold | 120.2222 | 136.8889 | -16.6667 |
| excess_pm25_room_minutes | 1086.7306 | 1765.3952 | -678.6646 |
| distance_cells | 271.5556 | 899.0000 | -627.4444 |
| completed_trips | 21.5556 | 71.0000 | -49.4444 |
| move_requests | 21.5556 | 71.0000 | -49.4444 |
| moving_minutes | 45.2593 | 149.8333 | -104.5741 |
| max_observation_age_minutes | 279.1481 | 49.8333 | 229.3148 |
| forecast_moves | 2.5556 | 0.0000 | 2.5556 |
| stale_revisits | 17.0000 | 0.0000 | 17.0000 |

Threshold room-minutes: AI better on 6, worse on 3, tied on 0 scenarios.

Room-minutes sum durations across rooms and may exceed 1440.
They do not represent human exposure without an occupancy model.
Excess PM minutes sum max(PM - 20, 0) using 1-minute samples.
Travel distance is measured in actual grid cells.
Initial observations are identical, but startup patrol behavior differs as part of each policy.
Training measurement age is at most 60 minutes. Check operational ages before claiming reliability.
Lower movement is not automatically better purification; observations may become stale.
If policies are tuned using these results, use new scenarios for a fresh final evaluation.
These are simulation results, not verified real-home performance or prediction MAE improvements.
