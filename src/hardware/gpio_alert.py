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

        self.led_low = None
        self.led_med = None
        self.led_high = None
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
            print("[GPIO] Mock mode enabled - running simulated GPIO hardware (3-LED + Buzzer).")
            return

        try:
            from gpiozero import LED, Buzzer, Button

            # Initialize 3 Risk-Level LEDs
            self.led_low = LED(self.config.led_low_pin, active_high=self.config.active_high)
            self.led_med = LED(self.config.led_med_pin, active_high=self.config.active_high)
            self.led_high = LED(self.config.led_high_pin, active_high=self.config.active_high)

            # Initialize Piezo Buzzer (High/Critical only)
            self.buzzer = Buzzer(self.config.buzzer_pin, active_high=self.config.active_high)

            # Initialize Panic Button
            self.button = Button(self.config.panic_button_pin, pull_up=True, bounce_time=0.1)

            if self.panic_callback:
                self.button.when_pressed = self._on_panic_button_pressed

            # Initial State: ALL LEDs and Buzzer OFF by default
            self.all_off()

            print(
                f"[GPIO] Initialized 3 LEDs [LOW: GPIO {self.config.led_low_pin} (Green), "
                f"MED: GPIO {self.config.led_med_pin} (Yellow), HIGH: GPIO {self.config.led_high_pin} (Red)], "
                f"Buzzer on GPIO {self.config.buzzer_pin} (High only), "
                f"Panic Button on GPIO {self.config.panic_button_pin}"
            )
        except Exception as e:
            print(f"[GPIO-WARN] Failed to initialize gpiozero hardware: {e}. Falling back to mock mode.")
            self.mock_mode = True

    def _on_panic_button_pressed(self) -> None:
        print("\n[GPIO-ALERT] !!! PHYSICAL PANIC BUTTON PRESSED !!!\n")
        self.trigger_alert("PANIC_BUTTON_PRESSED", severity="HIGH", duration_sec=5.0)
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

        sev = severity.upper()
        now = time.time()

        # HIGH and CRITICAL alerts immediately bypass routine cooldown
        if (now - self._last_alert_time < self.config.cooldown_sec) and (sev not in ("HIGH", "CRITICAL")):
            return

        dur = duration_sec or self.config.alert_duration_sec
        try:
            self._alert_queue.put_nowait(
                AlertEvent(threat_type=threat_type, severity=sev, duration_sec=dur)
            )
            self._last_alert_time = now
        except queue.Full:
            pass

    def _alert_worker(self) -> None:
        """Background thread executing 3-LED risk patterns and high-only buzzer sirens."""
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
        sev = event.severity

        # Ensure all actuators are initially off
        self.all_off()

        if self.mock_mode:
            if sev in ("HIGH", "CRITICAL"):
                print(f"\n[MOCK-GPIO] 🔴 HIGH RISK DETECTED: {event.threat_type} -> RED LED (GPIO {self.config.led_high_pin}) ON | 🔊 BUZZER (GPIO {self.config.buzzer_pin}) ON")
            elif sev == "MEDIUM":
                print(f"\n[MOCK-GPIO] 🟡 MEDIUM RISK DETECTED: {event.threat_type} -> YELLOW LED (GPIO {self.config.led_med_pin}) ON | 🔇 BUZZER OFF")
            else:
                print(f"\n[MOCK-GPIO] 🟢 LOW RISK DETECTED: {event.threat_type} -> GREEN LED (GPIO {self.config.led_low_pin}) ON | 🔇 BUZZER OFF")

        # 1. HIGH / CRITICAL RISK: RED LED strobing + BUZZER sounding (Green & Yellow OFF)
        if sev in ("HIGH", "CRITICAL"):
            pulse_rate = 0.08 if sev == "CRITICAL" else 0.15
            while time.time() < end_time and not self._stop_event.is_set():
                if self.led_high:
                    self.led_high.on()
                if self.buzzer:
                    self.buzzer.on()
                time.sleep(pulse_rate)

                if self.led_high:
                    self.led_high.off()
                if self.buzzer:
                    self.buzzer.off()
                time.sleep(pulse_rate)

        # 2. MEDIUM RISK: YELLOW LED pulsing ONLY (Green, Red, Buzzer OFF)
        elif sev == "MEDIUM":
            while time.time() < end_time and not self._stop_event.is_set():
                if self.led_med:
                    self.led_med.on()
                time.sleep(0.25)

                if self.led_med:
                    self.led_med.off()
                time.sleep(0.25)

        # 3. LOW RISK: GREEN LED solid ON ONLY (Yellow, Red, Buzzer OFF)
        else:
            if self.led_low:
                self.led_low.on()
            time.sleep(event.duration_sec)
            if self.led_low:
                self.led_low.off()

        # Turn EVERYTHING completely OFF after alert duration expires
        self.all_off()
        self._is_alerting = False

    def reset_to_idle(self) -> None:
        """Turns OFF all LEDs and Buzzer when idle / no threat is active."""
        self.all_off()

    def all_off(self) -> None:
        """Explicitly forces all 3 LEDs and Buzzer to the OFF (inactive) state."""
        if self.led_low:
            self.led_low.off()
        if self.led_med:
            self.led_med.off()
        if self.led_high:
            self.led_high.off()
        if self.buzzer:
            self.buzzer.off()

    def cleanup(self) -> None:
        self._stop_event.set()
        self.all_off()
        for dev in (self.led_low, self.led_med, self.led_high, self.buzzer, self.button):
            if dev:
                dev.close()
        print("[GPIO] Cleaned up hardware pins.")
