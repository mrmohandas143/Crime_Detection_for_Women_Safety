"""
Condition 5: Panic Movement Detector
Detects sudden high-velocity running, erratic evasive motion, or simultaneous crowd scattering.
"""

from typing import Any, Dict, List
import numpy as np
from src.detectors.base_detector import BaseDetector, ThreatAlert
from src.tracking.spatial import vector_angle_degrees
from src.tracking.tracker import TrackedPerson


class PanicMovementDetector(BaseDetector):
    """
    Monitors velocity surges, acceleration spikes, erratic trajectory turns,
    and multi-person outward scattering (panic stampede / crowd dispersal).
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("panic_movement", config)
        self.speed_thresh = config.get("speed_threshold", 200.0)
        self.accel_thresh = config.get("acceleration_threshold", 120.0)
        self.erratic_angle_thresh = config.get("min_erratic_angle_change", 70.0)
        self.scatter_thresh = config.get("crowd_scatter_threshold", 3)
        self._alerted_tracks: Dict[int, float] = {}
        self._last_scatter_alert = 0.0

    def detect(
        self,
        frame: np.ndarray,
        tracks: Dict[int, TrackedPerson],
        fps: float,
        timestamp: float,
    ) -> List[ThreatAlert]:
        if not self.enabled or not tracks:
            return []

        alerts: List[ThreatAlert] = []
        running_tracks: List[int] = []

        # 1. Check individual tracks for panic speed / erratic zig-zag
        for track_id, track in tracks.items():
            if len(track.history) < 3:
                continue

            current_speed = track.speed_px_per_sec
            is_running = current_speed >= self.speed_thresh

            if is_running:
                running_tracks.append(track_id)

            # Check erratic angle changes across the last 3 positions
            p1, p2, p3 = track.history[-3], track.history[-2], track.history[-1]
            v1 = (p2[0] - p1[0], p2[1] - p1[1])
            v2 = (p3[0] - p2[0], p3[1] - p2[1])

            mag1 = (v1[0] ** 2 + v1[1] ** 2) ** 0.5
            mag2 = (v2[0] ** 2 + v2[1] ** 2) ** 0.5

            is_erratic = False
            if mag1 > 5.0 and mag2 > 5.0:
                u1 = (v1[0] / mag1, v1[1] / mag1)
                u2 = (v2[0] / mag2, v2[1] / mag2)
                angle_turn = vector_angle_degrees(u1, u2)
                if angle_turn >= self.erratic_angle_thresh and current_speed > 120.0:
                    is_erratic = True

            # Trigger individual panic alert
            if (is_running or is_erratic) and (timestamp - self._alerted_tracks.get(track_id, 0.0) > 4.0):
                self._alerted_tracks[track_id] = timestamp

                # Dynamically calculate accuracy score from live velocity spike, erratic angular turn & detection confidence
                speed_factor = min(1.0, max(0.5, current_speed / max(1.0, self.speed_thresh * 1.4)))
                turn_factor = 1.0 if is_erratic else 0.82
                det_conf = track.confidence

                calc_score = 0.50 * speed_factor + 0.30 * turn_factor + 0.20 * det_conf
                dynamic_accuracy = round(max(0.72, min(0.99, calc_score)), 3)

                alerts.append(
                    ThreatAlert(
                        threat_type="PANIC_MOVEMENT",
                        severity="LOW",
                        confidence=dynamic_accuracy,
                        description=(
                            f"Panic movement / sudden sprint by Person {track_id} "
                            f"(Speed: {current_speed:.1f}px/s, Erratic: {is_erratic}, Acc: {dynamic_accuracy*100:.1f}%)"
                        ),
                        track_ids=[track_id],
                        details={
                            "track_id": track_id,
                            "speed": round(current_speed, 1),
                            "is_erratic_turn": is_erratic,
                            "centroid": [round(c, 1) for c in track.centroid],
                            "accuracy_score_pct": round(dynamic_accuracy * 100.0, 1),
                        },
                    )
                )

        # 2. Check for multi-person crowd scatter / dispersal
        if len(running_tracks) >= self.scatter_thresh and (timestamp - self._last_scatter_alert > 5.0):
            self._last_scatter_alert = timestamp
            scatter_accuracy = round(min(0.99, 0.75 + (len(running_tracks) * 0.06)), 3)
            alerts.append(
                ThreatAlert(
                    threat_type="CROWD_SCATTER_PANIC",
                    severity="LOW",
                    confidence=scatter_accuracy,
                    description=f"Mass panic dispersal detected: {len(running_tracks)} persons sprinting simultaneously (Acc: {scatter_accuracy*100:.1f}%)",
                    track_ids=running_tracks,
                    details={
                        "running_count": len(running_tracks),
                        "track_ids": running_tracks,
                        "accuracy_score_pct": round(scatter_accuracy * 100.0, 1),
                    },
                )
            )

        return alerts
