# karabasan-simulation — UI Module

This directory contains the main entry point and UI layer for the **karabasan-simulation** project.

---

## Table of Contents

- [Module Structure](#module-structure)
- [Architecture Decisions](#architecture-decisions)
- [Prerequisites](#prerequisites)
- [Setup and Installation](#setup-and-installation)
  - [1. Clone the Repository](#1-clone-the-repository)
  - [2. Create the Virtual Environment](#2-create-the-virtual-environment)
  - [3. Activate the Environment](#3-activate-the-environment)
  - [4. Install Dependencies](#4-install-dependencies)
  - [5. Run the Application](#5-run-the-application)
- [Deactivation](#deactivation)
- [Notes](#notes)

---

## Module Structure

```
ui/
├── main.py                  # Entry point only — creates QApplication, launches MainWindow
├── main_window.py           # MainWindow class — layout assembly, wires everything together
├── components/
│   ├── __init__.py
│   ├── spectrum_panel.py    # Spectrum plot + waterfall heatmap (left panel)
│   ├── df_radar.py          # Compass/DF radar widget
│   ├── target_table.py      # ED target table
│   ├── et_panel.py          # ET attack buttons
│   └── log_console.py       # Log console widget + update_sigint_log logic
└── listeners/
    ├── __init__.py
    └── zmq_listener.py      # QThread listener — replaces RedisListener
```

---

## Architecture Decisions

| Decision | Reasoning |
|---|---|
| `components/` one file per panel | Each visual panel maps to exactly one file — easy to find, easy to replace. |
| `log_console.py` owns `update_sigint_log` | It's purely a display concern, so it lives with the widget that renders it. |
| `listeners/` is its own package | Swapping transports later (e.g. ZMQ → Redis) touches only this folder. |
| `main_window.py` as the wiring layer | It's the only file that imports from both `components/` and `listeners/`, keeping coupling explicit and contained. |
| `main.py` stays tiny | Just `QApplication` + `MainWindow` + `sys.exit` — no logic bleeds into the entry point. |

---

## Prerequisites

- **Python 3.8+** installed on your system
- `pip` available in your Python installation

---

## Setup and Installation

This project uses a virtual environment (`venv`) to manage dependencies in isolation. Since the virtual environment folder is **not tracked by Git**, every developer needs to create it locally once.

### 1. Clone the Repository

```bash
git clone <repository-url>
cd karabasan-simulation
```

### 2. Create the Virtual Environment

Create a local virtual environment in the project root:

```bash
python3 -m venv .venv
```

> This creates an isolated `.venv/` folder containing its own Python interpreter and package space, keeping your global Python environment clean.

### 3. Activate the Environment

You must activate the virtual environment before installing packages or running the app.

**Linux / macOS / WSL:**
```bash
source .venv/bin/activate
```

**Windows — Command Prompt:**
```bat
.venv\Scripts\activate.bat
```

**Windows — PowerShell:**
```powershell
.venv\Scripts\Activate.ps1
```

Once activated, your terminal prompt will be prefixed with `(.venv)`, confirming the environment is active.

### 4. Install Dependencies

Install all required packages (e.g. `numpy`, etc.) into the isolated environment:

```bash
pip install -r requirements.txt
```

### 5. Run the Application

Always run from the **project root directory** using the module flag so Python resolves imports correctly:

```bash
python3 -m ui.main
```

---

## Deactivation

When you are done, exit the virtual environment by running:

```bash
deactivate
```

---

## Notes

| Topic | Detail |
|---|---|
| Why `python3 -m ui.main`? | Running as a module from the project root ensures all relative imports within the `ui` package resolve correctly. |
| Why not commit `.venv/`? | Virtual environments are machine-specific and often large. Each developer creates their own from `requirements.txt`. |
| Updating dependencies | After adding a new package, run `pip freeze > requirements.txt` so teammates stay in sync. |