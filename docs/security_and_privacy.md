# Security and Privacy Considerations

## 1. System Summary

The FIM24725 Coherent Receiver GUI is a web-based control system for a Fujitsu FIM24725 coherent optical receiver module, designed for use in an optical communications research laboratory. A FastAPI REST backend (`fuj_backend`) orchestrates hardware through two networked programmable power supply units (MP71050x, controlled via UDP) and an Arduino Uno R3 microcontroller (USB serial), while a Plotly Dash web frontend (`fuj_gui`) provides a real-time operator interface. Both services are containerised with Docker Compose and deployed on a Raspberry Pi 3 Model B.

The system serves a single lab technician operating locally or via Tailscale VPN. The primary sensitive asset is the physical hardware: incorrect voltage sequencing or out-of-range setpoints can cause permanent damage to the FIM24725 module. Secondary assets include operational telemetry, network configuration, and control-surface availability. Trust boundaries exist between browser and Dash frontend, frontend and FastAPI backend (HTTP), and backend and hardware devices (UDP and serial).

## 2. Threat Model Overview

Given the deployment context — a university research lab with restricted physical access — the most plausible threat actors are: a rogue or careless lab user with LAN access; a compromised device on the laboratory network; and, in a misconfiguration scenario, opportunistic internet-based attackers. The principal attack surfaces are the HTTP API (ports 8000 and 8050), the unauthenticated UDP PSU protocol on isolated subnets (10.10.10.x, 10.10.20.x), and the USB serial interface to the Arduino MCU.

The system is designed to be accessible remotely only through Tailscale VPN. Tailscale establishes a WireGuard-encrypted mesh network in which every device is authenticated against a central identity provider; traffic between nodes is end-to-end encrypted and never traverses the public internet, and access control lists (ACLs) restrict which tailnet members may reach specific ports (`docs/tailscale.md`, lines 54–75). Crucially, Tailscale achieves this without opening any inbound ports on the Pi — connections are established outbound through NAT traversal — so the Pi's listening services remain invisible to internet scanners regardless of the surrounding network topology.

The backend API binds to `127.0.0.1` only (`docker-compose.yml`, line 21), making it unreachable from the network — only the co-located Dash GUI can contact it. The GUI, however, binds to `0.0.0.0:8050` (line 51) so that it is reachable via the Tailscale interface for remote access. This means the GUI is the externally facing service, and the only one directly exposed if the network model is violated.

If that model is bypassed — for example, if a router port-forwarding rule is added to expose port 8050 without Tailscale, or if the Pi is placed on a network with a permissive firewall — the GUI becomes reachable by any internet host. Automated scanning tools (such as Shodan or Masscan) routinely discover newly exposed HTTP services within minutes, meaning the window between misconfiguration and exploitation can be extremely short. Although the backend API is not directly exposed, the GUI acts as a proxy to it: an attacker who can interact with the Dash UI can trigger startup, shutdown, and voltage-control actions through the browser interface. Furthermore, since the Pi bridges to the isolated PSU subnets via dedicated NICs, a compromised host could serve as a pivot point to mount further attacks inside the laboratory network — reaching not only the PSU control plane but any other devices on the lab's internal subnets. This internet-exposure scenario represents the highest-impact threat and motivates several of the considerations below.

The system handles no personal data or authentication credentials. Sensitive data is purely operational: hardware configuration parameters, real-time telemetry, and infrastructure addresses. The design explicitly forgoes application-layer authentication, relying on network-level access control through Tailscale VPN and physical network segmentation.

## 3. Key Security Considerations

The following analysis draws on the OWASP Application Security Verification Standard (ASVS) as a guiding framework, focusing on the categories most relevant to an embedded hardware-control system: access control, communication security, input validation, error handling, configuration management, and logging. Each consideration is grounded in specific evidence from the repository.

### 3.1 Absence of Application-Layer Authentication and Authorisation

