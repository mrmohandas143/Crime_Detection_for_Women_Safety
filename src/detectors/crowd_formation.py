"""
Condition 8: Unusual Crowd Formation Detector
Detects sudden localized clustering of people using spatial adjacency grouping.
"""

from typing import Any, Dict, List, Set
import numpy as np
from src.detectors.base_detector import BaseDetector, ThreatAlert
from src.tracking.spatial import euclidean_distance
from src.tracking.tracker import TrackedPerson


class CrowdFormationDetector(BaseDetector):
    """
    Evaluates spatial distribution of persons and detects dense clusters exceeding threshold count.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("crowd_formation", config)
        self.cluster_dist_thresh = config.get("cluster_distance_threshold", 85.0)
        self.min_cluster_size = config.get("min_cluster_size", 4)
        self.formation_window = config.get("formation_time_window", 5.0)
        self._last_alert_time = 0.0

    def detect(
        self,
        frame: np.ndarray,
        tracks: Dict[int, TrackedPerson],
        fps: float,
        timestamp: float,
    ) -> List[ThreatAlert]:
        if not self.enabled or len(tracks) < self.min_cluster_size:
            return []

        # Debounce alert to once every 6 seconds
        if timestamp - self._last_alert_time < 6.0:
            return []

        track_ids = list(tracks.keys())
        n = len(track_ids)
        centroids = [tracks[tid].centroid for tid in track_ids]

        # Build adjacency graph for cluster connected components
        adj: Dict[int, List[int]] = {i: [] for i in range(n)}
        for i in range(n):
            for j in range(i + 1, n):
                if euclidean_distance(centroids[i], centroids[j]) <= self.cluster_dist_thresh:
                    adj[i].append(j)
                    adj[j].append(i)

        # Find connected components (clusters)
        visited: Set[int] = set()
        alerts: List[ThreatAlert] = []

        for i in range(n):
            if i not in visited:
                cluster_members = []
                queue = [i]
                visited.add(i)

                while queue:
                    curr = queue.pop(0)
                    cluster_members.append(curr)
                    for neighbor in adj[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)

                if len(cluster_members) >= self.min_cluster_size:
                    cluster_track_ids = [track_ids[idx] for idx in cluster_members]
                    # Compute cluster center
                    avg_x = sum(centroids[idx][0] for idx in cluster_members) / len(cluster_members)
                    avg_y = sum(centroids[idx][1] for idx in cluster_members) / len(cluster_members)

                    self._last_alert_time = timestamp
                    alerts.append(
                        ThreatAlert(
                            threat_type="UNUSUAL_CROWD_FORMATION",
                            severity="HIGH",
                            confidence=0.88,
                            description=(
                                f"Unusual crowd density detected: {len(cluster_members)} persons "
                                f"clustered at ({avg_x:.0f}, {avg_y:.0f})"
                            ),
                            track_ids=cluster_track_ids,
                            details={
                                "cluster_size": len(cluster_members),
                                "cluster_center": [round(avg_x, 1), round(avg_y, 1)],
                                "track_ids": cluster_track_ids,
                            },
                        )
                    )
                    break

        return alerts
