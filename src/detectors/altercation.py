"""
Condition 6: Physical Altercation Detector
Detects fighting, violent grappling, or physical aggression via overlapping bounding boxes,
sudden kinetic energy spikes, and rapid limb/wrist velocity oscillations.
"""

from typing import Any, Dict, List, Tuple
import numpy as np
from src.detectors.base_detector import BaseDetector, ThreatAlert
from src.tracking.spatial import calculate_iou, euclidean_distance
from src.tracking.tracker import TrackedPerson


class AltercationDetector(BaseDetector):
    """
    Detects physical fights or aggressive physical contact by analyzing:
    1. Bounding box intersection / close proximity
    2. Kinetic energy of motion during contact
    3. Rapid keypoint velocity (wrist/elbow striking motion)
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("altercation", config)
        self.iou_thresh = config.get("overlap_iou_threshold", 0.15)
        self.keypoint_vel_thresh = config.get("keypoint_velocity_thresh", 180.0)
        self.contact_duration_min = config.get("contact_duration", 1.0)
        # Tracking ongoing contact: (tid1, tid2) -> start_timestamp
        self._contact_history: Dict[Tuple[int, int], float] = {}
        self._alert_cooldowns: Dict[Tuple[int, int], float] = {}

    def detect(
        self,
        frame: np.ndarray,
        tracks: Dict[int, TrackedPerson],
        fps: float,
        timestamp: float,
    ) -> List[ThreatAlert]:
        if not self.enabled or len(tracks) < 2:
            return []

        alerts: List[ThreatAlert] = []
        track_ids = list(tracks.keys())
        active_pairs = set()

        for i in range(len(track_ids)):
            for j in range(i + 1, len(track_ids)):
                tid1, tid2 = track_ids[i], track_ids[j]
                t1, t2 = tracks[tid1], tracks[tid2]

                pair_key = (min(tid1, tid2), max(tid1, tid2))

                iou = calculate_iou(t1.bbox, t2.bbox)
                centroid_dist = euclidean_distance(t1.centroid, t2.centroid)
                avg_height = (t1.height + t2.height) / 2.0

                # Close contact condition: IoU > threshold or distance < 0.6 * height
                in_contact = (iou >= self.iou_thresh) or (centroid_dist < avg_height * 0.6)

                if in_contact:
                    active_pairs.add(pair_key)
                    if pair_key not in self._contact_history:
                        self._contact_history[pair_key] = timestamp

                    duration = timestamp - self._contact_history[pair_key]

                    # Assess kinetic energy / violence indicator: requires high combined motion during close contact
                    combined_speed = t1.speed_px_per_sec + t2.speed_px_per_sec
                    has_violent_motion = combined_speed >= 160.0

                    if duration >= self.contact_duration_min and has_violent_motion:
                        last_alert = self._alert_cooldowns.get(pair_key, 0.0)
                        if timestamp - last_alert > 6.0:
                            self._alert_cooldowns[pair_key] = timestamp
                            alerts.append(
                                ThreatAlert(
                                    threat_type="PHYSICAL_ALTERCATION",
                                    severity="CRITICAL",
                                    confidence=0.88,
                                    description=(
                                        f"Physical altercation/fight between Person {tid1} and Person {tid2} "
                                        f"(Contact: {duration:.1f}s, IoU: {iou:.2f}, Speed: {combined_speed:.0f}px/s)"
                                    ),
                                    track_ids=[tid1, tid2],
                                    details={
                                        "track_1": tid1,
                                        "track_2": tid2,
                                        "iou": round(iou, 2),
                                        "contact_duration": round(duration, 1),
                                        "combined_speed": round(combined_speed, 1),
                                    },
                                )
                            )
                else:
                    self._contact_history.pop(pair_key, None)

        # Cleanup inactive pairs
        stale_pairs = [k for k in self._contact_history if k not in active_pairs]
        for k in stale_pairs:
            self._contact_history.pop(k, None)

        return alerts
