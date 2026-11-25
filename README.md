# lg-walking-air-purifier

# Proactive AI Mobile Air Purifier

### AI-Based Proactive Autonomous Air Purification System

## 1. Project Overview

This project aims to develop a software-based simulation of an autonomous mobile air purifier that predicts future indoor air pollution and proactively moves to areas requiring air purification.

The system combines a virtual home, A* pathfinding, a Random Forest model, a FastAPI backend, and the LG Airy mobile app. The purifier uses forecasts to select destinations in Auto Mode and uses measured PM2.5 to determine whether to purify the air.

This project was developed as part of the Software Engineering course in the Department of Information Systems at Hanyang University, in collaboration with LG Electronics.


## 2. Key Technologies

| Category | Technologies |
|---|---|
| Mobile Application | React Native, Expo, TypeScript |
| Backend | Python, FastAPI, Uvicorn |
| Machine Learning | scikit-learn (Random Forest) |
| Data Processing | Pandas, NumPy |
| Pathfinding | A* Algorithm |
| Database | SQLite |
| Real-Time Communication | HTTP Polling (WebSocket planned) |
| UI/UX Design | Figma |
| Development Tools | VS Code, ChatGPT(Codex) |
| Version Control | Git, GitHub |
| Authentication | Amazon Cognito, AWS Amplify |
| Cloud Infrastructure | AWS EC2 |

## 3. Project Structure

The following tree shows the main directories and source files.

```text
lg-walking-air-purifier/
├── ai/
│   ├── generate_data.py          # Synthetic training data
│   ├── train_model.py            # Random Forest training
│   ├── predict.py                # PM2.5 forecasting
│   └── policy_evaluation_report.md
├── backend/
│   └── main.py                   # FastAPI endpoints and simulation loop
├── simulation/
│   ├── house_map.json             # Virtual home layout
│   ├── pathfinding.py            # A* navigation
│   ├── simulator.py              # Movement, measurement, and purification
│   └── controller.py             # AI destination selection
├── mobile/
│   └── src/
│       ├── app/
│       │   ├── login.tsx          # Cognito sign-in
│       │   └── (main)/
│       │       ├── index.tsx      # Home and simulation controls
│       │       └── explore.tsx    # Activity history
│       ├── components/airy/
│       │   ├── ui.tsx             # Shared UI components
│       │   └── floor-plan.tsx     # Map and live purifier position
│       └── lib/simulation.ts      # Shared API client
├── docs/                         # Course reports
└── README.md
```

## 4. Development Workflow

This repository is used for source code management, version control, and team collaboration.

- All team members currently collaborate on the shared `main` branch.
- Each team member is responsible for developing and maintaining their assigned components.
- Changes are recorded through Git commits with descriptive commit messages.
- Team members synchronize their local repositories using `git pull --rebase origin main` before pushing changes.
- Completed changes are uploaded using `git push origin main`.
- Merge conflicts are resolved carefully to avoid overwriting other team members' work.
- Project reports and documentation are maintained in the `docs/` directory.


## 5. Project Status

**Current Stage: Integrated Prototype and Validation**

The mobile app, FastAPI backend, forecasting model, and simulation are integrated. The prototype supports initial patrol, room-level measurements, 30-minute PM2.5 forecasts, AI-based destination selection, manual movement, measurement-based purification, and activity history.

The LG Airy mobile interface now includes Figma-based Sign In, Home, and History screens. Home uses live server data and shows distinct states for Auto Mode, Manual Mode, loading, and connection failure. A paired evaluation of the AI policy and fixed patrol is available in ai/.

Remaining validation includes testing Cognito sign-in and simulation controls together on a physical device, as well as checking connection recovery during a demo.

## 6. Team Members

| Member | Area | Responsibilities |
| --- | --- | --- |
| Haewon Kwon | Simulation | Environment modeling, pathfinding, movement, purification |
| Dongjin Son | Mobile App | App development, UI/UX design, visualization, device control |
| Yena Jo | Data & AI | Data generation, AI training, air quality prediction |

