"""Arduino MCU implementation for FIM24725 coherent receiver.

Controls FIM24725 digital signals via an OSEPP Arduino Uno R3 connected over
USB serial (/dev/arduino on Raspberry Pi).

Digital outputs (Arduino → FIM24725):
  D2  SD (Shutdown):  LOW  = module disabled (D2 LOW → FIM24725 SD LOW = shutdown active)
                      HIGH = module enabled  (D2 HIGH → FIM24725 SD HIGH = shutdown inactive)
  D3  MC/AGC (Mode):  HIGH = AGC,              LOW = MGC

Analog inputs (FIM24725 → Arduino ADC, 0–2V):
  A0  PI_XI  (Peak Indicator X-I)
  A1  PI_XQ  (Peak Indicator X-Q)
  A2  PI_YI  (Peak Indicator Y-I)
  A3  PI_YQ  (Peak Indicator Y-Q)
  A4  MPD+   (Monitor Photodiode positive terminal)
  A5  MPD-   (Monitor Photodiode negative terminal)

The Arduino autonomously pushes a TELE: line every 500 ms.
Commands are sent as ASCII lines; the Arduino echoes the applied state.
A INIT: line is emitted by the Arduino on startup to confirm initial state.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Optional

import serial

from ..services.exceptions import MCUError
from ..services.logging import get_service_logger
from ..services.models import OperatingMode, PeakIndicators


class ArduinoMCU:
    """Arduino Uno MCU implementation of MCUInterface.

    Communicates over USB serial using a simple ASCII command/response protocol.
    A background reader thread handles incoming data, routing telemetry lines
    to an internal cache and command responses to a queue for synchronous callers.

    Usage:
        mcu = ArduinoMCU("/dev/arduino")
        service = FIM24725Service(..., mcu=mcu)
        try:
            service.startup()
        finally:
            service.close()
            mcu.close()
    """

    BAUD: int = 115200
    READ_TIMEOUT_S: float = 0.1  # Short timeout in reader thread (non-blocking feel)

    def __init__(
        self,
        port: str = "/dev/arduino",
        baud: int = BAUD,
        timeout: float = 2.0,
    ) -> None:
        """Open serial connection and wait for Arduino startup.

        Args:
            port: Serial device path (default /dev/arduino via udev symlink).
            baud: Baud rate (must match Arduino firmware, default 115200).
            timeout: Seconds to wait for each command response (including HELLO
                     during connection).

        Raises:
            MCUError: If the Arduino does not respond to HELLO within timeout
                      seconds, indicating wrong firmware or hardware fault.
            serial.SerialException: If the serial port cannot be opened.
        """
        self._logger = get_service_logger().getChild("mcu.arduino")
        self._port = port
        self._baud = baud
        self._timeout = timeout

        # Cached state — updated by set_shutdown() and set_mode()
        self._sd_disabled = True
        self._mode = OperatingMode.AGC

        # Latest telemetry cache
        self._last_pi: Optional[PeakIndicators] = None
        self._last_mpd: Optional[float] = None    # differential: MPD+ - MPD-
        self._last_mpd_n: Optional[float] = None  # MPD- raw
        self._tele_lock = threading.Lock()

        # Command response queue — reader thread deposits non-TELE lines here
        self._response_queue: queue.Queue[str] = queue.Queue()

        # Connected flag — set False by reader thread on serial fault
        self._connected = False

        # Reader thread management
        self._stop_reader = threading.Event()
        self._serial: Optional[serial.Serial] = None
        self._reader_thread: Optional[threading.Thread] = None

        self._connect()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        """Open serial port, reset Arduino via DTR, confirm firmware with HELLO."""
        self._logger.info(
            f"Connecting to Arduino on {self._port} at {self.BAUD} baud"
        )

        self._serial = serial.Serial(
            self._port,
            baudrate=self._baud,
            timeout=self.READ_TIMEOUT_S,
        )

        # Clear stale bytes buffered before this open (e.g. TELE: left over
        # from the Arduino reset triggered when the previous session closed)
        self._serial.reset_input_buffer()

        # Start reader thread before the DTR pulse so it is ready to receive
        self._stop_reader.clear()
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="arduino-reader",
            daemon=True,
        )
        self._reader_thread.start()

        # DTR reset: force HIGH first so the subsequent LOW is a guaranteed
        # HIGH→LOW falling edge regardless of initial DTR state.
        # HIGH→LOW on DTR couples through the 100nF cap → brief LOW on RESET → Arduino resets.
        self._logger.debug("Resetting Arduino via DTR pulse")
        self._serial.dtr = True   # ensure HIGH (no-op if already HIGH)
        time.sleep(0.05)          # let cap settle to steady state
        self._serial.dtr = False  # HIGH→LOW: cap couples edge → RESET LOW → Arduino resets

        # Wait for optiboot bootloader to finish before sending HELLO.
        # Arduino Uno R3 optiboot has a 1s upload window; 1.5s gives safe margin.
        time.sleep(1.5)

        # Drain any bytes that arrived during reset (null bytes, bootloader noise)
        # before sending HELLO so _send_command gets the real response.
        while True:
            try:
                self._response_queue.get_nowait()
            except queue.Empty:
                break

        # Active handshake: Pi requests state; Arduino responds with INIT: line.
        # This is timing-safe — Pi controls when the handshake happens.
        self._logger.debug("Sending HELLO to Arduino")
        try:
            response = self._send_command("HELLO")
        except MCUError as e:
            self.close()
            raise MCUError(
                f"Arduino on {self._port} did not respond to HELLO — "
                f"check firmware is flashed correctly: {e}"
            ) from e

        if not response.startswith("INIT:"):
            self.close()
            raise MCUError(
                f"Unexpected HELLO response from {self._port}: {response!r}"
            )

        self._connected = True
        self._logger.info(f"Arduino connected: {response}")

    def _reader_loop(self) -> None:
        """Background thread: read lines from serial and route them."""
        while not self._stop_reader.is_set():
            try:
                if self._serial is None or not self._serial.is_open:
                    break

                raw = self._serial.readline()
                if not raw:
                    continue  # Timeout, no data — keep looping

                line = raw.decode("ascii", errors="replace").strip()
                if not line or '\x00' in line:
                    continue

                self._logger.debug(f"RX: {line}")

                if line.startswith("TELE:"):
                    self._parse_telemetry(line[5:])
                else:
                    self._response_queue.put(line)

            except serial.SerialException as e:
                self._logger.error(f"Serial read error: {e}")
                self._connected = False
                break
            except Exception as e:
                self._logger.error(f"Reader loop error: {e}")
                break

    def _parse_telemetry(self, payload: str) -> None:
        """Parse TELE payload and update internal cache.

        Expected format: PI_XI=1.234,PI_XQ=0.876,PI_YI=1.543,PI_YQ=0.234,MPD_P=0.567,MPD_N=0.123
        MPD differential is computed as MPD+ - MPD-.
        """
        try:
            parts = dict(item.split("=") for item in payload.split(","))
            pi = PeakIndicators(
                pi_xi=float(parts["PI_XI"]),
                pi_xq=float(parts["PI_XQ"]),
                pi_yi=float(parts["PI_YI"]),
                pi_yq=float(parts["PI_YQ"]),
            )
            mpd_p = float(parts["MPD_P"])
            mpd_n = float(parts["MPD_N"])
            with self._tele_lock:
                self._last_pi = pi
                self._last_mpd = mpd_p - mpd_n  # differential
                self._last_mpd_n = mpd_n
        except Exception as e:
            self._logger.warning(f"Telemetry parse error: {e} | payload: {payload!r}")

    def _send_command(self, cmd: str) -> str:
        """Send a command and wait for the Arduino's response.

        Args:
            cmd: Command string (without newline).

        Returns:
            The response string from the Arduino.

        Raises:
            MCUError: On timeout, serial error, or ERR: response from Arduino.
        """
        if self._serial is None or not self._serial.is_open:
            raise MCUError("Serial port not open")

        self._logger.debug(f"TX: {cmd}")
        try:
            self._serial.write((cmd + "\n").encode("ascii"))
        except serial.SerialException as e:
            self._connected = False
            raise MCUError(f"Serial write error: {e}") from e

        try:
            response = self._response_queue.get(timeout=self._timeout)
        except queue.Empty:
            raise MCUError(f"No response to command '{cmd}' within {self._timeout}s")

        if response.startswith("ERR:"):
            raise MCUError(f"Arduino error: {response}")

        return response

    # ------------------------------------------------------------------
    # MCUInterface implementation
    # ------------------------------------------------------------------

    def set_shutdown(self, disable: bool) -> bool:
        """Set SD pin state. Returns actual SD state after setting.

        Args:
            disable: True  → sends SD:1 → D2 LOW  → FIM24725 SD LOW  = shutdown active (module off).
                     False → sends SD:0 → D2 HIGH → FIM24725 SD HIGH = shutdown inactive (module on).

        Returns:
            Actual SD state: True if disabled, False if enabled.

        Raises:
            MCUError: On communication failure or pin fault.
        """
        cmd = "SD:1" if disable else "SD:0"
        response = self._send_command(cmd)

        if response == "SD:1":
            self._sd_disabled = True
        elif response == "SD:0":
            self._sd_disabled = False
        else:
            raise MCUError(f"Unexpected SD response: {response!r}")

        return self._sd_disabled

    def set_mode(self, mode: OperatingMode) -> OperatingMode:
        """Set MC/AGC pin for gain control mode. Returns actual mode.

        Args:
            mode: AGC sets pin HIGH, MGC sets pin LOW.

        Returns:
            Actual operating mode confirmed by Arduino.

        Raises:
            MCUError: On communication failure or pin fault.
        """
        response = self._send_command(f"MODE:{mode.value}")

        if response == "MODE:AGC":
            self._mode = OperatingMode.AGC
        elif response == "MODE:MGC":
            self._mode = OperatingMode.MGC
        else:
            raise MCUError(f"Unexpected MODE response: {response!r}")

        return self._mode

    @property
    def sd_disabled(self) -> bool:
        """Current SD pin state (cached). True = module disabled (D2 LOW, FIM24725 SD LOW)."""
        return self._sd_disabled

    @property
    def mode(self) -> OperatingMode:
        """Current MC/AGC mode (cached)."""
        return self._mode

    def read_peak_indicators(self) -> PeakIndicators:
        """Return latest PI readings from telemetry cache.

        Returns:
            PeakIndicators with values 0–2V for each channel.

        Raises:
            MCUError: If no telemetry has been received yet.
        """
        with self._tele_lock:
            pi = self._last_pi
        if pi is None:
            raise MCUError("No telemetry received from Arduino yet")
        return pi

    def read_mpd(self) -> float:
        """Return differential MPD reading (MPD+ - MPD-) from telemetry cache.

        Returns:
            MPD differential voltage (MPD+ - MPD-).

        Raises:
            MCUError: If no telemetry has been received yet.
        """
        with self._tele_lock:
            mpd = self._last_mpd
        if mpd is None:
            raise MCUError("No telemetry received from Arduino yet")
        return mpd

    def read_mpd_n(self) -> float:
        """Return latest MPD- (negative terminal) raw reading from telemetry cache.

        Returns:
            MPD- voltage (0–2V).

        Raises:
            MCUError: If no telemetry has been received yet.
        """
        with self._tele_lock:
            mpd_n = self._last_mpd_n
        if mpd_n is None:
            raise MCUError("No telemetry received from Arduino yet")
        return mpd_n

    def is_connected(self) -> bool:
        """Check if Arduino is responsive by sending PING.

        Returns:
            True if PONG is received, False otherwise.
        """
        if not self._connected:
            return False
        try:
            return self._send_command("PING") == "PONG"
        except MCUError:
            return False

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Stop reader thread and close serial port."""
        self._stop_reader.set()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=2.0)
            self._reader_thread = None
        if self._serial is not None:
            self._serial.close()
            self._serial = None
        self._connected = False
        self._logger.info("Arduino disconnected")

    def __enter__(self) -> "ArduinoMCU":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
