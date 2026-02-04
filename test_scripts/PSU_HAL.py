from __future__ import annotations
import socket
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Union

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

class PsuTransportUDP:
    """
    UDP transport for MP71050x.
    In practice, the PSU replies reliably when the client binds local UDP port == device port. :contentReference[oaicite:3]{index=3}
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

    def _sock(self) -> socket.socket:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(self.timeout_s)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if self.local_port is not None:
            bind_ip = self.local_ip if self.local_ip is not None else ""
            s.bind((bind_ip, self.local_port))
        return s

    def write(self, cmd: str) -> None:
        msg = cmd.encode("ascii") + self.term
        with self._sock() as s:
            s.sendto(msg, (self.psu_ip, self.psu_port))
        time.sleep(0.03)

    def query_raw(self, cmd: str) -> bytes:
        msg = cmd.encode("ascii") + self.term
        with self._sock() as s:
            s.sendto(msg, (self.psu_ip, self.psu_port))
            data, _ = s.recvfrom(4096)
            return data

    def query_str(self, cmd: str) -> str:
        return self.query_raw(cmd).decode("ascii", errors="replace").strip()

class MP71050x:
    """
    One instance per physical PSU.
    Provides .channel(n) views for clear channel/PSU separation.
    Command set per comms protocol. :contentReference[oaicite:4]{index=4}
    """
    def __init__(self, name: str, transport: PsuTransportUDP):
        self.name = name
        self.t = transport
        self._id_cache: Optional[DeviceId] = None

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

        raw = self.t.query_str("*IDN?")  # :contentReference[oaicite:5]{index=5}
        # Example you saw: "MP710508 V1.1 SN:00002338"
        model = raw.split()[0] if raw else "UNKNOWN"
        version = None
        serial = None
        parts = raw.replace("SN:", "SN:").split()
        for p in parts:
            if p.upper().startswith("V"):
                version = p
            if p.upper().startswith("SN:"):
                serial = p.split(":", 1)[1] if ":" in p else None

        self._id_cache = DeviceId(raw=raw, model=model, version=version, serial=serial)
        return self._id_cache

    def lock_front_panel(self, locked: bool) -> None:
        self.t.write(f"LOCK:{1 if locked else 0}")  # :contentReference[oaicite:6]{index=6}

    def beep(self, enabled: bool) -> None:
        self.t.write(f"BEEP:{1 if enabled else 0}")  # :contentReference[oaicite:7]{index=7}

    def status(self) -> Status:
        raw = self.t.query_raw("STATUS?")  # :contentReference[oaicite:8]{index=8}
        b0 = raw[0]
        modes = tuple("CV" if ((b0 >> i) & 1) else "CC" for i in range(4))
        outs = tuple(bool((b0 >> (4 + i)) & 1) for i in range(4))
        return Status(raw=b0, mode=modes, output=outs)

    # ----- outputs (multi-channel capable) -----
    def set_output(self, channels: Channels, enabled: bool) -> None:
        x = self._fmt_channels(channels)
        self.t.write(f"OUT{x}:{1 if enabled else 0}")  # :contentReference[oaicite:9]{index=9}

    # ----- channel view -----
    def channel(self, ch: int) -> "Channel":
        return Channel(self, self._chk_ch(ch))

class Channel:
    """
    Bound view of one channel of one PSU.
    """
    def __init__(self, psu: MP71050x, ch: int):
        self.psu = psu
        self.ch = ch

    # setpoints / readback
    def set_voltage(self, volts: float) -> None:
        self.psu.t.write(f"VSET{self.ch}:{volts:.3f}")  # :contentReference[oaicite:10]{index=10}

    def get_voltage_setpoint(self) -> float:
        return self.psu._parse_float(self.psu.t.query_str(f"VSET{self.ch}?"))  # :contentReference[oaicite:11]{index=11}

    def set_current_limit(self, amps: float) -> None:
        self.psu.t.write(f"ISET{self.ch}:{amps:.3f}")  # :contentReference[oaicite:12]{index=12}

    def get_current_setpoint(self) -> float:
        return self.psu._parse_float(self.psu.t.query_str(f"ISET{self.ch}?"))  # :contentReference[oaicite:13]{index=13}

    def measure_voltage(self) -> float:
        return self.psu._parse_float(self.psu.t.query_str(f"VOUT{self.ch}?"))  # :contentReference[oaicite:14]{index=14}

    def measure_current(self) -> float:
        return self.psu._parse_float(self.psu.t.query_str(f"IOUT{self.ch}?"))  # :contentReference[oaicite:15]{index=15}

    # output
    def output(self, enabled: bool) -> None:
        self.psu.set_output(self.ch, enabled)

    # protections
    def set_ovp(self, volts: float, enabled: Optional[bool] = None) -> None:
        self.psu.t.write(f"OVPSET{self.ch}:{volts:.3f}")  # :contentReference[oaicite:16]{index=16}
        if enabled is not None:
            self.psu.t.write(f"OVP{self.ch}:{1 if enabled else 0}")  # :contentReference[oaicite:17]{index=17}

    def get_ovp(self) -> tuple[float, bool]:
        v = self.psu._parse_float(self.psu.t.query_str(f"OVPSET{self.ch}?"))  # :contentReference[oaicite:18]{index=18}
        en = bool(int(self.psu.t.query_str(f"OVP{self.ch}?")))                # :contentReference[oaicite:19]{index=19}
        return v, en

    def set_ocp(self, amps: float, enabled: Optional[bool] = None) -> None:
        self.psu.t.write(f"OCPSET{self.ch}:{amps:.3f}")  # :contentReference[oaicite:20]{index=20}
        if enabled is not None:
            self.psu.t.write(f"OCP{self.ch}:{1 if enabled else 0}")  # :contentReference[oaicite:21]{index=21}

    def get_ocp(self) -> tuple[float, bool]:
        a = self.psu._parse_float(self.psu.t.query_str(f"OCPSET{self.ch}?"))  # :contentReference[oaicite:22]{index=22}
        en = bool(int(self.psu.t.query_str(f"OCP{self.ch}?")))                # :contentReference[oaicite:23]{index=23}
        return a, en