## 7. Documentation

Project reports, requirements, specifications, and related documentation will be maintained in the `docs/` directory.

Document revisions and development progress will be tracked through Git commit history.

## 8. How to Run

### 8.1 Hosted Backend

The FastAPI backend runs on Amazon EC2. The app connects to the hosted demo by default. To use a different deployment, set `EXPO_PUBLIC_SERVER_URL` in `mobile/.env.local`. If that deployment requires an API key header, set `EXPO_PUBLIC_API_KEY` there as well.

### 8.2 Mobile Application

From the repository root, run the following commands.

```bash
cd mobile
npm ci
npx expo start
```

Scan the QR code to open the project in Expo Go, then sign in with a provisioned Cognito account. The phone needs internet access to reach the EC2 backend.

### 8.3 API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/` | Check whether the FastAPI server is running. |
| `GET` | `/map` | Get the virtual home grid, room boundaries, and destination coordinates. |
| `GET` | `/status` | Get the purifier’s position, remaining route, operating mode, measurements, forecasts, and latest AI decision. |
| `GET` | `/predict` | Generate 30-minute PM2.5 forecasts from the current observations. |
| `GET` | `/history` | Get recorded movement, measurement, purification, and simulation events. |
| `POST` | `/mode` | Select Auto or Manual Mode. |
| `POST` | `/move` | Request a destination in Manual Mode. |
| `POST` | `/start` | Start or resume the simulation. |
| `POST` | `/pause` | Pause the simulation. |
| `POST` | `/reset` | Reset the simulation, event history, and AI state. |
| `POST` | `/step` | Advance the simulation by one step for testing while it is running. |

**Example mode selection request (`POST /mode`)**

```json
{
  "mode": "manual"
}
```

Supported modes are `auto` and `manual`.

**Example movement request (`POST /move`)**

```json
{
  "target_room": "kitchen"
}
```

Supported rooms:

- `living_room`
- `kitchen`
- `bedroom`

The EC2 backend advances the running simulation automatically, and the mobile app polls for updates.

---

## 9. Current Implementation

### 9.1 Virtual Home Simulation

- 2D grid-based home environment with three rooms.
- Defined walls, doors, obstacles, and walkable cells.
- A* pathfinding for autonomous navigation.
- Time-based indoor air pollution simulation.
- Automatic initial patrol and room-based air quality measurement.
- Air purification logic based on measured PM2.5 levels.
- Server-controlled simulation and movement.

### 9.2 AI Prediction and Decision-Making

- Generation of 60 days of virtual indoor air quality data.
- Random Forest model for 30-minute PM2.5 prediction.
- Prediction based on time, room information, previous measurements, and measurement age.
- Forecast evaluation at 10-minute simulation boundaries.
- In Auto Mode, the controller selects a destination based on predicted pollution and travel time when forecasts are available and the purifier has no active route.
- The AI policy and fixed patrol were compared across nine paired synthetic scenarios. The AI policy traveled less and slightly lowered mean PM2.5, while spending more time above the experimental threshold. [Policy evaluation report](ai/policy_evaluation_report.md)

### 9.3 Mobile Application

- Cognito sign-in and Figma-based Home and History screens.
- Live floor plan showing the purifier's position, destination, and route when available.
- Device status, simulation time, measured and forecast PM2.5, and AI destination decisions.
- Auto and Manual modes, manual destination selection, and start, pause, and reset controls.
- Loading and connection failure states with a reconnect action.
- Activity history showing movement, measurement, and purification events.

### 9.4 Backend Integration

- FastAPI runs a shared simulation and serves state, forecasts, and history through REST APIs. The mobile app polls for updates.
- A mode change requested during movement takes effect after the active route finishes.
- The backend stores simulation state, event history, and AI results in memory. A reset or server restart clears the previous run's history.

### 9.5 Future Development

- Verify Cognito sign-in, simulation controls, and reconnection on a physical device.
- Validate the full arrival, measurement, purification, and replanning cycle during demo testing.
