from __future__ import annotations
import logging
import re
import socket
import time
import threading
from dataclasses import dataclass
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Iterable, Optional, Union


def _setup_psu_logger() -> logging.Logger:
    """Configure dedicated PSU HAL logger with daily rotation."""
    logger = logging.getLogger("psu_hal")
    if logger.handlers:
        return logger  # Already configured

    logger.setLevel(logging.DEBUG)

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "psu_hal.log"

    handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        backupCount=30,  # Keep 30 days of logs
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s.%(msecs)03d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(handler)

    return logger


_psu_logger = _setup_psu_logger()

Channels = Union[int, Iterable[int], None]  # None => all

@dataclass(frozen=True)
class DeviceId:
    raw: str
    model: str
    version: Optional[str]
    serial: Optional[str]

@dataclass(frozen=True)
class Status:
    raw: int
    mode: tuple[str, str, str, str]      # "CV"/"CC"
    output: tuple[bool, bool, bool, bool]

def _extract_channel(cmd: str) -> Optional[str]:
    """Extract channel number(s) from command string, if present."""
    match = re.match(r'^[A-Z*]+(\d+)', cmd.upper())
    return match.group(1) if match else None


class PsuTransportUDP:
    """
    UDP transport for MP71050x.

    In practice, replies are reliable when the client binds local UDP port == device port.
    Socket is created once and kept open for the lifetime of the transport.
    """
    def __init__(
        self,
        psu_ip: str,
        psu_port: int = 18190,
        local_ip: Optional[str] = None,
        local_port: Optional[int] = 18190,
        term: bytes = b"\n",
        timeout_s: float = 2.0,
    ):
        self.psu_ip = psu_ip
        self.psu_port = psu_port
        self.local_ip = local_ip
        self.local_port = local_port
        self.term = term
        self.timeout_s = timeout_s
        self._logger = _psu_logger

        # Create persistent socket
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(self.timeout_s)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if self.local_port is not None:
            bind_ip = self.local_ip if self.local_ip is not None else ""
            self._sock.bind((bind_ip, self.local_port))

    def _log(self, direction: str, cmd: str, response: Optional[str] = None) -> None:
        """Log a command or response with channel info if available."""
        channel = _extract_channel(cmd)
        ch_str = f"CH{channel} | " if channel else ""

        if direction == "TX":
            self._logger.debug(f"{self.psu_ip} | TX | {ch_str}{cmd}")
        elif direction == "RX" and response is not None:
            self._logger.debug(f"{self.psu_ip} | RX | {ch_str}{response}")

    def write(self, cmd: str) -> None:
        msg = cmd.encode("ascii") + self.term
        self._sock.sendto(msg, (self.psu_ip, self.psu_port))
        self._log("TX", cmd)
        time.sleep(0.03)

    def query_raw(self, cmd: str) -> bytes:
        msg = cmd.encode("ascii") + self.term
        self._sock.sendto(msg, (self.psu_ip, self.psu_port))
        self._log("TX", cmd)
        data, addr = self._sock.recvfrom(4096)
        if addr[0] != self.psu_ip:
            raise RuntimeError(f"Unexpected reply from {addr}, expected {self.psu_ip}")
        response = data.decode("ascii", errors="replace").strip()
        self._log("RX", cmd, response)
        return data

    def query_str(self, cmd: str) -> str:
        return self.query_raw(cmd).decode("ascii", errors="replace").strip()

    def close(self) -> None:
        """Close the UDP socket."""
        if self._sock:
            self._sock.close()
            self._sock = None

    def __enter__(self) -> "PsuTransportUDP":
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb) -> None:
        self.close()

