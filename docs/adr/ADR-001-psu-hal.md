# ADR-001: PSU Hardware Abstraction Layer (PSU_HAL)

**Status:** Accepted  
**Date:** 2026-02-04  
**Authors:** Project Team  

---

## Context

This project requires programmatic control of multiple **Multicomp Pro MP710508 / MP710509** programmable power supplies deployed in a laboratory environment and accessed remotely from a server.

Key constraints and observations:

- Each PSU is a **networked physical instrument** with:
  - 4 independent output channels
  - A SCPI-like UDP command interface
- The PSU’s UDP implementation is **request/response**, but:
  - It does not support multiple outstanding queries
  - Replies are not tagged or correlated
- Empirical testing shows:
  - Reliable operation when the client binds its local UDP port to match the PSU’s configured device port
- Deployment will involve:
  - Multiple PSUs on the same network
  - A higher-level service/API that will call into this library
- Safety, clarity, and correctness are more important than raw throughput

---

## Decision

We will implement a **synchronous Hardware Abstraction Layer (HAL)** with the following design decisions:

### 1. Object model
- One `MP71050x` object represents **one physical PSU**
- One `Channel` object represents **one output channel (CH1–CH4)** bound to a specific PSU
- A `Channel` can only be created via `psu.channel(n)`, ensuring PSU/channel identity is never ambiguous

### 2. Transport separation
- Network communication details are isolated in a `PsuTransportUDP` class
- The PSU logic never directly manipulates sockets
- Alternative transports (USB, serial, TCP) may be added later without changing the public API

### 3. Command execution model
- All HAL calls are **synchronous and blocking**
- Commands to the same PSU are **serialized** (no interleaving)
- At most **one in-flight command per PSU** at any time
- Different PSUs may be controlled independently

### 4. Network addressing strategy
- Each PSU is assigned:
  - A static IP address
  - A unique UDP device port (e.g., 20001, 20002, …)
- The client binds its local UDP port to the same value as the PSU device port
- This prevents reply cross-talk and removes ambiguity when multiple PSUs are active

### 5. API design philosophy
- One method per conceptual operation (e.g. `set_voltage`, not `VSET1`)
- Parameters are expressed in **engineering units** (volts, amps, seconds)
- Channel selection is explicit and readable
- The HAL performs minimal validation; higher-level services enforce policies

### 6. Scope boundaries
- The HAL:
  - Exposes the full documented command surface of the PSU
  - Does **not** enforce safety policies or operating envelopes
- Network configuration commands (IP, DHCP, port) are logically separated and not part of normal operation paths
- Persistence, orchestration, and user-facing APIs are out of scope for this layer

---

## Consequences

### Positive
- Clear mental model: *PSU → Channel → Operation*
- No risk of command interleaving or reply mismatch
- Safe foundation for higher-level automation and server APIs
- Easy to reason about and test
- Compatible with threaded or async callers (via external adapters)

### Trade-offs
- Blocking calls may reduce throughput if a single PSU is heavily polled
- UDP sockets are created per command (simple but not maximally efficient)
- Validation and safety enforcement are deferred to higher layers

---

## Future considerations

- Optional async wrappers (`asyncio.to_thread`) may be added without changing the core API
- Transport reuse (persistent sockets) may be evaluated if performance becomes critical
- Formal safety rules and parameter validation may be layered on top
- Support for additional PSU models can reuse the same object model

---

## Notes

This ADR establishes the HAL as a **deterministic, minimal, and explicit boundary** between application logic and laboratory hardware. All future development should preserve the guarantees of:

- Clear PSU/channel identity
- Serialized execution per device
- Predictable network behavior

