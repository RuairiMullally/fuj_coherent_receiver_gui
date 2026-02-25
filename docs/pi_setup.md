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

## 4. docker-compose — Arduino device passthrough

Add the `devices` entry to `docker-compose.yml` so the container can access
the Arduino:

```yaml
services:
  backend:
    ...
    devices:
      - /dev/arduino:/dev/arduino
```

---

## 5. Build and deploy

**On the Pi directly** (slow but simple):
```bash
docker compose build
docker compose up -d
```

**Cross-compile on dev machine, transfer to Pi** (faster):
```bash
docker buildx build --platform linux/arm64 \
  -f Dockerfile.backend -t fuj_backend --load .
docker save fuj_backend | ssh pi@<tailscale-ip> docker load
```

No changes to `Dockerfile.backend` or `pyproject.toml` are needed —
`python:3.12-slim` has an official arm64 variant that Docker pulls
automatically when building on arm64.