class MP71050x:
    """
    One instance per physical PSU.
    Provides .channel(n) views for clear channel/PSU separation.

    Command set per comms protocol. :contentReference[oaicite:5]{index=5}
    """
    def __init__(self, name: str, transport: PsuTransportUDP):
        self.name = name
        self.t = transport
        self._id_cache: Optional[DeviceId] = None
        self._lock = threading.Lock()  # serialize per PSU

    # ---- locked transport access (prevents interleaving on same PSU) ----
    def write(self, cmd: str) -> None:
        with self._lock:
            self.t.write(cmd)

    def query_raw(self, cmd: str) -> bytes:
        with self._lock:
            return self.t.query_raw(cmd)

    def query_str(self, cmd: str) -> str:
        with self._lock:
            return self.t.query_str(cmd)

    # ----- helpers -----
    @staticmethod
    def _chk_ch(ch: int) -> int:
        if ch not in (1, 2, 3, 4):
            raise ValueError("channel must be 1..4")
        return ch

    @staticmethod
    def _fmt_channels(sel: Channels) -> str:
        if sel is None:
            return "1234"
        if isinstance(sel, int):
            MP71050x._chk_ch(sel)
            return str(sel)
        chans = sorted({MP71050x._chk_ch(int(c)) for c in sel})
        if not chans:
            raise ValueError("empty channel selection")
        return "".join(str(c) for c in chans)

    @staticmethod
    def _parse_float(s: str) -> float:
        return float(s.strip())

    # ----- identity / UI -----
    def identify(self, refresh: bool = False) -> DeviceId:
        if self._id_cache is not None and not refresh:
            return self._id_cache

        raw = self.query_str("*IDN?")  # :contentReference[oaicite:6]{index=6}
        model = raw.split()[0] if raw else "UNKNOWN"
        version = None
        serial = None
        for p in raw.split():
            if p.upper().startswith("V"):
                version = p
            if p.upper().startswith("SN:"):
                serial = p.split(":", 1)[1] if ":" in p else None

        self._id_cache = DeviceId(raw=raw, model=model, version=version, serial=serial)
        return self._id_cache

    def lock_front_panel(self, locked: bool) -> None:
        self.write(f"LOCK:{1 if locked else 0}")  # :contentReference[oaicite:7]{index=7}

    def beep(self, enabled: bool) -> None:
        self.write(f"BEEP:{1 if enabled else 0}")  # :contentReference[oaicite:8]{index=8}

    def status(self) -> Status:
        raw = self.query_raw("STATUS?")  # :contentReference[oaicite:9]{index=9}
        b0 = raw[0]
        modes = tuple("CV" if ((b0 >> i) & 1) else "CC" for i in range(4))
        outs = tuple(bool((b0 >> (4 + i)) & 1) for i in range(4))
        return Status(raw=b0, mode=modes, output=outs)

    # ----- outputs (multi-channel capable) -----
    def set_output(self, channels: Channels, enabled: bool) -> None:
        x = self._fmt_channels(channels)
        self.write(f"OUT{x}:{1 if enabled else 0}")  # :contentReference[oaicite:10]{index=10}

    # ----- profiles -----
    def save_profile(self, slot: int) -> None:
        if slot not in range(10):
            raise ValueError("slot must be 0..9")
        self.write(f"SAV{slot}")  # :contentReference[oaicite:11]{index=11}

    def recall_profile(self, slot: int) -> None:
        if slot not in range(10):
            raise ValueError("slot must be 0..9")
        self.write(f"RCL{slot}")  # :contentReference[oaicite:12]{index=12}

    # ----- channel view -----
    def channel(self, ch: int) -> "Channel":
        return Channel(self, self._chk_ch(ch))

