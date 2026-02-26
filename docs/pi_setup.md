# Raspberry Pi Deployment Setup

Target hardware: Raspberry Pi 3 Model B — 64-bit Debian Trixie (arm64)

---

## Dependencies

- Docker (CE + Compose plugin)
- Tailscale

---

## 1. Install Docker

```bash
sudo apt-get update && sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/debian trixie stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

Log out and back in for the group change to take effect.

---

## 2. Install Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

The Pi will receive a stable Tailscale IP and (with MagicDNS) a hostname
reachable from anywhere on the tailnet.

---

## 3. Arduino udev rule

The Arduino Uno (FTDI FT232 chip, `0403:6001`) appears as `/dev/ttyUSBx`.
This rule gives it a stable device name regardless of what else is plugged in.

```bash
echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", SYMLINK+="arduino"' \
  | sudo tee /etc/udev/rules.d/99-arduino.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Verify (Arduino must be plugged in):

```bash
ls -la /dev/arduino   # should show: /dev/arduino -> ttyUSB0
```

> **Note:** `0403:6001` is the generic FT232 VID:PID shared by other FTDI
> devices. If multiple FTDI devices are connected simultaneously, make the
> rule more specific by adding `ATTRS{serial}=="<serial>"` (visible via
> `udevadm info /dev/ttyUSB0`).

---

## 4. Verify Arduino passthrough

The `docker-compose.yml` already includes the Arduino device passthrough for
the `api` service. Confirm it is present:

```yaml
services:
  api:
    devices:
      - /dev/arduino:/dev/arduino
```

---

## 5. Build and deploy

The application runs as two containers:

| Container | Port | Description |
|---|---|---|
| `fuj_api` | 8000 | FastAPI backend (`Dockerfile.backend`) |
| `fuj_gui` | 8050 | Dash UI (`Dockerfile.gui`) |

Both use `network_mode: host` so the backend can bind to the PSU-facing NICs
(`10.10.10.50`, `10.10.20.50`) directly. The GUI reaches the API at
`http://localhost:8000`.

### Build and start (on the Pi)

```bash
# Clone / pull the repository
git clone <repo-url> fuj_coherent_receiver_gui
cd fuj_coherent_receiver_gui

# Build both images and start in the background
docker compose build
docker compose up -d
```

The GUI container waits for the API healthcheck to pass before starting.
Watch startup progress with:

```bash
docker compose logs -f
```

Open `http://<pi-tailscale-ip>:8050` in a browser.

### Cross-compile on dev machine, transfer to Pi (faster builds)

```bash
# Build arm64 images on the dev machine
docker buildx build --platform linux/arm64 \
  -f Dockerfile.backend -t fuj_backend:latest --load .
docker buildx build --platform linux/arm64 \
  -f Dockerfile.gui     -t fuj_gui:latest     --load .

# Transfer to the Pi
docker save fuj_backend:latest | ssh pi@<tailscale-ip> docker load
docker save fuj_gui:latest     | ssh pi@<tailscale-ip> docker load

# On the Pi — start with the pre-loaded images
ssh pi@<tailscale-ip>
cd fuj_coherent_receiver_gui
docker compose up -d
```

`python:3.12-slim` has an official `arm64` variant — no changes to either
Dockerfile are needed.

### Useful commands

```bash
# View live logs from both containers
docker compose logs -f

# View API logs only
docker compose logs -f api

# Stop everything
docker compose down

# Restart after a config change
docker compose restart api

# Check container status and health
docker compose ps
```

### Adjusting configuration

Edit the `environment` section in `docker-compose.yml` for the relevant
service. Changes take effect after:

```bash
docker compose up -d --no-build
```
