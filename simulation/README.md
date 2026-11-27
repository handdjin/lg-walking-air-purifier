# Air Purifier Navigation and Air Quality Simulation

This Python package simulates a mobile air purifier in a home with a living room, kitchen, and bedroom. It tracks movement, simulated time, air quality, measurements, and automatic purification. The simulation core uses the Python standard library. Concentrations and thresholds are simulation assumptions rather than device performance ratings or health standards.

## Running the simulation

Run these commands from the project root, which contains the `simulation/` directory.

```sh
python3 -m simulation.demo
python3 -m simulation.integration_demo
python3 -m simulation.environment_demo
python3 -m simulation.controller_demo
python3 -m unittest discover -s simulation/tests -v
```

- `demo`: Shows the purifier moving from the living room to the kitchen, bedroom, and back to the living room. Use `--delay 0.2` to wait 0.2 real seconds between frames.
- `integration_demo`: Compares three scenarios: no pollution, cooking without a visit, and cooking with a purifier visit. Prints measurements and purification events and demonstrates pause and reset.
- `environment_demo`: Shows the air quality formula, activity schedule, and effect of purification in isolation.
- `controller_demo`: Uses sample forecasts to demonstrate destination selection, travel, and waiting.
- The tests cover navigation, environmental calculations, time boundaries, observation limits, automatic purification, destination selection, and reproducibility.

## Files

| File | Purpose |
|---|---|
| `house_map.json` | Defines rooms, walls, doors, obstacles, start position, and target cells |
| `house_map.py` | Validates the map and identifies the room at a coordinate |
| `pathfinding.py` | D* Lite shortest-path search with incremental replanning |
| `simulator.py` | Coordinates movement, time, measurements, purification, start, pause, and reset |
| `environment.py` | Provides air quality calculations and activity schedules for use by the simulator and data generator |
| `controller.py` | Selects a destination using predicted air quality and travel time |
| `controller_demo.py` | Demonstrates movement and waiting using sample forecasts |
| `compare_patrol.py` | `AutoModePolicy` mirrors the backend Auto Mode rules for evaluation; also compares it with a 20-minute fixed patrol for one day |
| `__init__.py` | `Simulator` public interface |
| `demo.py` | Demonstrates the map and navigation |
| `integration_demo.py` | Shows integrated behavior and comparison logs |
| `environment_demo.py` | Demonstrates environmental calculations in isolation |
| `tests/test_navigation.py` | Tests the map, shortest paths, movement, and D* Lite replanning around run-time obstacles |
| `tests/test_environment.py` | Tests air quality calculations, activities, and reproducibility |
| `tests/test_integration.py` | Tests interactions between time, control, measurements, and purification |
| `tests/test_controller.py` | Tests destination selection, error handling, and movement |
| `tests/test_compare_patrol.py` | Tests the Auto Mode mirror (initial patrol, stay after arrival, stale-reading revisit) and `next_day(late_dinner=...)` |

## Basic usage

```python
from simulation import Simulator

sim = Simulator(seed=42)
sim.move_to("kitchen")  # Reserve a route without moving yet
sim.start()             # Enable simulated time
while sim.get_state()["remaining_steps"]:
    sim.step()          # Move one cell and advance ten simulated seconds

print(sim.get_state())
sim.step()              # Time continues while waiting or purifying after arrival
sim.pause()             # Pause and preserve position, route, and time
sim.start()             # Resume
sim.reset()             # Restore the start position, midnight, and initial air quality, then remain paused
```

This loop is useful for a quick check. To display movement in the app, have a single server or app loop call `step()` at regular real-time intervals. The simulator has no real-time timer of its own.

## Time and update order

