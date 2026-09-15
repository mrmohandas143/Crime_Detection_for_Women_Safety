"""
Condition 1: Snatching Detector (Grab-and-Run Motion)
Detects chain/purse snatching patterns using approach-intercept-escape dynamics.
"""

from typing import Any, Dict, List, Tuple
import numpy as np
from src.detectors.base_detector import BaseDetector, ThreatAlert
from src.tracking.spatial import euclidean_distance, vector_angle_degrees
from src.tracking.tracker import TrackedPerson


class SnatchingDetector(BaseDetector):
    """
    Detects sudden grab-and-run snatching events:
    Phase 1: Fast approach toward victim.
    Phase 2: Brief close-proximity contact window (<1.5s).
    Phase 3: High-speed escape acceleration away from victim.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("snatching", config)
        self.min_approach_speed = config.get("min_approach_speed", 160.0)
        self.min_escape_speed = config.get("min_escape_speed", 220.0)
        self.max_interaction_dist = config.get("max_interaction_dist", 70.0)
        self.max_interaction_time = config.get("max_interaction_time", 1.5)
        self.divergence_angle_min = config.get("divergence_angle_min", 60.0)

        # Track contact state: (snatcher_id, victim_id) -> (contact_timestamp, approach_speed)
        self._proximity_events: Dict[Tuple[int, int], Tuple[float, float]] = {}
        self._last_alert_time = 0.0

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

        for i in range(len(track_ids)):
            for j in range(len(track_ids)):
                if i == j:
                    continue

                t_attacker, t_victim = tracks[track_ids[i]], tracks[track_ids[j]]
                attacker_id, victim_id = track_ids[i], track_ids[j]
                pair_key = (attacker_id, victim_id)

                dist = euclidean_distance(t_attacker.centroid, t_victim.centroid)

                # Phase 2: Intercept/Proximity registration
                if dist <= self.max_interaction_dist:
                    if pair_key not in self._proximity_events:
                        self._proximity_events[pair_key] = (timestamp, t_attacker.speed_px_per_sec)
                else:
                    # If previously in proximity, check for escape phase
                    if pair_key in self._proximity_events:
                        contact_time, approach_speed = self._proximity_events.pop(pair_key)
                        contact_duration = timestamp - contact_time

                        # Check if contact was brief and attacker is now sprinting away
                        if contact_duration <= self.max_interaction_time:
                            escape_speed = t_attacker.speed_px_per_sec

                            if escape_speed >= self.min_escape_speed or (
                                escape_speed > approach_speed * 1.4 and escape_speed > 180.0
                            ):
                                if timestamp - self._last_alert_time > 4.0:
                                    self._last_alert_time = timestamp
                                    alerts.append(
                                        ThreatAlert(
                                            threat_type="SNATCHING_ATTEMPT",
                                            severity="MEDIUM",
                                            confidence=0.85,
                                            description=(
                                                f"Grab-and-run snatching pattern: Person {attacker_id} approached "
                                                f"Person {victim_id} and fled at {escape_speed:.0f}px/s"
                                            ),
                                            track_ids=[attacker_id, victim_id],
                                            details={
                                                "snatcher_id": attacker_id,
                                                "victim_id": victim_id,
                                                "escape_speed": round(escape_speed, 1),
                                                "approach_speed": round(approach_speed, 1),
                                                "contact_duration": round(contact_duration, 2),
                                            },
                                        )
                                    )

        return alerts
