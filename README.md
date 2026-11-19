# lg-walking-air-purifier

# Proactive AI Mobile Air Purifier

### AI-Based Proactive Autonomous Air Purification System

## 1. Project Overview

This project aims to develop a software-based simulation of an autonomous mobile air purifier that predicts future indoor air pollution and proactively moves to areas requiring air purification.

The system integrates machine learning, autonomous pathfinding, and a mobile application to demonstrate proactive air purification in a virtual home environment.

This project is developed as part of the Software Engineering course in the Department of Information Systems at Hanyang University, in collaboration with LG Electronics.

## 2. Key Technologies

| Category | Technologies |
|---|---|
| Mobile Application | React Native, Expo, TypeScript |
| Backend | Python, FastAPI |
| Machine Learning | scikit-learn (Random Forest) |
| Data Processing | Pandas, NumPy |
| Pathfinding | A* Algorithm |
| Database | SQLite |
| Real-Time Communication | HTTP Polling (WebSocket planned) |
| UI/UX Design | Figma |
| Development Tools | VS Code, ChatGPT(Codex) |
| Version Control | Git, GitHub |

## 3. Project Structure

The following directory structure is planned and may be updated during development.

```text
ai-mobile-air-purifier/
├── mobile/          # React Native application
├── backend/         # FastAPI backend
├── ai/              # AI model
├── simulation/      # Virtual environment simulation
├── docs/            # Project reports and documentation
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

Detailed Git instructions are provided in Section 10.

## 5. Project Status

**Current Stage: Core Feature Integration**

The mobile application, FastAPI backend, AI prediction model, and autonomous navigation system have been successfully integrated.

The current prototype supports automatic initial patrol, room-based air quality measurement, 30-minute PM2.5 prediction, AI-based destination selection, and server-controlled autonomous movement.

The next development stages will focus on purification and replanning validation, activity history, UI/UX improvements, performance evaluation, and system testing.

## 6. Team Members

| Member | Department | University | email |
|---|---|---|---|
| Haewon Kwon | Department of Information Systems | Hanyang University | hw030302@hanyang.ac.kr |
| Dongjin Son | Department of Information Systems | Hanyang University | djson322@hanyang.ac.kr |
| Yena Jo | Department of Information Systems | Hanyang University | yena1743@hanyang.ac.kr |

## 7. Documentation

Project reports, requirements, specifications, and related documentation will be maintained in the `docs/` directory.

Document revisions and development progress will be tracked through Git commit history.

## 8. How to Run

### 8.1 Start the FastAPI Backend

Open a terminal and navigate to the project root directory.

```bash
source backend/.venv/bin/activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

The backend server will run on port `8000`.

API documentation is available at:

`http://127.0.0.1:8000/docs`

### 8.2 Start the Mobile Application

Open a separate terminal.

```bash
cd mobile
npm install
npx expo start
```

Scan the QR code using Expo Go on an iPhone.

**Network Requirements:**

- The iPhone and development computer must be connected to the same Wi-Fi network.
- The FastAPI backend must be running.
- The `SERVER_URL` in `mobile/src/app/index.tsx` must match the development computer's local IP address.

To check the local IP address on macOS:

```bash
ipconfig getifaddr en0
```

Example:

```tsx
const SERVER_URL =
  Platform.OS === 'web'
    ? 'http://127.0.0.1:8000'
    : 'http://YOUR_LOCAL_IP:8000';
```

Replace `YOUR_LOCAL_IP` with the computer's current IP address.

### 8.3 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Check whether FastAPI is running |
| GET | `/map` | Retrieve the virtual home map |
| GET | `/status` | Retrieve the current state, measured air quality, AI predictions, and destination decisions |
| GET | `/predict` | Retrieve 30-minute PM2.5 predictions |
| POST | `/move` | Manually set a destination and calculate the movement path |
| POST | `/step` | Advance the simulation by one step for testing |
| POST | `/start` | Start or resume the simulation |
| POST | `/pause` | Pause the simulation |
| POST | `/reset` | Reset the simulation and AI decision data |