**Why it matters here.** Every endpoint — including `POST /api/v1/startup`, `POST /api/v1/shutdown`, and all voltage-control routes — is accessible without authentication. The FastAPI application factory in `src/fuj_backend/api/app.py` (lines 149–197) configures CORS, trusted-host, and rate-limiting middleware, but no authentication layer. The dependency injection module (`api/deps.py`) provides the service instance unconditionally.

**Existing safeguards.** The backend API binds to `127.0.0.1` only (`docker-compose.yml`, line 21), so it is not directly reachable from the network — only the co-located Dash GUI can contact it. CORS is restricted to localhost origins (lines 171–177), and `TrustedHostMiddleware` rejects any request whose `Host` header is not `localhost` or `127.0.0.1` (lines 183–186). Together, these controls ensure that — within a browser context — only the Dash GUI server running on the same machine can make requests to the API. A browser on a remote machine, even one on the same LAN, cannot issue cross-origin requests to the API because the CORS preflight would be rejected. Rate limiting caps control operations at ten per minute. Remote access requires Tailscale VPN, providing WireGuard encryption and identity-verified access.

**Gaps and risks.** The localhost bind address is a strong network-level control for the API, but the Dash GUI itself binds to `0.0.0.0:8050` (line 51) and provides a browser-based interface to all API operations. CORS and trusted-host restrictions are browser-enforced mechanisms that govern how web browsers behave; they offer no protection against non-browser clients on the Pi itself. More critically, as discussed in the threat model, if port 8050 is exposed to the internet — through accidental port forwarding or a permissive firewall — any attacker who can reach the GUI can trigger hardware control actions through the browser interface. Since the Pi also bridges to the PSU subnets, a compromised host grants access to the entire hardware control plane. This is the system's most significant security gap.

**Recommended mitigation.** For multi-user or internet-adjacent deployment, introduce API-key or mutual-TLS authentication on the backend. As a minimum host-level hardening step, the `ufw` firewall rules documented in `docs/tailscale.md` (lines 90–102) should be applied to restrict port 8050 to the Tailscale interface only, ensuring that even if the Pi's LAN IP becomes routable, the GUI remains unreachable from untrusted networks. The trust assumption should be documented as a formal accepted risk, consistent with OWASP ASVS guidance on access control.

**Priority.** Severity: High. Likelihood: Low–Medium (depends on network configuration). Impact: High (hardware damage, full system compromise).

### 3.2 Unencrypted and Unauthenticated PSU Control Channel

**Why it matters here.** The `PsuTransportUDP` class in `src/fuj_backend/hardware/psu_hal.py` (lines 63–135) sends ASCII-encoded SCPI-like commands over raw UDP sockets with no encryption, integrity verification, or message authentication. Commands such as `VSET1:5.000` directly set rail voltages that can destroy the optical module if incorrect.

**Existing safeguards.** The PSUs reside on physically isolated subnets (10.10.10.x and 10.10.20.x) with dedicated NIC interfaces. Reply datagrams are validated against the expected source IP (line 116). Voltage bounds are enforced at the service layer before commands reach the PSU, and hardware-programmed OVP/OCP thresholds provide a final safety net.

**Gaps and risks.** UDP source addresses are trivially spoofable, so the IP check offers limited protection. The protocol includes no sequence numbers, nonces, or MACs. However, exploiting this requires physical access to the isolated PSU subnet or compromise of the Pi itself, substantially reducing practical likelihood.

**Recommended mitigation.** Physical network isolation is the appropriate control and should be documented as a deliberate security boundary. If PSU subnets are ever shared with other devices, firewall or VLAN segmentation should be introduced.

**Priority.** Severity: High. Likelihood: Low (physically isolated). Impact: High (hardware damage).

### 3.3 Plaintext HTTP Communication

**Why it matters here.** Communication in this system occurs over two HTTP hops: the user's browser to the Dash GUI (`0.0.0.0:8050`), and the Dash GUI to the FastAPI backend (`127.0.0.1:8000`). Because the backend binds to localhost, the second hop always remains on the loopback interface and is not observable on the network. The first hop, however — browser to GUI — traverses the physical network in plaintext whenever the user is not on the same machine.