- The simulator starts paused after construction or reset. **Call `start()` before stepping.**
- By default, each `step()` advances ten simulated seconds and moves one cell if a route is active.
- Time continues while running, even without a route. The environment updates every simulated minute.
- While paused, `step()` preserves the state. `move_to()` can still reserve a route.
- The real-time call interval is independent of simulated time. Calling `step()` every 0.7 real seconds advances ten simulated seconds per call.
- The simulator stops at 24:00. Call `reset()` to run it again. For multi-day data generation, create a new environment for each day.

Each step performs the following operations in order.

1. Record the time spent purifying in each room over the previous ten seconds. Travel contributes no purification time.
2. At a minute boundary, apply emissions, natural decay, and accumulated purification to each room, in that order.
3. Move one cell if a route is active and update the clock.
4. Take a reading in the current room if the purifier has arrived or a periodic measurement is due.
5. Use the reading to decide whether to purify during the next interval.

An arrival between minute boundaries samples the most recently calculated concentration. For an arrival at 00:11:40, the measurement timestamp is 700 seconds and its `source_minute` is 11. The environment approximates concentration at one-minute intervals.

## Measurements and purification

- The purifier measures in its starting room, on arrival at a destination, and after ten minutes since the last reading while stationary.
- It does not measure in doorways or in rooms it passes through. It records at most one reading per room at a given time.
- An unmeasured room has `null` observation fields. After departure, the last reading stays in place and its age increases.
- A reading of 20 or higher starts purification. A reading of 15 or lower stops it. Between these values, the previous decision remains in effect.
- If the underlying concentration drops during purification, the decision stays in effect until the next measurement.
- Reserving a route that requires movement stops purification. A fresh reading on arrival determines what happens next.
- Pausing preserves the purification decision and suspends both purification and the clock.

`get_state()` exposes only observed air quality. The internal room concentrations from `get_ground_truth()` and future activities from `get_scenario()` are for evaluation and label generation. Keep them out of app observations and AI prediction inputs. Measurements and forecasts are separate values.

## Interface

| Function | Return value or behavior |
|---|---|
| `Simulator(seed=0, day_index=0, late_dinner=False, events=None)` | Create a reproducible simulation starting on virtual day one |
| `get_map()` | Return a copy of the map, room boundaries, targets, and start position |
| `get_state()` | Return a snapshot for the app or control policy without advancing time |
| `start()` | Enable simulation and return the state |
| `pause()` | Pause simulation and return the state |
| `reset()` | Reset the position, route, destination, clock, environment, observations, and history, then return the state |
| `next_day(late_dinner=None)` | Start the next virtual day after the current day ends and keep up to 14 previous days of measurements. `late_dinner` optionally switches the generated schedule from that day on; `reset()` restores the original setting |
| `move_to(room)` | Reserve a route from the current position and return the state |
| `set_blocked(cells, blocked=True)` | Close or reopen walkable cells at run time and replan an active route |
| `step()` | Advance one tick if running and return the state |
| `get_history()` | Return a copy of the command, arrival, measurement, and purification transition history |
| `get_ground_truth()` | Return a copy of the internal concentrations for evaluation |
| `get_scenario()` | Return a copy of the settings and activity schedule for reproducibility |
| `render_map()` | Return a text map showing the purifier's position |

`reset()` restores the initial position, destination, route, clock, and environment. Identical settings and commands reproduce the same results. Reset also returns the simulation to day one and discards the previous days of measurements. Immediately after reset, the history contains only the reset and the initial room measurement.

### State fields

| Field | Meaning |
|---|---|
| `simulation_day` | Virtual day number. Starts at 1, increases with `next_day()`, and returns to 1 after `reset()` |
| `current_room`, `room_name` | Current room ID and display name. In a doorway both are `null` |
| `position` | `[x, y]` coordinates |
| `destination` | Requested destination. Retained after arrival and reset to `null` |
| `status` | `moving`, `idle`, `purifying` indicate the current activity |
| `remaining_path`, `remaining_steps` | Remaining route and cell count, excluding the current cell |
| `blocked_cells` | Cells closed with `set_blocked()`. Empty by default |
| `simulation_time_seconds` | Elapsed simulated seconds |
| `environment_minute` | Last simulated minute processed by the environment |
| `tick_seconds` | Simulated seconds per tick. Default: 10 |
| `is_running` | Whether the simulation is running |
| `is_purifying` | Whether the running purifier is stationary and actively purifying |
| `is_measuring` | Whether a reading was taken in the last 20 simulated seconds while stationary. The app uses it for the measuring indicator |
| `finished` | Whether the simulated day has ended |
| `observations` | Last measurement in each room |