class Channel:
    """
    Bound view of one channel of one PSU.
    Implements full per-channel command surface. :contentReference[oaicite:13]{index=13}
    """
    def __init__(self, psu: MP71050x, ch: int):
        self.psu = psu
        self.ch = ch

    # ---- setpoints / readback ----
    def set_voltage(self, volts: float) -> None:
        self.psu.write(f"VSET{self.ch}:{volts:.3f}")  # :contentReference[oaicite:14]{index=14}

    def get_voltage_setpoint(self) -> float:
        return self.psu._parse_float(self.psu.query_str(f"VSET{self.ch}?"))  # :contentReference[oaicite:15]{index=15}

    def set_current_limit(self, amps: float) -> None:
        self.psu.write(f"ISET{self.ch}:{amps:.3f}")  # :contentReference[oaicite:16]{index=16}

    def get_current_setpoint(self) -> float:
        return self.psu._parse_float(self.psu.query_str(f"ISET{self.ch}?"))  # :contentReference[oaicite:17]{index=17}

    def measure_voltage(self) -> float:
        return self.psu._parse_float(self.psu.query_str(f"VOUT{self.ch}?"))  # :contentReference[oaicite:18]{index=18}

    def measure_current(self) -> float:
        return self.psu._parse_float(self.psu.query_str(f"IOUT{self.ch}?"))  # :contentReference[oaicite:19]{index=19}

    # ---- output ----
    def output(self, enabled: bool) -> None:
        self.psu.set_output(self.ch, enabled)

    # ---- protections ----
    def set_ovp(self, volts: float, enabled: Optional[bool] = None) -> None:
        self.psu.write(f"OVPSET{self.ch}:{volts:.3f}")  # :contentReference[oaicite:20]{index=20}
        if enabled is not None:
            self.psu.write(f"OVP{self.ch}:{1 if enabled else 0}")  # :contentReference[oaicite:21]{index=21}

    def get_ovp(self) -> tuple[float, bool]:
        v = self.psu._parse_float(self.psu.query_str(f"OVPSET{self.ch}?"))  # :contentReference[oaicite:22]{index=22}
        en = bool(int(self.psu.query_str(f"OVP{self.ch}?")))                # :contentReference[oaicite:23]{index=23}
        return v, en

    def set_ocp(self, amps: float, enabled: Optional[bool] = None) -> None:
        self.psu.write(f"OCPSET{self.ch}:{amps:.3f}")  # :contentReference[oaicite:24]{index=24}
        if enabled is not None:
            self.psu.write(f"OCP{self.ch}:{1 if enabled else 0}")  # :contentReference[oaicite:25]{index=25}

    def get_ocp(self) -> tuple[float, bool]:
        a = self.psu._parse_float(self.psu.query_str(f"OCPSET{self.ch}?"))  # :contentReference[oaicite:26]{index=26}
        en = bool(int(self.psu.query_str(f"OCP{self.ch}?")))                # :contentReference[oaicite:27]{index=27}
        return a, en

    # ---- LIST programming ----
    def list_set_step(self, list_id: int, step: int, volts: float, amps: float, dwell_s: float) -> None:
        # LISTCH<X>:<NR1>,<NR1>,<NR2>,<NR2>,<NR2> :contentReference[oaicite:28]{index=28}
        self.psu.write(f"LISTCH{self.ch}:{int(list_id)},{int(step)},{volts:.3f},{amps:.3f},{dwell_s:.3f}")

    def list_set_length(self, list_id: int, length: int) -> None:
        # LISTLCH<X>:<NR1>,<NR1> :contentReference[oaicite:29]{index=29}
        self.psu.write(f"LISTLCH{self.ch}:{int(list_id)},{int(length)}")

    def list_set_cycles(self, list_id: int, cycles: int) -> None:
        # LISTCCH<X>:<NR1>,<NR1> :contentReference[oaicite:30]{index=30}
        self.psu.write(f"LISTCCH{self.ch}:{int(list_id)},{int(cycles)}")

    def list_save(self, list_id: int) -> None:
        # LISTSCH<X>:<NR1> :contentReference[oaicite:31]{index=31}
        self.psu.write(f"LISTSCH{self.ch}:{int(list_id)}")

    # ---- External trigger / switch / compensation ----
    def external_trigger(self, enabled: bool) -> None:
        # EXIT<X>:<Boolean> :contentReference[oaicite:32]{index=32}
        self.psu.write(f"EXIT{self.ch}:{1 if enabled else 0}")

    def external_switch(self, enabled: bool) -> None:
        # EXON<X>:<Boolean> :contentReference[oaicite:33]{index=33}
        self.psu.write(f"EXON{self.ch}:{1 if enabled else 0}")

    def external_comp(self, enabled: bool) -> None:
        # COMP<X>:<Boolean> :contentReference[oaicite:34]{index=34}
        self.psu.write(f"COMP{self.ch}:{1 if enabled else 0}")

    # ---- Automatic stepping (requires output ON per docs) ----
    def auto_step_voltage(self, v_start: float, v_end: float, v_step: float, step_time_s: float) -> None:
        # VASTEP<X>:<NR2>,<NR2>,<NR2>,<NR2> :contentReference[oaicite:35]{index=35}
        self.psu.write(f"VASTEP{self.ch}:{v_start:.3f},{v_end:.3f},{v_step:.3f},{step_time_s:.3f}")

    def auto_step_voltage_stop(self) -> None:
        # VASTOP<X> :contentReference[oaicite:36]{index=36}
        self.psu.write(f"VASTOP{self.ch}")

    def auto_step_current(self, i_start: float, i_end: float, i_step: float, step_time_s: float) -> None:
        # IASTEP<X>:<NR2>,<NR2>,<NR2>,<NR2> :contentReference[oaicite:37]{index=37}
        self.psu.write(f"IASTEP{self.ch}:{i_start:.3f},{i_end:.3f},{i_step:.3f},{step_time_s:.3f}")

    def auto_step_current_stop(self) -> None:
        # IASTOP<X> :contentReference[oaicite:38]{index=38}
        self.psu.write(f"IASTOP{self.ch}")

    # ---- Manual stepping ----
    def set_manual_voltage_step(self, step_v: float) -> None:
        # VSTEP<X>:<NR2> :contentReference[oaicite:39]{index=39}
        self.psu.write(f"VSTEP{self.ch}:{step_v:.3f}")

    def voltage_step_up(self) -> None:
        # VUP<X> :contentReference[oaicite:40]{index=40}
        self.psu.write(f"VUP{self.ch}")

    def voltage_step_down(self) -> None:
        # VDOWN<X> :contentReference[oaicite:41]{index=41}
        self.psu.write(f"VDOWN{self.ch}")

    def set_manual_current_step(self, step_a: float) -> None:
        # ISTEP<X>:<NR2> :contentReference[oaicite:42]{index=42}
        self.psu.write(f"ISTEP{self.ch}:{step_a:.3f}")

    def current_step_up(self) -> None:
        # IUP<X> :contentReference[oaicite:43]{index=43}
        self.psu.write(f"IUP{self.ch}")

    def current_step_down(self) -> None:
        # IDOWN<X> :contentReference[oaicite:44]{index=44}
        self.psu.write(f"IDOWN{self.ch}")