**Existing safeguards.** The GUI-to-API link is inherently protected by the loopback bind. For the browser-to-GUI link, Tailscale provides WireGuard encryption so that remote access traverses an encrypted tunnel rather than the open network. Optional HTTPS termination via `tailscale serve` is documented in `docs/tailscale.md`.

**Gaps and risks.** No TLS termination is built into the application itself. When a user accesses the GUI remotely via Tailscale, the WireGuard tunnel encrypts the traffic end-to-end, but if Tailscale is not in use — for example, when accessing the GUI from another machine on the same LAN — the browser-to-GUI traffic (including any control actions the operator performs) travels in plaintext. An attacker on the same network segment could observe or modify this traffic via ARP spoofing or passive sniffing. OWASP ASVS recommends encrypted channels for all sensitive communications.

**Recommended mitigation.** For deployments where the GUI may be accessed from the LAN without Tailscale, place a reverse proxy with TLS termination (e.g., Caddy or nginx) in front of the Dash server, or apply the `ufw` firewall rules documented in `docs/tailscale.md` (lines 90–102) to restrict port 8050 to the Tailscale interface only.

**Priority.** Severity: Medium. Likelihood: Low (Tailscale mitigates). Impact: Medium.

### 3.4 Input Validation and Hardware Safety

**Why it matters here.** Incorrect voltage setpoints can permanently damage the FIM24725 module. The system implements three-layer defence-in-depth: Pydantic models in `src/fuj_backend/api/models.py` enforce strict bounds (`VoaRequest`: 0–4.8 V, `OaRequest`: 0.5–2.0 V, `GaRequest`: 0–3.3 V); the service-layer `RailController` clamps values and logs warnings; and PSU-programmed OVP/OCP thresholds provide a final safety net.

**Gaps and risks.** The `SweepRequest` model (lines 44–49) validates only the `channel` field. The `start`, `end`, `step`, and `dwell_ms` parameters have no bounds. A sweep with an extremely small step and large range would hold the service `RLock` indefinitely, blocking all API requests — a denial-of-service condition. Service-layer clamping prevents out-of-range voltages, but the unbounded duration remains exploitable.

**Recommended mitigation.** Add Pydantic constraints to `SweepRequest`: bound `start`/`end` to 0–3.3 V, require `step > 0`, and cap `dwell_ms` (e.g., 60 000 ms).

**Priority.** Severity: Medium. Likelihood: Medium. Impact: Medium (DoS, not hardware damage).

### 3.5 Error Message Information Disclosure

**Why it matters here.** The exception handler in `src/fuj_backend/api/exceptions.py` (lines 23–24) returns `str(exc)` verbatim in JSON responses. `VerificationError` messages include measured hardware values, and `BoundsError` messages reveal configured voltage limits — exposing internal configuration to any API consumer.

**Existing safeguards.** No stack traces are returned. The single-user deployment limits the audience.

**Gaps and risks.** If the API becomes accessible to untrusted consumers, these messages could reveal hardware configuration and operating limits, contrary to OWASP ASVS guidance on error handling.

**Recommended mitigation.** Log detailed exceptions server-side; return generic descriptions (e.g., "Verification failed") to clients. This can be implemented by adding a `user_message` property to each exception class.

**Priority.** Severity: Low. Likelihood: Low. Impact: Low–Medium (information leakage only).

### 3.6 Configuration Management

**Why it matters here.** Configuration is managed through Pydantic `BaseSettings` in `src/fuj_backend/config.py`, reading environment variables (prefix `FUJ_`) and supporting `.env` files — consistent with twelve-factor application design. The system contains no authentication secrets or database credentials; values are limited to infrastructure addresses and operational parameters.

