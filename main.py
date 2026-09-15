#!/usr/bin/env python3
"""
AI Safety Monitoring System - Main Executable
Raspberry Pi 5 AI Surveillance & Physical Alert System
Target OS: Debian 13 (Trixie)
"""

import argparse
import os
import signal
import sys
import time
import cv2

from src.config_loader import load_config
from src.capture import ThreadedCamera
from src.engine import SafetyMonitoringEngine
from src.hardware.gpio_alert import GPIOAlertController
from src.hardware.oled_display import OLEDDisplayController
from src.logger import SafetyLogger


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI Safety Monitoring System for Raspberry Pi 5"
    )
    parser.add_argument(
        "-c", "--config", default="config/config.yaml", help="Path to YAML configuration file"
    )
    parser.add_argument(
        "-s", "--source", default=None, help="Override camera source (index, RTSP, video file, or 'rpicam')"
    )
    parser.add_argument(
        "--headless", action="store_true", help="Run in headless background mode without GUI display"
    )
    parser.add_argument(
        "--mock-hardware", action="store_true", help="Run with simulated GPIO and OLED (for testing off-Pi)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Test initialization and process 10 frames then exit"
    )
    return parser.parse_args()


class SafetyMonitorApp:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.config = load_config(args.config)

        # Apply CLI overrides
        if args.source is not None:
            self.config.camera.source = args.source
        if args.mock_hardware:
            self.config.system.mock_hardware = True

        self.running = True

        # Initialize Logger
        self.logger = SafetyLogger(
            log_file=self.config.system.log_file,
            snapshot_dir=self.config.system.snapshot_dir,
            log_level=self.config.system.log_level,
            save_snapshots=self.config.system.save_alert_snapshots,
        )
        self.logger.log_info(f"Starting {self.config.system.device_name} Safety Monitoring System...")

        # Initialize Hardware Controllers
        self.gpio = None
        self.oled = None
        self._init_hardware()

        # Initialize Camera
        self.camera = ThreadedCamera(self.config.camera).start()

        # Initialize AI Engine
        self.engine = SafetyMonitoringEngine(
            config=self.config,
            gpio_controller=self.gpio,
            oled_controller=self.oled,
            logger=self.logger,
        )

        # Setup graceful signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _init_hardware(self) -> None:
        mock = self.config.system.mock_hardware

        # GPIO Alert Controller
        if self.config.hardware.gpio.enabled:
            self.gpio = GPIOAlertController(
                config=self.config.hardware.gpio,
                mock_mode=mock,
                panic_callback=self._on_panic_trigger,
            )

        # OLED Display Controller
        if self.config.hardware.oled.enabled:
            self.oled = OLEDDisplayController(
                config=self.config.hardware.oled,
                mock_mode=mock,
            )
            self.oled.start()

    def _on_panic_trigger(self) -> None:
        """Invoked when physical panic button is pressed."""
        self.logger.log_alert(
            threat_type="MANUAL_PANIC_TRIGGER",
            severity="CRITICAL",
            details={"source": "GPIO_PANIC_BUTTON", "timestamp": time.time()},
        )
        if self.oled:
            self.oled.show_alert("PANIC PRESSED", duration_sec=5.0)

    def _signal_handler(self, signum, frame) -> None:
        print("\n[SYSTEM] Termination signal received. Cleaning up...")
        self.running = False

    def run(self) -> None:
        print("==================================================================")
        print(f"  AI SAFETY MONITORING ACTIVE [{self.config.system.device_name}]")
        print("  Press 'p' in GUI for Panic Override | Press 'q' or Ctrl+C to Exit")
        print("==================================================================")

        prev_time = time.time()
        frame_counter = 0

        window_name = f"AI Safety Monitor - {self.config.system.device_name}"
        if not self.args.headless:
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window_name, self.config.camera.width, self.config.camera.height)

        try:
            while self.running:
                ret, frame = self.camera.read()
                if not ret or frame is None:
                    time.sleep(0.01)
                    continue

                now = time.time()
                dt = now - prev_time
                if dt > 0:
                    self.engine.current_fps = 1.0 / dt
                prev_time = now

                # Execute Detection Pipeline
                annotated_frame, alerts = self.engine.process_frame(frame, now)

                # GUI Window Display (if not headless)
                if not self.args.headless:
                    cv2.imshow(window_name, annotated_frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        print("[USER] Quit key pressed.")
                        break
                    elif key in (ord("p"), ord("P")):
                        print("\n[KEYBOARD] Manual Panic Triggered via Keyboard!")
                        self._on_panic_trigger()
                        if self.gpio:
                            self.gpio.trigger_alert("KEYBOARD_PANIC", "CRITICAL", 4.0)

                frame_counter += 1
                if self.args.dry_run and frame_counter >= 10:
                    print("[DRY-RUN] Processed 10 frames successfully. Exiting.")
                    break

        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        print("[SYSTEM] Shutting down AI Safety Monitor...")
        self.running = False
        if hasattr(self, "camera") and self.camera:
            self.camera.stop()
        if self.oled:
            self.oled.stop()
        if self.gpio:
            self.gpio.cleanup()
        if not self.args.headless:
            cv2.destroyAllWindows()
        self.logger.log_info("Safety Monitoring System stopped cleanly.")
        print("[SYSTEM] All components stopped successfully.")


def main():
    args = parse_arguments()
    app = SafetyMonitorApp(args)
    app.run()


if __name__ == "__main__":
    main()
