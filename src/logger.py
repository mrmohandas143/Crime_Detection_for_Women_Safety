"""
Logging Module
Provides structured rotating logging and asynchronous alert snapshot recording.
"""

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import threading
import time
from typing import Any, Dict, Optional
import cv2
import numpy as np


class SafetyLogger:
    """Central structured logger and evidence recorder for detection alerts."""

    def __init__(
        self,
        log_file: str = "logs/safety_monitor.log",
        snapshot_dir: str = "logs/snapshots",
        log_level: str = "INFO",
        save_snapshots: bool = True,
    ):
        self.log_file = Path(log_file)
        self.snapshot_dir = Path(snapshot_dir)
        self.save_snapshots = save_snapshots

        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger("SafetyMonitor")
        self.logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        self.logger.handlers.clear()

        # Console Handler with clear formatting
        console_fmt = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        c_handler = logging.StreamHandler()
        c_handler.setFormatter(console_fmt)
        self.logger.addHandler(c_handler)

        # File Handler (5 MB max, 5 backup files)
        file_fmt = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "msg": %(message)s}',
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
        f_handler = RotatingFileHandler(
            str(self.log_file), maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        f_handler.setFormatter(file_fmt)
        self.logger.addHandler(f_handler)

        self._last_snapshot_time: Dict[str, float] = {}

    def log_info(self, message: str) -> None:
        self.logger.info(json.dumps({"event": "INFO", "details": message}))

    def log_warning(self, message: str) -> None:
        self.logger.warning(json.dumps({"event": "WARNING", "details": message}))

    def log_error(self, message: str) -> None:
        self.logger.error(json.dumps({"event": "ERROR", "details": message}))

    def log_alert(
        self,
        threat_type: str,
        severity: str,
        details: Dict[str, Any],
        frame: Optional[np.ndarray] = None,
    ) -> Optional[str]:
        """
        Record a safety threat alert, write to log file, and asynchronously save snapshot
        ONLY for harmful / physical threat events (altercations, snatching, falling, harassment, panic).
        """
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        snapshot_path: Optional[str] = None
        now = time.time()

        # Define harmful threat types that warrant photo evidence
        harming_threats = {
            "PHYSICAL_ALTERCATION",
            "SNATCHING_ATTEMPT",
            "FALLING",
            "EVE_TEASING_PROXIMITY",
            "PANIC_MOVEMENT",
            "CROWD_SCATTER_PANIC",
            "MANUAL_PANIC_TRIGGER",
            "KEYBOARD_PANIC",
        }

        # Save snapshot ONLY if the event is a harming threat and not within 5s cooldown
        is_harming_event = (threat_type in harming_threats) or (severity == "CRITICAL")
        last_snap = self._last_snapshot_time.get(threat_type, 0.0)

        if self.save_snapshots and frame is not None and is_harming_event and (now - last_snap >= 5.0):
            self._last_snapshot_time[threat_type] = now
            filename = f"ALERT_{threat_type}_{timestamp_str}.jpg"
            target_path = self.snapshot_dir / filename
            snapshot_path = str(target_path)

            # Save snapshot asynchronously to avoid blocking the main vision loop
            snapshot_frame = frame.copy()

            def _write_image(p: str, img: np.ndarray) -> None:
                try:
                    cv2.imwrite(p, img)
                    print(f"\n[PHOTO-EVIDENCE] Saved incident photo: {p}")
                except Exception as e:
                    print(f"[ERROR] Failed to save snapshot to {p}: {e}")

            threading.Thread(target=_write_image, args=(snapshot_path, snapshot_frame), daemon=True).start()

        event_payload = {
            "event": "THREAT_DETECTED",
            "threat_type": threat_type,
            "severity": severity,
            "details": details,
            "snapshot": snapshot_path,
        }

        self.logger.warning(json.dumps(event_payload))
        return snapshot_path
