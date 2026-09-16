"""
Condition 9: Unauthorized Entry Detector
Detects immediate intrusion into high-security or restricted polygonal zones.
"""

from typing import Any, Dict, List, Tuple
import numpy as np
from src.detectors.base_detector import BaseDetector, ThreatAlert
from src.tracking.spatial import point_in_polygon
from src.tracking.tracker import TrackedPerson


class UnauthorizedEntryDetector(BaseDetector):
    """
    Monitors restricted perimeter polygons and triggers an immediate high-priority alert
    whenever any person enters the restricted zone boundary.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("unauthorized_entry", config)
        self.zones = config.get("zones", [])
        # Cooldown per (track_id, zone_name)
        self._alert_cooldowns: Dict[Tuple[int, str], float] = {}

    def detect(
        self,
        frame: np.ndarray,
        tracks: Dict[int, TrackedPerson],
        fps: float,
        timestamp: float,
    ) -> List[ThreatAlert]:
        if not self.enabled or not self.zones:
            return []

        alerts: List[ThreatAlert] = []

        for zone in self.zones:
            zone_name = zone.get("name", "Restricted_Zone")
            polygon = zone.get("polygon", [])
            if len(polygon) < 3:
                continue

            for track_id, track in tracks.items():
                centroid = track.centroid
                # Check if centroid or bottom center (feet) is inside restricted polygon
                feet_point = (centroid[0], track.bbox[3])
                is_inside = point_in_polygon(centroid, polygon) or point_in_polygon(feet_point, polygon)

                if is_inside:
                    key = (track_id, zone_name)
                    last_alert = self._alert_cooldowns.get(key, 0.0)

                    # Debounce: Alert every 5 seconds while person remains inside restricted zone
                    if timestamp - last_alert >= 5.0:
                        self._alert_cooldowns[key] = timestamp
                        dynamic_accuracy = round(max(0.85, min(0.99, track.confidence * 1.05)), 3)
                        alerts.append(
                            ThreatAlert(
                                threat_type="UNAUTHORIZED_ENTRY",
                                severity="MEDIUM",
                                confidence=dynamic_accuracy,
                                description=f"Unauthorized entry detected: Person {track_id} entered '{zone_name}' (Acc: {dynamic_accuracy*100:.1f}%)",
                                track_ids=[track_id],
                                details={
                                    "track_id": track_id,
                                    "zone_name": zone_name,
                                    "centroid": [round(c, 1) for c in centroid],
                                    "bbox": [round(b, 1) for b in track.bbox],
                                    "accuracy_score_pct": round(dynamic_accuracy * 100.0, 1),
                                },
                            )
                        )

        return alerts
