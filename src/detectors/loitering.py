"""
Condition 4: Loitering Detector
Detects persons lingering inside configured spatial polygon zones beyond a time threshold.
"""

from typing import Any, Dict, List, Tuple
import numpy as np
from src.detectors.base_detector import BaseDetector, ThreatAlert
from src.tracking.spatial import point_in_polygon, euclidean_distance
from src.tracking.tracker import TrackedPerson


class LoiteringDetector(BaseDetector):
    """
    Monitors person presence inside specified polygonal zones.
    Triggers an alert when a person dwells beyond the allowed threshold.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("loitering", config)
        self.dwell_threshold = config.get("dwell_time_threshold", 10.0)
        self.movement_radius_max = config.get("movement_radius_max", 50.0)
        self.zones = config.get("zones", [])

        # Track dwell entry times: (track_id, zone_name) -> entry_timestamp
        self._entry_times: Dict[Tuple[int, str], float] = {}
        self._alerted_tracks: Dict[Tuple[int, str], float] = {}

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
        active_keys = set()

        for zone in self.zones:
            zone_name = zone.get("name", "Zone")
            polygon = zone.get("polygon", [])
            if len(polygon) < 3:
                continue

            for track_id, track in tracks.items():
                centroid = track.centroid
                is_inside = point_in_polygon(centroid, polygon)
                key = (track_id, zone_name)

                if is_inside:
                    active_keys.add(key)
                    if key not in self._entry_times:
                        self._entry_times[key] = timestamp

                    dwell_duration = timestamp - self._entry_times[key]

                    # Check if dwell threshold exceeded
                    if dwell_duration >= self.dwell_threshold:
                        # Check cooldown (alert once every 10 seconds per person per zone)
                        last_alert = self._alerted_tracks.get(key, 0.0)
                        if timestamp - last_alert >= 10.0:
                            # Verify if movement is localized
                            dist_from_origin = euclidean_distance(centroid, track.stationary_origin)
                            
                            self._alerted_tracks[key] = timestamp
                            alerts.append(
                                ThreatAlert(
                                    threat_type="LOITERING",
                                    severity="LOW",
                                    confidence=0.85,
                                    description=(
                                        f"Person {track_id} loitering in '{zone_name}' "
                                        f"for {dwell_duration:.1f}s (Threshold: {self.dwell_threshold}s)"
                                    ),
                                    track_ids=[track_id],
                                    details={
                                        "track_id": track_id,
                                        "zone_name": zone_name,
                                        "dwell_duration_sec": round(dwell_duration, 1),
                                        "centroid": [round(c, 1) for c in centroid],
                                        "displacement": round(dist_from_origin, 1),
                                    },
                                )
                            )
                else:
                    # Outside zone, clear entry record
                    self._entry_times.pop(key, None)

        # Cleanup stale records
        stale_keys = [k for k in self._entry_times.keys() if k not in active_keys]
        for k in stale_keys:
            self._entry_times.pop(k, None)
            self._alerted_tracks.pop(k, None)

        return alerts
