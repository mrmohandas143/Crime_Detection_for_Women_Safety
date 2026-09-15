"""
Condition 7: Falling Detector
Detects sudden collapses or falls using bounding box aspect ratio inversion,
downward vertical velocity spikes, and horizontal torso pose keypoint angles.
"""

import math
import time
from typing import Any, Dict, List
import numpy as np
from src.detectors.base_detector import BaseDetector, ThreatAlert
from src.tracking.tracker import TrackedPerson


class FallingDetector(BaseDetector):
    """
    Detects person collapse or falling events via:
    1. Bounding box aspect ratio (Width / Height > 1.15)
    2. Downward vertical velocity spike
    3. Pose keypoint torso angle relative to ground plane
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("falling", config)
        self.aspect_ratio_thresh = config.get("aspect_ratio_threshold", 1.15)
        self.downward_vel_thresh = config.get("downward_velocity_thresh", 130.0)
        self.torso_angle_thresh = config.get("torso_angle_threshold", 30.0)
        self.ground_plane_y_min = config.get("ground_plane_y_min", 200)
        self._fallen_tracker_alerts: Dict[int, float] = {}

    def detect(
        self,
        frame: np.ndarray,
        tracks: Dict[int, TrackedPerson],
        fps: float,
        timestamp: float,
    ) -> List[ThreatAlert]:
        if not self.enabled:
            return []

        alerts: List[ThreatAlert] = []

        for track_id, track in tracks.items():
            # Suppress repeat alerts for same track within 5 seconds
            if track_id in self._fallen_tracker_alerts:
                if timestamp - self._fallen_tracker_alerts[track_id] < 5.0:
                    continue

            # Check 1: Aspect ratio (fallen person is wider than tall)
            aspect_ratio = track.aspect_ratio
            is_horizontal_bbox = aspect_ratio > self.aspect_ratio_thresh

            # Check 2: Vertical velocity vector (moving downwards rapidly)
            downward_vel = 0.0
            if len(track.history) >= 2:
                prev_y = track.history[-2][1]
                curr_y = track.history[-1][1]
                dt = track.history[-1][2] - track.history[-2][2]
                if dt > 0.001:
                    downward_vel = (curr_y - prev_y) / dt

            # Check 3: Pose Keypoints Torso Angle (if keypoints are available)
            is_horizontal_pose = False
            if track.keypoints is not None and len(track.keypoints) >= 13:
                # Keypoints (COCO format): 5: Left Shoulder, 6: Right Shoulder, 11: Left Hip, 12: Right Hip
                ls, rs = track.keypoints[5], track.keypoints[6]
                lh, rh = track.keypoints[11], track.keypoints[12]

                # Check shoulder-hip vector angle
                if (ls[2] > 0.4 or rs[2] > 0.4) and (lh[2] > 0.4 or rh[2] > 0.4):
                    shoulder_y = (ls[1] + rs[1]) / 2.0
                    shoulder_x = (ls[0] + rs[0]) / 2.0
                    hip_y = (lh[1] + rh[1]) / 2.0
                    hip_x = (lh[0] + rh[0]) / 2.0

                    dx = abs(hip_x - shoulder_x)
                    dy = abs(hip_y - shoulder_y)
                    # Angle relative to horizontal plane
                    angle_deg = math.degrees(math.atan2(dy, max(1e-5, dx)))
                    if angle_deg < self.torso_angle_thresh:
                        is_horizontal_pose = True

            # Trigger condition: Horizontal bounding box + (downward velocity OR horizontal pose)
            if is_horizontal_bbox and (downward_vel > self.downward_vel_thresh or is_horizontal_pose):
                self._fallen_tracker_alerts[track_id] = timestamp
                alerts.append(
                    ThreatAlert(
                        threat_type="FALLING",
                        severity="MEDIUM",
                        confidence=0.88,
                        description=f"Person {track_id} collapsed / fell to ground (aspect_ratio={aspect_ratio:.2f}, vy={downward_vel:.1f}px/s)",
                        track_ids=[track_id],
                        details={
                            "track_id": track_id,
                            "aspect_ratio": round(aspect_ratio, 2),
                            "downward_velocity": round(downward_vel, 1),
                            "centroid": [round(c, 1) for c in track.centroid],
                            "is_horizontal_pose": is_horizontal_pose,
                        },
                    )
                )

        return alerts
