"""
Condition 3: Suspicious Following Detector
Detects one person consistently trailing another over time using trajectory correlation,
heading alignment, and distance consistency.
"""

from typing import Any, Dict, List, Tuple
import numpy as np
from src.detectors.base_detector import BaseDetector, ThreatAlert
from src.tracking.spatial import calculate_trajectory_similarity, euclidean_distance
from src.tracking.tracker import TrackedPerson


class SuspiciousFollowingDetector(BaseDetector):
    """
    Identifies stalking / trailing behavior where a follower mirrors the leader's trajectory
    while maintaining a lagging distance over a sustained duration.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("suspicious_following", config)
        self.min_duration = config.get("min_tracking_duration", 4.0)
        self.sim_thresh = config.get("trajectory_similarity", 0.78)
        self.min_dist = config.get("min_distance", 40.0)
        self.max_dist = config.get("max_distance", 180.0)
        self.min_dist_traveled = config.get("min_distance_traveled", 80.0)

        # Pair state: (leader_id, follower_id) -> start_timestamp
        self._following_pairs: Dict[Tuple[int, int], float] = {}
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
            for j in range(len(track_ids)):
                if i == j:
                    continue

                id_lead, id_foll = track_ids[i], track_ids[j]
                t_lead, t_foll = tracks[id_lead], tracks[id_foll]

                # Need sufficient trajectory history
                if len(t_lead.history) < 10 or len(t_foll.history) < 10:
                    continue

                # Check total displacement to ignore stationary standing pairs
                lead_disp = euclidean_distance(t_lead.history[0][:2], t_lead.history[-1][:2])
                foll_disp = euclidean_distance(t_foll.history[0][:2], t_foll.history[-1][:2])
                if lead_disp < self.min_dist_traveled or foll_disp < self.min_dist_traveled:
                    continue

                # Current distance between pair
                curr_dist = euclidean_distance(t_lead.centroid, t_foll.centroid)
                if not (self.min_dist <= curr_dist <= self.max_dist):
                    continue

                # Compute trajectory vector alignment (cosine similarity)
                similarity = calculate_trajectory_similarity(list(t_lead.history), list(t_foll.history))
                if similarity >= self.sim_thresh:
                    # Directional check: follower must be positioned behind leader along leader's motion vector
                    if len(t_lead.history) >= 2:
                        v_lead_x = t_lead.history[-1][0] - t_lead.history[0][0]
                        v_lead_y = t_lead.history[-1][1] - t_lead.history[0][1]
                        rel_x = t_lead.centroid[0] - t_foll.centroid[0]
                        rel_y = t_lead.centroid[1] - t_foll.centroid[1]
                        # Dot product must be positive (leader is ahead of follower)
                        if (v_lead_x * rel_x + v_lead_y * rel_y) <= 0:
                            continue

                    pair_key = (id_lead, id_foll)
                    active_pairs.add(pair_key)

                    if pair_key not in self._following_pairs:
                        self._following_pairs[pair_key] = timestamp

                    duration = timestamp - self._following_pairs[pair_key]
                    if duration >= self.min_duration:
                        last_alert = self._alert_cooldowns.get(pair_key, 0.0)
                        if timestamp - last_alert > 8.0:
                            self._alert_cooldowns[pair_key] = timestamp

                            # Dynamically calculate accuracy score based on trajectory similarity, trailing duration & distance stability
                            sim_factor = min(1.0, max(0.6, similarity / 0.95))
                            dur_factor = min(1.0, duration / max(2.0, self.min_duration * 1.5))
                            dist_factor = max(0.6, 1.0 - (abs(curr_dist - 90.0) / 150.0))
                            det_conf = (t_lead.confidence + t_foll.confidence) / 2.0

                            calc_score = 0.40 * sim_factor + 0.30 * dur_factor + 0.15 * dist_factor + 0.15 * det_conf
                            dynamic_accuracy = round(max(0.72, min(0.98, calc_score)), 3)

                            alerts.append(
                                ThreatAlert(
                                    threat_type="SUSPICIOUS_FOLLOWING",
                                    severity="LOW",
                                    confidence=dynamic_accuracy,
                                    description=(
                                        f"Suspicious following: Person {id_foll} is trailing Person {id_lead} "
                                        f"for {duration:.1f}s (Sim: {similarity:.2f}, Acc: {dynamic_accuracy*100:.1f}%)"
                                    ),
                                    track_ids=[id_lead, id_foll],
                                    details={
                                        "leader_id": id_lead,
                                        "follower_id": id_foll,
                                        "duration_sec": round(duration, 1),
                                        "similarity": round(similarity, 2),
                                        "current_distance": round(curr_dist, 1),
                                        "accuracy_score_pct": round(dynamic_accuracy * 100.0, 1),
                                    },
                                )
                            )
                else:
                    self._following_pairs.pop((id_lead, id_foll), None)

        # Clean stale
        stale_pairs = [k for k in self._following_pairs if k not in active_pairs]
        for k in stale_pairs:
            self._following_pairs.pop(k, None)

        return alerts
