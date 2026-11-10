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
| Real-Time Communication | WebSocket |
| UI/UX Design | Figma |
| Development Tools | VS Code, Claude Code |
| Version Control | Git, GitHub |

## 3. Project Structure

The following directory structure is planned and may be updated during development.

```text
ai-mobile-air-purifier/
├── mobile/          # React Native application
├── backend/         # FastAPI backend
├── ml/              # Machine learning model
├── simulation/      # Virtual environment simulation
├── docs/            # Project reports and documentation
└── README.md
```

## 4. Development Workflow

This repository is used for source code management, version control, and team collaboration.

- The `main` branch contains the stable version of the project.
- Each team member works on a separate feature branch.
- Changes are recorded through Git commits.
- Pull requests are used to review and merge changes.
- Project reports and documentation are maintained in the `docs/` directory.

## 5. Project Status

Current Stage: Initial Prototype Development

The initial mobile application, FastAPI backend, and room-based simulator have been implemented and successfully integrated.

The current prototype supports basic room status retrieval and movement commands. Advanced simulation, AI prediction, autonomous navigation, and real-time communication will be implemented in subsequent development stages.

## 6. Team Members

| Member | Department | University | email |
|---|---|---|---|
| Haewon Kwon | Department of Information Systems | Hanyang University | hw030302@hanyang.ac.kr |
| Dongjin Son | Department of Information Systems | Hanyang University | djson322@hanyang.ac.kr |
| Yena Jo | Department of Information Systems | Hanyang University | yena1743@hanyang.ac.kr |

## 7. Documentation

Project reports, requirements, specifications, and related documentation will be maintained in the `docs/` directory.

Document revisions and development progress will be tracked through Git commit history.

HEAD
## 8. How to Run

### 8.1 Simulation

Run the room-based simulator from the project root directory.

```bash
python3 -m simulation.demo
```

The simulator supports three rooms: `living_room`, `kitchen`, and `bedroom`.

### 8.2 FastAPI Backend

Create and activate a Python virtual environment if one has not already been configured.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install "fastapi[standard]"
cd ..
```

Start the backend server from the project root directory.

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

API documentation is available at:

`http://127.0.0.1:8000/docs`

**Available endpoints:**

- `GET /status`: Retrieve the current room from the simulator.
- `POST /move`: Move the simulated air purifier to the kitchen (temporary implementation).

### 8.3 Mobile Application

Open a separate terminal and run:

```bash
cd mobile
npm install
npx expo start
```

Open the application on an iPhone using Expo Go.

The mobile application communicates with the FastAPI backend through the development computer's local IP address and port `8000`.

The iPhone and development computer must be connected to the same local network, and the mobile application's server URL must match the computer's current IP address.

## 9. Current Implementation

The following features have been implemented and tested:

- React Native and Expo mobile application running on an iPhone.
- Basic mobile interface displaying the current room and a movement button.
- FastAPI backend with status retrieval and movement endpoints.
- Integration between FastAPI and the Python room-based simulator.
- Successful communication between the iPhone application, FastAPI server, and simulator.

**Future Development**

- 2D virtual home environment and coordinate-based movement.
- A* pathfinding and autonomous navigation.
- Synthetic air quality data generation and PM2.5 simulation.
- Machine learning-based pollution prediction.
- Automatic purification and proactive movement.
- Real-time updates and persistent data storage.


## How to Run

### 1. Start the Backend Server

From the project root:

```bash
source backend/.venv/bin/activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### 2. Start the Mobile App

Open a new terminal:

```bash
cd mobile
npx expo start
```

Scan the QR code using Expo Go on an iPhone.

Make sure the iPhone and Mac are connected to the same Wi-Fi network and that the SERVER_URL in mobile/src/app/index.tsx matches the Mac's local IP address.

### 3. Error Handling Tests

- Server unavailable: The app displays "Connection Failed".
- Invalid room: The backend returns HTTP 400 without changing the current room.
- Network connection failure: The app displays an error without crashing.

### 4. API Endpoints

- GET /status: Returns the current room.
- POST /move: Moves the purifier to the requested room.

Supported rooms:
- living_room
- kitchen
- bedroom

a7c71ef (docs: add run instructions and error handling tests)
