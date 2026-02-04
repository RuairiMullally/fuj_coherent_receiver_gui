# FUJ Coherent Receiver GUI

A web-based control system for coherent receiver hardware, combining FastAPI backend with a Dash-based interactive frontend in a single application.

---

## Project Status

This project has been initialized with the development infrastructure. The source code is ready to be built with a clear architectural vision.

**Verified Tech Stack:**
- FastAPI + Dash integration using WSGIMiddleware ✓
- Single-process, single-port application ✓
- Docker and dev container configuration ✓

---

## Quick Start

### Development Setup

The project includes a VS Code dev container with all dependencies pre-configured:

1. Open in VS Code
2. Click "Reopen in Container" when prompted
3. Wait for the container to build

### Manual Setup

```bash
# Install dependencies
pip install -e .

# Run the application (once implemented)
python -m fuj_backend.main
```

**Planned Access Points:**
- **Web Dashboard:** http://localhost:8000/dashboard/
- **API Documentation:** http://localhost:8000/docs
- **REST API:** http://localhost:8000/api/*

---

## Project Goals

- Provide a **robust, safe control interface** for coherent receiver hardware
- **Web-based GUI** accessible from any browser (local or remote)
- Ensure **all control logic and validation** lives in a single backend
- **Single unified application** - no separate frontend/backend processes
- Be **fully reproducible** using Docker on Linux systems

---

## Planned Architecture

This application will use a **unified architecture** where the FastAPI backend and Dash frontend run in a single process:

```
┌─────────────────────────────────────────────┐
│  Browser → http://localhost:8000            │
│                                             │
│  /dashboard/  → Dash Web UI (WSGI)         │
│  /api/*       → FastAPI REST API (ASGI)    │
│  /docs        → Interactive API docs        │
└─────────────────────────────────────────────┘
                      ↓
        ┌─────────────────────────┐
        │   Safety Manager        │
        │   - Validation          │
        │   - Rate Limiting       │
        └─────────────────────────┘
                      ↓
        ┌─────────────────────────┐
        │   Hardware Layer        │
        │   - Simulator (dev)     │
        │   - Real HW (prod)      │
        └─────────────────────────┘
```

**Key Integration:** FastAPI (ASGI) hosts Dash (WSGI) using `WSGIMiddleware`, allowing both to run in one process on one port.

---

## Project Structure

```
src/
├── fuj_backend/              # FastAPI backend (to be implemented)
│   ├── api/                  # REST API endpoints
│   ├── hardware/             # Hardware drivers & safety
│   ├── models/               # Pydantic models
│   ├── config.py             # Configuration
│   └── main.py              # Application entry point
│
└── fuj_gui/                  # Dash frontend (to be implemented)
    ├── app.py                # Dash app factory
    ├── layout.py             # UI components
    ├── callbacks.py          # Interactive callbacks
    └── api_client.py         # Backend API client
```

---

## Running with Docker

```bash
# Using docker-compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

---

## Configuration

Set via environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `false` | Enable debug mode and auto-reload |
| `HARDWARE_MODE` | `simulator` | Use `simulator` or `real` hardware |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `NUM_CHANNELS` | `8` | Number of hardware channels |

**Example `.env` file:**
```bash
DEBUG=true
HARDWARE_MODE=simulator
PORT=8000
```

---

## Technology Stack

- **Backend:** FastAPI 0.115+, Uvicorn, Pydantic
- **Frontend:** Dash 2.18+, Dash Bootstrap Components
- **Integration:** Starlette WSGIMiddleware (ASGI ↔ WSGI bridge)
- **API Client:** HTTPX
- **Containerization:** Docker, Docker Compose

---

## Development Tools

- **Dev Container:** Pre-configured VS Code development environment
- **Docker:** Containerized deployment for Linux systems
- **Python 3.12+:** Modern Python features and performance

---

## Next Steps

1. Define the hardware control requirements
2. Implement the backend API structure
3. Create the hardware abstraction layer
4. Build the Dash-based web interface
5. Integrate safety and validation layers

---

## License

[Add license information]

---

## Contributing

[Add contribution guidelines]