`status` is preserved during a pause. Use `is_running` for the pause indicator and `is_purifying` for active purification. Check `remaining_steps == 0` to determine whether the route is finished.

Each room has `pm25`, `measured_at_seconds`, `source_minute`, and `age_seconds`. Initially the living room has a reading of 10 at time zero. All four fields are `null` for the kitchen and bedroom. `age_seconds` counts simulated seconds since the last measurement.

An invalid room ID or unreachable destination raises `ValueError` or its subclass `NoPathError` and preserves the previous state. Modifying a returned snapshot does not affect internal state.

## Application integration

Keep a simulator instance alive to handle commands and state queries. The host application controls the update interval.

| Action | Call |
|---|---|
| Start or resume | `start()` |
| Pause | `pause()` |
| Reset | `reset()` |
| Set destination | `move_to(room)` |
| Start the next day | `next_day()` |
| Close or reopen cells | `set_blocked(cells, blocked=True)` |
| Advance one step | `step()` |
| Read state or map | `get_state()`, `get_map()` |

Use a single update loop and call `step()` while running, even without a route. Time and air quality continue to change after arrival. State queries do not advance the clock.

Use `is_running` for the running indicator and `is_purifying` for active purification. Display the readings and timestamps from `observations`. A `null` value means the room has not been measured. Refresh the screen with the state returned after reset.

State is stored in memory. Process commands and steps sequentially or protect concurrent updates with a lock. State is neither restored after a server restart nor shared between processes.

## Shared air quality calculations

All rooms start at 10 µg/m³. Each minute, apply these calculations in order.

```text
C1 = previous concentration + emission
C2 = C1 - max(C1 - 10, 0) × 0.01
Without purification: C2
With s seconds of purification: max(5, C2 × 0.95 ** (s / 60))
```

60 seconds of purification reduces concentration by 5%, subject to the floor. If the purifier arrives or leaves mid-minute, count only the seconds it actually purifies. For example, 20 seconds count as a partial minute. The effect is applied at the next minute boundary, so a room can show the effect of earlier purification after the purifier has left.

This approximation applies emissions, natural decay, and purification at minute boundaries. The data generator and simulator must use the same function and purification durations to reproduce results. The rule version is `pm25-v1.1`. Activity generation retains the `pm25-v1` seed version to preserve existing schedules.

Cooking adds 3 units per minute. Cleaning and making the bed each add 2. Overlapping activities add together. Pollution does not spread between rooms. Natural decay applies only to the concentration above 10.

| Activity | Room | Start window | Duration |
|---|---|---|---|
| Morning cooking | Kitchen | 07:00–09:00 | 10–20 min |
| Evening cooking | Kitchen | 18:00–20:00 | 10–20 min |
| Cleaning | Living room | 13:00–17:00 | 5–10 min |
| Making the bed | Bedroom | 07:00–10:00 | 5–10 min |

Times are drawn in whole minutes with both endpoints included. Activities run over the half-open interval `[start, end)`. Setting `late_dinner=True` shifts the dinner start window two hours later. Environmental randomness is independent of the visit schedule.

```python
from simulation.environment import AirEnvironment

env = AirEnvironment(seed=42, day_index=0)
env.advance()                               # Advance one minute without purification
env.advance(purifying_room="kitchen")         # Purify the kitchen for the full minute
# For a partial minute, supply only the time spent purifying while stationary
env.advance(purification_seconds={"kitchen": 20})
observation = env.sample_current_room("kitchen")
```