**Example movement request:**

```json
{
  "target_room": "kitchen"
}
```

Supported rooms:

- `living_room`
- `kitchen`
- `bedroom`

The backend automatically advances the simulation while it is running. The mobile application retrieves the latest state through HTTP polling without repeatedly calling `/step`.
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
- Automatic prediction and destination evaluation every 10 simulation minutes when the purifier is not moving.
- Destination selection based on predicted pollution levels and travel time.
- Autonomous movement toward the selected destination.

### 9.3 Mobile Application

- Interactive grid-based home map.
- Automatic visualization of the purifier's current position.
- Start, pause, and reset controls connected to the backend.
- Display of the current room, coordinates, operating status, and remaining movement steps.
- Display of the current simulation time.
- Separate display of measured and AI-predicted PM2.5 values.
- Display of AI-selected destinations and decision reasons.
- Server connection error messages.

### 9.4 Backend Integration

- FastAPI integration with the simulator, AI prediction model, and destination controller.
- Automatic simulation progression through a server-side loop.
- REST APIs for simulation control and state retrieval.
- Storage of the latest AI prediction and destination decision in memory.
- Automatic state synchronization through HTTP polling.
- Error handling for invalid requests and simulation failures.

### 9.5 Future Development

- Validation of arrival, measurement, purification, and replanning.
- Separate measurement status visualization.
- Manual movement controls in the mobile application.
- Movement, measurement, and purification event history.
- UI/UX design improvements and screen navigation.
- Mobile connection recovery and restart testing.
- Performance comparison with a fixed patrol baseline.
- KPI evaluation and system optimization.
- Final integration testing, demonstration, and documentation.

**Current Limitations:** Core AI prediction and autonomous movement have been integrated and verified. However, the complete purification and replanning cycle requires further validation. Activity history, manual movement controls in the mobile application, and detailed UI/UX design are not yet completed. HTTP polling is currently used instead of WebSocket communication.

---

## 10. Git Workflow

### 10.1 Navigate to the Project Directory

Open a terminal and navigate to your local project directory.

```bash
cd lg-walking-air-purifier
```

Make sure you are in the project root directory before running Git commands.

### 10.2 Check Modified Files

```bash
git status
```

Review the modified and untracked files before staging changes.

### 10.3 Stage Changes

To stage all changes:

```bash
git add .
```

To stage a specific file:

```bash
git add mobile/src/app/index.tsx
```

Avoid committing unnecessary files, virtual environments, API keys, or environment variables.

### 10.4 Commit Changes

```bash
git commit -m "Describe your changes"
```

Example:

```bash
git commit -m "Add air quality UI and position polling"
```

Use meaningful commit messages that describe the implemented features.

### 10.5 Pull the Latest Changes

Before pushing, synchronize with the remote repository.

```bash
git pull --rebase origin main
```

If a merge conflict occurs, resolve the conflicting files and continue the rebase.

```bash
git add <resolved-file>
git rebase --continue
```

Do not push until all conflicts have been resolved.

### 10.6 Push to GitHub

```bash
git push origin main
```

### 10.7 Verify the Repository Status

```bash
git status
```

A successful synchronization should display:

```text
On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean
```

### 10.8 Useful Git Commands

| Command | Description |
|---|---|
| `git status` | Check modified and staged files |
| `git add .` | Stage all changes |
| `git commit -m "message"` | Create a commit |
| `git pull --rebase origin main` | Integrate the latest remote changes |
| `git push origin main` | Upload local commits |
| `git fetch origin` | Update remote repository information |
| `git log --oneline -10` | View the latest 10 commits |
| `git log --oneline --all --graph` | View the commit history across branches |

**Important Notes:**

- Always check `git status` before committing.
- Pull the latest changes before pushing.
- Never use `git push --force` on the shared `main` branch.
- Resolve merge conflicts carefully to avoid overwriting teammates' work.
- Use feature branches and pull requests when required by the team's collaboration workflow.
