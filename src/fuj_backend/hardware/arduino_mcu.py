"""Arduino MCU implementation for FIM24725 coherent receiver.

Controls FIM24725 digital signals via an OSEPP Arduino Uno R3 connected over
USB serial (/dev/arduino on Raspberry Pi).

Digital outputs (Arduino → FIM24725):
  D2  SD (Shutdown):  HIGH = module disabled,  LOW = module enabled
  D3  MC/AGC (Mode):  HIGH = AGC,              LOW = MGC

Analog inputs (FIM24725 → Arduino ADC, 0–2V):
  A0  PI_XI  (Peak Indicator X-I)
  A1  PI_XQ  (Peak Indicator X-Q)
  A2  PI_YI  (Peak Indicator Y-I)
  A3  PI_YQ  (Peak Indicator Y-Q)
  A4  MPD    (Monitor Photodiode)

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
    BOOT_DELAY_S: float = 2.0   # Wait for Arduino reset-on-DTR before sending
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
            timeout: Seconds to wait for command responses and INIT message.

        Raises:
            MCUError: If the Arduino does not send INIT: within timeout seconds,
                      indicating wrong firmware or hardware fault.
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
        self._last_mpd: Optional[float] = None
        self._tele_lock = threading.Lock()

        # Command response queue — reader thread deposits non-TELE lines here
        self._response_queue: queue.Queue[str] = queue.Queue()

        # Connected flag — set False by reader thread on serial fault
        self._connected = False

        # INIT confirmation event — set when INIT: message is received
        self._init_event = threading.Event()

        # Reader thread management
        self._stop_reader = threading.Event()
        self._serial: Optional[serial.Serial] = None
        self._reader_thread: Optional[threading.Thread] = None

        self._connect()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        """Open serial port, wait for Arduino boot, confirm INIT message."""
        self._logger.info(
            f"Connecting to Arduino on {self._port} at {self.BAUD} baud"
        )

        self._serial = serial.Serial(
            self._port,
            baudrate=self._baud,
            timeout=self.READ_TIMEOUT_S,
        )

        # Arduino resets when DTR is toggled on connect; give it time to boot
        self._logger.debug(f"Waiting {self.BOOT_DELAY_S}s for Arduino reset")
        time.sleep(self.BOOT_DELAY_S)
        self._serial.reset_input_buffer()

        # Start background reader
        self._stop_reader.clear()
        self._init_event.clear()
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="arduino-reader",
            daemon=True,
        )
        self._reader_thread.start()

        # Wait for INIT: message confirming firmware is running
        if not self._init_event.wait(timeout=self._timeout):
            self.close()
            raise MCUError(
                f"Arduino on {self._port} did not send INIT within "
                f"{self._timeout}s — check firmware and connection"
            )

        self._connected = True
        self._logger.info("Arduino connected and initialised")

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
                if not line:
                    continue

                self._logger.debug(f"RX: {line}")

                if line.startswith("TELE:"):
                    self._parse_telemetry(line[5:])
                elif line.startswith("INIT:"):
                    self._logger.info(f"Arduino startup: {line}")
                    self._init_event.set()
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

        Expected format: PI_XI=1.234,PI_XQ=0.876,PI_YI=1.543,PI_YQ=0.234,MPD=0.567
        """
        try:
            parts = dict(item.split("=") for item in payload.split(","))
            pi = PeakIndicators(
                pi_xi=float(parts["PI_XI"]),
                pi_xq=float(parts["PI_XQ"]),
                pi_yi=float(parts["PI_YI"]),
                pi_yq=float(parts["PI_YQ"]),
            )
            mpd = float(parts["MPD"])
            with self._tele_lock:
                self._last_pi = pi
                self._last_mpd = mpd
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
            disable: True sets SD HIGH (module disabled),
                     False sets SD LOW (module enabled).

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
        """Current SD pin state (cached). True = module disabled (HIGH)."""
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
        """Return latest MPD reading from telemetry cache.

        Returns:
            MPD voltage (0–2V, units TBD).

        Raises:
            MCUError: If no telemetry has been received yet.
        """
        with self._tele_lock:
            mpd = self._last_mpd
        if mpd is None:
            raise MCUError("No telemetry received from Arduino yet")
        return mpd

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