`AirEnvironment` requires callers using it directly to verify the purifier's location and purification time. `Simulator` handles both internally. Specify only one of `purifying_room` and `purification_seconds`. Total purification time across rooms must be at most 60 seconds per minute. Invalid inputs are rejected before the environment changes.

`calculate_pm25(current_pm25, emission=0.0, purifying=False)` and `advance(purifying_room=...)` support one-minute calculations. For partial purification, use `calculate_pm25(..., purifying=True, purifying_seconds=20)`.

## Map

15 columns and 11 rows form the grid. Coordinates are `[x, y]` with `[0, 0]` at the top left. The purifier moves horizontally or vertically, avoiding walls (`#`) and obstacles (`X`). Floors (`.`) and doorways (`D`) are traversable.

| Room ID | Display name | Target |
|---|---|---|
| `living_room` | Living room | `[2, 4]` (start position) |
| `kitchen` | Kitchen | `[11, 3]` |
| `bedroom` | Bedroom | `[11, 8]` |

Doorways at `[7, 3]` and `[7, 8]` belong to no room. Map edits take effect when a new simulator is created. Clients can display the same map using `get_map()`.

## Pathfinding (D* Lite)

`pathfinding.py` implements D* Lite on the four-connected grid with unit movement cost and a Manhattan-distance heuristic. The search runs backward from the goal and keeps its `g`/`rhs` estimates, so later changes repair only the affected cells instead of replanning from scratch.

```python
from simulation.house_map import load_house_map
from simulation.pathfinding import DStarLite, find_path

house = load_house_map()
path = find_path(house, house.start, house.rooms["kitchen"].target)  # One-shot query

planner = DStarLite(house, house.start, house.rooms["bedroom"].target)
route = planner.path()
planner.move_start(route[3])               # The purifier advanced three cells
planner.update_cells(blocked=[(7, 8)])     # The bedroom door closed
planner.update_cells(cleared=[(7, 8)])     # The door reopened
route = planner.path()                     # Repaired shortest path from the new start
```

- `find_path()` returns the shortest path including both endpoints and raises `NoPathError` when the goal is unreachable. The simulator and controller use this interface.
- `update_cells()` closes or reopens walkable map cells at run time. The goal cannot be blocked. `move_start()` must name a passable cell.
- When several shortest paths exist, the route may differ from the earlier A* implementation, but its length and travel time are the same.
- `Simulator` keeps one `DStarLite` instance per active route and calls `move_start()` after each step, so replanning during travel reuses the existing search.

### Run-time obstacles

No cells are blocked by default, so routes and results match the static map. Call `set_blocked()` to simulate a closed door or a temporary obstacle.

```python
sim = Simulator()
sim.start()
sim.move_to("kitchen")
sim.step()
sim.set_blocked([(7, 3)])                  # Close the kitchen door during travel
sim.set_blocked([(7, 3)], blocked=False)   # Reopen it
```

- Only walkable cells (`.` or `D`) can be blocked. Room targets and the purifier's current cell cannot. Invalid input raises `ValueError` and preserves the state.
- If a change affects the active route, D* Lite repairs the remaining route from the current cell and records `replanned`. Reopening a cell can also shorten the route.
- If no route remains, the purifier stops where it is, keeps `destination`, records `route_blocked`, and measures if it stopped inside a room. A later `move_to()` raises `NoPathError` until a route opens.
- `move_to()`, `estimate_travel_seconds()`, and `choose_destination()` all avoid blocked cells. `get_state()["blocked_cells"]` lists them.
- `reset()` and `next_day()` clear all blocked cells. Blocking and reopening are recorded as `cells_blocked` and `cells_cleared` in the history.

## Forecast-based destination selection (initial policy)

