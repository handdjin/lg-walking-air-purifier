# Paired Policy Evaluation

Nine new synthetic scenarios: six normal and three late-dinner days.

Values are means per scenario.

| Metric | AI | Fixed patrol | AI minus fixed |
| --- | ---: | ---: | ---: |
| mean_pm25 | 11.5155 | 11.8004 | -0.2850 |
| room_minutes_above_35 | 55.8889 | 54.6667 | 1.2222 |
| excess_pm25_room_minutes | 585.6076 | 573.0689 | 12.5387 |
| distance_cells | 40.0000 | 899.0000 | -859.0000 |
| completed_trips | 3.0000 | 71.0000 | -68.0000 |
| move_requests | 3.0000 | 71.0000 | -68.0000 |
| moving_minutes | 6.6667 | 149.8333 | -143.1667 |
| max_observation_age_minutes | 1440.0000 | 49.8333 | 1390.1667 |

Threshold room-minutes: AI better on 3, worse on 5, tied on 1 scenarios.

Room-minutes sum durations across rooms and may exceed 1440.
They do not represent human exposure without an occupancy model.
Excess PM minutes sum max(PM - 35, 0) using 1-minute samples.
Travel distance is measured in actual grid cells.
Initial observations are identical, but startup patrol behavior differs as part of each policy.
Training measurement age is at most 60 minutes. Check operational ages before claiming reliability.
Lower movement is not automatically better purification; observations may become stale.
If policies are tuned using these results, use new scenarios for a fresh final evaluation.
These are simulation results, not verified real-home performance or prediction MAE improvements.
