# FUJ Coherent Receiver GUI

This project is a containerized control and monitoring application for a coherent receiver system.  
It is designed to safely interface with sensitive laboratory equipment through a validated backend, while supporting multiple user interfaces (desktop GUI now, web interface later).

---

## Project Goals

- Provide a **robust, safe control interface** for hardware with strict parameter limits
- Support both:
  - a **local desktop GUI** (PySide6 / Qt)
  - a **future web-based interface**
- Ensure **all control logic and validation** lives in a single backend
- Be **fully reproducible** using Docker on Linux systems

---



