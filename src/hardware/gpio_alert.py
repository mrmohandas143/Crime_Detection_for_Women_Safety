"""
GPIO Hardware Alert Controller
Controls Alert LED (GPIO 18), Piezo Buzzer (GPIO 17), and Panic Button (GPIO 27) using gpiozero.
Includes non-blocking alert queue and mock mode for testing without hardware.
"""

from dataclasses import dataclass
import queue
import threading
import time
from typing import Callable, Optional
from src.config_loader import GPIOConfig


@dataclass
class AlertEvent:
    threat_type: str
    severity: str  # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    duration_sec: float = 2.5


class GPIOAlertController:
    """
    Manages physical LED, Buzzer, and Panic Button hardware with asynchronous non-blocking pulsing.
    """

    def __init__(
        self,
        config: GPIOConfig,
        mock_mode: bool = False,
        panic_callback: Optional[Callable[[], None]] = None,
    ):
        self.config = config
        self.mock_mode = mock_mode
        self.panic_callback = panic_callback

        self.led = None
        self.buzzer = None
        self.button = None
        self._is_alerting = False
        self._last_alert_time = 0.0
        self._stop_event = threading.Event()
        self._alert_queue: queue.Queue[AlertEvent] = queue.Queue(maxsize=10)

        self._init_hardware()

        # Start worker thread for handling audio/visual alert sequences
        self._worker_thread = threading.Thread(target=self._alert_worker, daemon=True)
        self._worker_thread.start()

    def _init_hardware(self) -> None:
        if not self.config.enabled:
            print("[GPIO] Hardware alerts disabled in configuration.")
            return

        if self.mock_mode:
            print("[GPIO] Mock mode enabled - running simulated GPIO hardware.")
            return

        try:
            from gpiozero import LED, Buzzer, Button

            self.led = LED(self.config.led_pin, active_high=self.config.active_high)
            self.buzzer = Buzzer(self.config.buzzer_pin, active_high=self.config.active_high)
            self.button = Button(self.config.panic_button_pin, pull_up=True, bounce_time=0.1)

            if self.panic_callback:
                self.button.when_pressed = self._on_panic_button_pressed

            print(
                f"[GPIO] Initialized LED on GPIO {self.config.led_pin}, "
                f"Buzzer on GPIO {self.config.buzzer_pin}, "
                f"Panic Button on GPIO {self.config.panic_button_pin}"
            )
        except Exception as e:
            print(f"[GPIO-WARN] Failed to initialize gpiozero hardware: {e}. Falling back to mock mode.")
            self.mock_mode = True

    def _on_panic_button_pressed(self) -> None:
        print("\n[GPIO-ALERT] !!! PHYSICAL PANIC BUTTON PRESSED !!!\n")
        self.trigger_alert("PANIC_BUTTON_PRESSED", severity="CRITICAL", duration_sec=5.0)
        if self.panic_callback:
            self.panic_callback()

    def trigger_alert(
        self,
        threat_type: str,
        severity: str = "HIGH",
        duration_sec: Optional[float] = None,
    ) -> None:
        """Queue an alert for non-blocking asynchronous hardware execution."""
        if not self.config.enabled:
            return

        now = time.time()
        if now - self._last_alert_time < self.config.cooldown_sec and severity != "CRITICAL":
            return  # Respect cooldown to prevent alert storms

        dur = duration_sec or self.config.alert_duration_sec
        try:
            self._alert_queue.put_nowait(
                AlertEvent(threat_type=threat_type, severity=severity, duration_sec=dur)
            )
            self._last_alert_time = now
        except queue.Full:
            pass  # Queue is busy, alert already active

    def _alert_worker(self) -> None:
        """Background thread executing buzzer chirps and LED strobe patterns."""
        while not self._stop_event.is_set():
            try:
                event = self._alert_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            self._execute_alert_pattern(event)
            self._alert_queue.task_done()

    def _execute_alert_pattern(self, event: AlertEvent) -> None:
        self._is_alerting = True
        end_time = time.time() + event.duration_sec

        # Pattern parameters based on severity
        if event.severity == "CRITICAL":
            on_time, off_time = 0.08, 0.08  # Rapid frantic strobe
        elif event.severity == "HIGH":
            on_time, off_time = 0.15, 0.15  # Fast warning pulse
        else:
            on_time, off_time = 0.35, 0.35  # Moderate cadence

        if self.mock_mode:
            print(f"[MOCK-GPIO] Activating LED + Buzzer for {event.threat_type} ({event.severity})")

        while time.time() < end_time and not self._stop_event.is_set():
            # Turn on
            if self.led:
                self.led.on()
            if self.buzzer:
                self.buzzer.on()
            time.sleep(on_time)

            # Turn off
            if self.led:
                self.led.off()
            if self.buzzer:
                self.buzzer.off()
            time.sleep(off_time)

        # Ensure all off at end
        self.all_off()
        self._is_alerting = False

    def all_off(self) -> None:
        if self.led:
            self.led.off()
        if self.buzzer:
            self.buzzer.off()

    def cleanup(self) -> None:
        self._stop_event.set()
        self.all_off()
        if self.led:
            self.led.close()
        if self.buzzer:
            self.buzzer.close()
        if self.button:
            self.button.close()
        print("[GPIO] Cleaned up hardware pins.")