**Gaps and risks.** The repository lacks a root `.gitignore` (only an empty `.devcontainer/.gitignore` exists), creating a risk that a `.env` file could be inadvertently committed. While no secrets are currently stored, this is a preventive concern aligned with OWASP ASVS configuration management guidance. Rate-limit values are documented in `Settings` but hardcoded in route decorators (`config.py`, lines 56–63), preventing runtime modification.

**Recommended mitigation.** Add a root `.gitignore` excluding `.env`, `logs/`, and `__pycache__/`.

**Priority.** Severity: Low. Likelihood: Low. Impact: Low.

### 3.7 Logging, Monitoring, and Audit Trail

**Why it matters here.** Three dedicated log files (`api.log`, `fim24725_service.log`, `psu_hal.log`) use daily rotation with 30-day retention (`app.py`, lines 65–78). A 500-line in-memory ring buffer is exposed via the unauthenticated `GET /api/v1/logs` endpoint.

**Existing safeguards.** Rotation and bounded retention prevent unbounded disk growth. The logs endpoint is rate-limited to 60 requests per minute. Consistent formatting with millisecond timestamps supports incident investigation.

**Gaps and risks.** The logs endpoint requires no authentication. Log files inherit default Docker permissions (typically 644). PSU IP addresses are logged at startup (`app.py`, line 111) and hardware measurements during operations — operational intelligence that could assist an attacker in understanding system configuration.

**Recommended mitigation.** Restrict log file permissions to 0640. If authentication is added, include the logs endpoint in the protected scope.

**Priority.** Severity: Low. Likelihood: Low. Impact: Low.

## 4. Privacy Discussion

The system processes no personal data. There are no user accounts, authentication credentials, session tokens, or personally identifiable information at any point in the data flow. All telemetry — peak indicator voltages, photodiode readings, PSU rail measurements — is purely equipment-specific. Log files record timestamped hardware events and infrastructure addresses but contain no user-identifiable content.

Data minimisation is inherently satisfied: only data required for hardware control is collected, transmitted, and stored. The 30-day rotating log retention provides implicit lifecycle management. No data leaves the local network unless Tailscale is configured, in which case it traverses an encrypted WireGuard tunnel. There are no third-party analytics or external API calls. From a privacy-by-design perspective, GDPR and similar regulations are not directly applicable — a positive property that should be preserved if the system evolves to include user accounts.

## 5. Conclusion

The most significant security consideration is the absence of application-layer authentication. The backend API is well-protected by its `127.0.0.1` bind address, but the Dash GUI on `0.0.0.0:8050` provides a browser-accessible interface to all hardware control operations. The system's security posture therefore depends on Tailscale VPN and network isolation — controls that operate outside the application boundary and can be invalidated by a single misconfiguration. If port 8050 were exposed to the public internet through accidental port forwarding or a permissive firewall, the GUI would provide unauthenticated access to hardware control, and the Pi's bridged PSU subnets would present a path for further lateral movement. Applying `ufw` rules to restrict port 8050 to the Tailscale interface is the most impactful single host-level hardening step available.

The second most notable consideration is the unencrypted, unauthenticated UDP channel used for PSU control. While the protocol offers no inherent security guarantees, the physical isolation of the PSU subnets provides an effective compensating control appropriate for the laboratory context — provided the Pi itself is not compromised.

On the positive side, the system demonstrates strong defensive engineering in areas that directly protect hardware safety: the three-layer input validation strategy, the strictly enforced state machine, the careful power-sequencing logic, and the Arduino firmware handshake with pin-readback verification all reflect a considered approach to safety-critical design. These patterns align well with OWASP ASVS principles of defence in depth and input validation at trust boundaries.

For prioritised improvement, the system would benefit from: (1) applying `ufw` firewall rules on the Pi host to restrict port 8050 to the Tailscale interface; (2) adding `SweepRequest` parameter validation to close the denial-of-service gap; (3) adding a root `.gitignore` to prevent accidental configuration exposure; and (4) documenting the no-authentication trust assumption as a formal accepted risk in the project's architecture decision records.
