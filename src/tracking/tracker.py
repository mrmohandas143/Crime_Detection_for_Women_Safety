"""
Person Tracker & Trajectory History Manager
Maintains spatial trajectories, velocities, keypoint poses, and lifetime metrics.
"""

from collections import deque
from dataclasses import dataclass, field
import time
from typing import Dict, List, Optional, Tuple
import numpy as np
from src.tracking.spatial import euclidean_distance, calculate_velocity, calculate_iou


@dataclass
class TrackedPerson:
    track_id: int
    bbox: List[float]  # [x1, y1, x2, y2]
    confidence: float
    keypoints: Optional[np.ndarray] = None  # Shape (17, 3): (x, y, conf)
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    history: deque = field(default_factory=lambda: deque(maxlen=60))  # (x, y, timestamp)
    speed_px_per_sec: float = 0.0
    velocity_vector: Tuple[float, float] = (0.0, 0.0)
    disappeared_count: int = 0
    stationary_origin: Tuple[float, float] = (0.0, 0.0)

    @property
    def centroid(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @property
    def width(self) -> float:
        return max(1.0, self.bbox[2] - self.bbox[0])

    @property
    def height(self) -> float:
        return max(1.0, self.bbox[3] - self.bbox[1])

    @property
    def aspect_ratio(self) -> float:
        """Aspect ratio W / H. Normal standing person is < 0.6, fallen person is > 1.0"""
        return self.width / self.height

    @property
    def dwell_time(self) -> float:
        return self.last_seen - self.first_seen


class LightweightTracker:
    """
    Lightweight CPU-friendly Multi-Object Centroid + IoU Tracker.
    Ideal for Raspberry Pi 5 CPU constraints while preserving trajectory histories.
    """

    def __init__(self, max_disappeared: int = 30, max_distance: float = 80.0):
        self.next_track_id = 1
        self.tracks: Dict[int, TrackedPerson] = {}
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance

    def update(
        self,
        detections: List[List[float]],
        confidences: List[float],
        keypoints_list: Optional[List[np.ndarray]] = None,
    ) -> Dict[int, TrackedPerson]:
        """
        Update tracks with new bounding box detections and keypoints.
        detections: list of [x1, y1, x2, y2]
        """
        now = time.time()
        num_dets = len(detections)

        if keypoints_list is None:
            keypoints_list = [None] * num_dets

        # If no tracks exist, register all new detections
        if len(self.tracks) == 0:
            for i in range(num_dets):
                self._register(detections[i], confidences[i], keypoints_list[i], now)
            return self.tracks

        # If no detections in current frame, increment disappeared counter
        if num_dets == 0:
            to_delete = []
            for track_id, track in self.tracks.items():
                track.disappeared_count += 1
                if track.disappeared_count > self.max_disappeared:
                    to_delete.append(track_id)
            for track_id in to_delete:
                del self.tracks[track_id]
            return self.tracks

        # Compute cost matrix between existing tracks and incoming detections (Centroid Dist + IoU)
        track_ids = list(self.tracks.keys())
        track_centroids = [self.tracks[tid].centroid for tid in track_ids]
        det_centroids = [
            ((d[0] + d[2]) / 2.0, (d[1] + d[3]) / 2.0) for d in detections
        ]

        cost_matrix = np.zeros((len(track_ids), num_dets), dtype=np.float32)
        for i, t_cent in enumerate(track_centroids):
            for j, d_cent in enumerate(det_centroids):
                dist = euclidean_distance(t_cent, d_cent)
                iou = calculate_iou(self.tracks[track_ids[i]].bbox, detections[j])
                # Combined distance penalty minus IoU bonus
                cost_matrix[i, j] = dist - (iou * 40.0)

        # Greedy match rows to columns
        rows = cost_matrix.min(axis=1).argsort()
        cols = cost_matrix.argmin(axis=1)[rows]

        assigned_rows = set()
        assigned_cols = set()

        for row, col in zip(rows, cols):
            if row in assigned_rows or col in assigned_cols:
                continue

            # Check if distance exceeds threshold
            t_cent = track_centroids[row]
            d_cent = det_centroids[col]
            if euclidean_distance(t_cent, d_cent) > self.max_distance:
                continue

            track_id = track_ids[row]
            track = self.tracks[track_id]

            # Calculate velocity
            dt = now - track.last_seen
            if dt > 0 and len(track.history) > 0:
                speed, direction = calculate_velocity(track.centroid, det_centroids[col], dt)
                # Exponential moving average filter for smooth speed
                track.speed_px_per_sec = 0.7 * speed + 0.3 * track.speed_px_per_sec
                track.velocity_vector = direction

            track.bbox = detections[col]
            track.confidence = confidences[col]
            track.keypoints = keypoints_list[col]
            track.last_seen = now
            track.disappeared_count = 0
            track.history.append((det_centroids[col][0], det_centroids[col][1], now))

            assigned_rows.add(row)
            assigned_cols.add(col)

        # Unassigned existing tracks
        unassigned_rows = set(range(len(track_ids))) - assigned_rows
        to_delete = []
        for row in unassigned_rows:
            track_id = track_ids[row]
            self.tracks[track_id].disappeared_count += 1
            if self.tracks[track_id].disappeared_count > self.max_disappeared:
                to_delete.append(track_id)

        for track_id in to_delete:
            del self.tracks[track_id]

        # Unassigned detections become new tracks
        unassigned_cols = set(range(num_dets)) - assigned_cols
        for col in unassigned_cols:
            self._register(detections[col], confidences[col], keypoints_list[col], now)

        return self.tracks

    def _register(
        self,
        bbox: List[float],
        confidence: float,
        keypoints: Optional[np.ndarray],
        timestamp: float,
    ) -> None:
        track = TrackedPerson(
            track_id=self.next_track_id,
            bbox=bbox,
            confidence=confidence,
            keypoints=keypoints,
            first_seen=timestamp,
            last_seen=timestamp,
            stationary_origin=((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0),
        )
        c = track.centroid
        track.history.append((c[0], c[1], timestamp))
        self.tracks[self.next_track_id] = track
        self.next_track_id += 1