`controller.py` selects a destination using externally supplied **30-minute forecasts** made at the same time. Training and inference take place outside the controller. `controller_demo.py` uses example predictions to demonstrate its behavior.

```sh
python3 -m simulation.controller_demo
```

### Selection rules

1. Find a D* Lite route from the current position to each room's target. Selecting the current room means staying in place, so its travel time is zero.
2. Travel time in seconds equals the number of cells to move times `tick_seconds` (default 10 seconds).
3. Consider reachable rooms whose predicted PM is at least `threshold`, initially 35.
4. Score = predicted PM − travel time in minutes × `travel_weight`. The default weight of 1 subtracts one point per minute of travel.
5. Choose the highest score. Break ties by shorter travel time, then by room ID in alphabetical order.

The backend passes 20 for automatic movement. The standalone controller defaults to 35 when a caller omits the threshold. The default travel weight is 1. The threshold applies to **predicted PM**. An eligible room can win even with a negative score.

### Example call

```python
from simulation import Simulator
from simulation.controller import choose_destination, decide_and_move

sim = Simulator(seed=42)
# Example 30-minute room forecasts for PM2.5
predictions = {"living_room": 20.0, "kitchen": 60.0, "bedroom": 40.0}

preview = choose_destination(sim, predictions)  # Preview the decision without changing state
result = decide_and_move(sim, predictions)      # Call move_to() if another room is selected
print(result["decision"]["target_room"])       # kitchen

sim.start()
while sim.get_state()["remaining_steps"]:
    sim.step()
```

`decide_and_move()` reserves a route without advancing time or starting the simulator. A running simulation continues running. A paused simulation moves only after it is started. The application's single update loop advances the steps.

### Return values and exceptions

`choose_destination()` returns a decision snapshot with the following fields.

- `action`: reserve travel to another room with `move`, remain in the current room with `stay`, or leave the destination unchanged with `wait`.
- `target_room`: selected room ID or `null`.
- `reason`: `highest_score`, `current_room_selected`, `all_predictions_below_threshold`, `no_reachable_candidate`.
- `decided_at_seconds`: simulated time of the decision.
- `prediction_horizon_minutes`: 30.
- `threshold`, `travel_weight`: settings used for this decision.
- `rooms`: predicted PM, reachability, travel steps and seconds, score, and eligibility for each room. Travel cost and score are `null` for unreachable rooms.

`decide_and_move()` returns a dictionary with `decision` and `state`. `get_state()` does not store the decision. Forward it to the server or app and clear any server-side copy on reset.

`stay` and `wait` reserve no new movement. Time continues, purification keeps its current setting, and the previous `destination` remains visible. Use `decision.target_room` to display the newly selected target. The simulator switches purification based on actual measurements. A high forecast alone does not start purification.

Missing or unknown rooms and invalid predictions (`None`, negatives, infinity, NaN, strings, or booleans) raise `ValueError` and preserve the previous state. Supply a finite, nonnegative Python `int` or `float` for each room. Convert model outputs to `float` in the integration layer if needed.

When a room lacks a prediction, the caller must first gather initial readings or apply the model's missing-data policy. Do not substitute hidden concentrations or zero. The controller does not initiate the initial patrol.

### Execution and model integration

The controller selects a destination and reserves a route while stationary. An outstanding route prevents another decision even while paused. Decisions are also rejected after the day ends. Invalid requests preserve an existing route.

Convert external forecasts to the input format above. Use `age_seconds / 60` for elapsed minutes and match the units used in training. Keep future events and unobserved concentrations out of the forecast inputs. Predictions carry no timestamp, so the caller must ensure they correspond to the current state.

Model inference, the decision interval, choosing a new destination during travel, the HTTP API, and rendering are handled outside this module. Repairing a route around run-time obstacles is handled by `Simulator` (see Pathfinding). The server must serialize decisions, route reservations, and other state changes.
