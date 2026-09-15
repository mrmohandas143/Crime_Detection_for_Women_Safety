"""
Core Pipeline Engine Module
Orchestrates AI inference (YOLOv8-pose), object tracking, 9-condition threat detection,
GPIO/OLED alerts, and diagnostic telemetry.
"""

import time
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np
try:
    import torch
except ImportError:
    torch = None

from src.config_loader import AppConfig
from src.detectors import (
    BaseDetector,
    ThreatAlert,
    FallingDetector,
    LoiteringDetector,
    UnauthorizedEntryDetector,
    CrowdFormationDetector,
    PanicMovementDetector,
    AltercationDetector,
    SuspiciousFollowingDetector,
    SnatchingDetector,
    EveTeasingDetector,
)
from src.hardware.gpio_alert import GPIOAlertController
from src.hardware.oled_display import OLEDDisplayController
from src.logger import SafetyLogger
from src.tracking.tracker import LightweightTracker, TrackedPerson


class SafetyMonitoringEngine:
    """
    Central pipeline orchestrator running on the Raspberry Pi 5 CPU.
    """

    def __init__(
        self,
        config: AppConfig,
        gpio_controller: Optional[GPIOAlertController] = None,
        oled_controller: Optional[OLEDDisplayController] = None,
        logger: Optional[SafetyLogger] = None,
    ):
        self.config = config
        self.gpio = gpio_controller
        self.oled = oled_controller
        self.logger = logger or SafetyLogger(
            log_file=config.system.log_file,
            snapshot_dir=config.system.snapshot_dir,
            log_level=config.system.log_level,
            save_snapshots=config.system.save_alert_snapshots,
        )

        # Configure CPU threading
        if torch is not None:
            num_threads = self.config.inference.num_threads
            torch.set_num_threads(num_threads)

        # Initialize AI model
        self.model = None
        self._init_model()

        # Initialize Tracker
        self.tracker = LightweightTracker(
            max_disappeared=self.config.tracker.max_disappeared,
            max_distance=90.0,
        )

        # Initialize 9 Threat Detectors
        self.detectors: List[BaseDetector] = []
        self._init_detectors()

        # Metrics
        self.frame_index = 0
        self.current_fps = 0.0
        self.last_inference_boxes: List[List[float]] = []
        self.last_inference_confs: List[float] = []
        self.last_inference_kpts: Optional[List[np.ndarray]] = None
        self.recent_alerts: List[ThreatAlert] = []

    def _init_model(self) -> None:
        model_name = self.config.inference.model_type
        print(f"[AI] Loading model '{model_name}' on CPU ({self.config.inference.num_threads} threads)...")
        try:
            from ultralytics import YOLO

            self.model = YOLO(model_name)
            # Run a dummy warmup pass
            dummy = np.zeros((self.config.camera.height, self.config.camera.width, 3), dtype=np.uint8)
            self.model.predict(
                dummy,
                device="cpu",
                verbose=False,
                conf=self.config.inference.confidence_threshold,
            )
            print("[AI] YOLO model loaded and warmed up successfully.")
        except Exception as e:
            print(f"[AI-WARN] Failed to load YOLO model '{model_name}': {e}. System running in mock inference mode.")
            self.model = None

    def _init_detectors(self) -> None:
        det_cfg = self.config.detectors
        self.detectors = [
            SnatchingDetector(det_cfg.get("snatching", {})),
            EveTeasingDetector(det_cfg.get("eve_teasing", {})),
            SuspiciousFollowingDetector(det_cfg.get("suspicious_following", {})),
            LoiteringDetector(det_cfg.get("loitering", {})),
            PanicMovementDetector(det_cfg.get("panic_movement", {})),
            AltercationDetector(det_cfg.get("altercation", {})),
            FallingDetector(det_cfg.get("falling", {})),
            CrowdFormationDetector(det_cfg.get("crowd_formation", {})),
            UnauthorizedEntryDetector(det_cfg.get("unauthorized_entry", {})),
        ]
        enabled_count = sum(1 for d in self.detectors if d.enabled)
        print(f"[ENGINE] Initialized {enabled_count}/9 active threat detectors.")

    def process_frame(self, frame: np.ndarray, timestamp: float) -> Tuple[np.ndarray, List[ThreatAlert]]:
        """
        Processes a single video frame through the detection and alerting pipeline.
        """
        self.frame_index += 1
        should_run_inference = (self.frame_index % self.config.inference.frame_skip == 0)

        boxes: List[List[float]] = []
        confs: List[float] = []
        kpts: Optional[List[np.ndarray]] = None

        if should_run_inference and self.model is not None:
            # Run YOLOv8-pose inference
            try:
                results = self.model.predict(
                    frame,
                    classes=[0],  # Filter only 'person' class
                    conf=self.config.inference.confidence_threshold,
                    iou=self.config.inference.iou_threshold,
                    device=self.config.inference.device,
                    verbose=False,
                )

                if results and len(results) > 0:
                    r = results[0]
                    if r.boxes is not None and len(r.boxes) > 0:
                        boxes = r.boxes.xyxy.cpu().numpy().tolist()
                        confs = r.boxes.conf.cpu().numpy().tolist()

                    if hasattr(r, "keypoints") and r.keypoints is not None:
                        kpts = r.keypoints.data.cpu().numpy()

                self.last_inference_boxes = boxes
                self.last_inference_confs = confs
                self.last_inference_kpts = kpts
            except Exception as e:
                print(f"[ENGINE-ERR] Inference error: {e}")
        else:
            # Reuse last detections for intermediate tracking frames
            boxes = self.last_inference_boxes
            confs = self.last_inference_confs
            kpts = self.last_inference_kpts

        # Update Multi-Object Tracker
        tracks = self.tracker.update(boxes, confs, kpts)

        # Run all 9 Threat Detectors
        active_alerts: List[ThreatAlert] = []
        for detector in self.detectors:
            try:
                alerts = detector.detect(frame, tracks, self.current_fps, timestamp)
                if alerts:
                    active_alerts.extend(alerts)
            except Exception as e:
                print(f"[ENGINE-ERR] Detector '{detector.name}' exception: {e}")

        # Render visual debug overlays on frame
        annotated_frame = self.annotate_frame(frame, tracks, active_alerts)

        # Handle Alerts (GPIO, OLED, Logger with evidence snapshot)
        if active_alerts:
            self._handle_threat_alerts(active_alerts, annotated_frame)

        # Update OLED status
        if self.oled:
            self.oled.update_metrics(fps=self.current_fps, person_count=len(tracks))

        self.recent_alerts = active_alerts

        return annotated_frame, active_alerts

    def _handle_threat_alerts(self, alerts: List[ThreatAlert], frame: np.ndarray) -> None:
        """Dispatches prioritized alerts to hardware actuators and logging infrastructure."""
        # Find highest severity
        severity_order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        highest_alert = max(alerts, key=lambda a: severity_order.get(a.severity, 1))

        # 1. Trigger GPIO LED and Buzzer
        if self.gpio:
            dur = 3.5 if highest_alert.severity == "CRITICAL" else 2.0
            self.gpio.trigger_alert(
                threat_type=highest_alert.threat_type,
                severity=highest_alert.severity,
                duration_sec=dur,
            )

        # 2. Update OLED screen banner
        if self.oled:
            self.oled.show_alert(highest_alert.threat_type, duration_sec=3.0)

        # 3. Log structured alert and save snapshot image
        for alert in alerts:
            self.logger.log_alert(
                threat_type=alert.threat_type,
                severity=alert.severity,
                details=alert.details,
                frame=frame,
            )

    def annotate_frame(
        self,
        frame: np.ndarray,
        tracks: Dict[int, TrackedPerson],
        alerts: List[ThreatAlert],
    ) -> np.ndarray:
        """Draws bounding boxes, motion trails, zone boundaries, and threat overlays."""
        vis = frame.copy()

        # Draw Zones
        for z in self.config.detectors.get("unauthorized_entry", {}).get("zones", []):
            poly = np.array(z.get("polygon", []), dtype=np.int32)
            if len(poly) >= 3:
                cv2.polylines(vis, [poly], isClosed=True, color=(0, 0, 255), thickness=2)
                cv2.putText(
                    vis, f"RESTRICTED: {z.get('name')}",
                    (poly[0][0], max(15, poly[0][1] - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1,
                )

        for z in self.config.detectors.get("loitering", {}).get("zones", []):
            poly = np.array(z.get("polygon", []), dtype=np.int32)
            if len(poly) >= 3:
                cv2.polylines(vis, [poly], isClosed=True, color=(0, 255, 255), thickness=1)
                cv2.putText(
                    vis, f"ZONE: {z.get('name')}",
                    (poly[0][0], max(15, poly[0][1] - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1,
                )

        # Draw Person Tracks & Trajectories
        for track_id, track in tracks.items():
            x1, y1, x2, y2 = map(int, track.bbox)
            color = (0, 255, 0)

            # Draw trajectory path history
            if len(track.history) >= 2:
                points = [np.array([int(p[0]), int(p[1])]) for p in track.history]
                for i in range(1, len(points)):
                    cv2.line(vis, tuple(points[i - 1]), tuple(points[i]), (255, 200, 0), 1)

            # Draw Bounding Box
            cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)
            label = f"ID:{track_id} | {track.speed_px_per_sec:.0f}px/s | Dwell:{track.dwell_time:.1f}s"
            cv2.putText(
                vis, label, (x1, max(15, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1,
            )

        # Draw Active Alerts Banner
        if alerts:
            alert_text = f"ALERT: {alerts[0].threat_type} ({alerts[0].severity})"
            cv2.rectangle(vis, (0, 0), (vis.shape[1], 36), (0, 0, 220), -1)
            cv2.putText(
                vis, alert_text, (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2,
            )

        # Telemetry HUD
        hud_text = f"FPS: {self.current_fps:.1f} | People: {len(tracks)} | CPU"
        cv2.putText(
            vis, hud_text, (10, vis.shape[0] - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1,
        )

        return vis
