"""
Spatial & Geometric Mathematics Utilities
Handles 2D vector geometry, polygon containment, trajectory metrics, and cosine similarity.
"""

from typing import List, Tuple, Optional
import math
import numpy as np


def point_in_polygon(point: Tuple[float, float], polygon: List[List[float]]) -> bool:
    """
    Ray-casting algorithm to determine if a 2D point (x, y) is inside a polygon.
    """
    x, y = point
    n = len(polygon)
    inside = False

    p1x, p1y = polygon[0]
    for i in range(n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y

    return inside


def euclidean_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Compute 2D Euclidean distance between two points."""
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def calculate_iou(boxA: List[float], boxB: List[float]) -> float:
    """
    Calculate Intersection over Union (IoU) of two bounding boxes [x1, y1, x2, y2].
    """
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = max(0, boxA[2] - boxA[0]) * max(0, boxA[3] - boxA[1])
    boxBArea = max(0, boxB[2] - boxB[0]) * max(0, boxB[3] - boxB[1])

    denom = float(boxAArea + boxBArea - interArea)
    if denom <= 0:
        return 0.0
    return interArea / denom


def calculate_trajectory_similarity(
    traj1: List[Tuple[float, float, float]], traj2: List[Tuple[float, float, float]]
) -> float:
    """
    Compute cosine similarity of average movement vectors between two trajectories.
    Each item is (x, y, timestamp).
    """
    if len(traj1) < 2 or len(traj2) < 2:
        return 0.0

    # Vector 1
    v1_x = traj1[-1][0] - traj1[0][0]
    v1_y = traj1[-1][1] - traj1[0][1]
    mag1 = math.sqrt(v1_x**2 + v1_y**2)

    # Vector 2
    v2_x = traj2[-1][0] - traj2[0][0]
    v2_y = traj2[-1][1] - traj2[0][1]
    mag2 = math.sqrt(v2_x**2 + v2_y**2)

    if mag1 < 10.0 or mag2 < 10.0:
        # Not enough motion to reliably compare trajectories
        return 0.0

    dot = v1_x * v2_x + v1_y * v2_y
    cosine_sim = dot / (mag1 * mag2)
    return max(-1.0, min(1.0, cosine_sim))


def calculate_velocity(
    p1: Tuple[float, float], p2: Tuple[float, float], dt: float
) -> Tuple[float, Tuple[float, float]]:
    """
    Compute speed (magnitude) in px/sec and directional normalized vector.
    """
    if dt <= 0.0001:
        return 0.0, (0.0, 0.0)

    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    dist = math.sqrt(dx**2 + dy**2)
    speed = dist / dt

    if dist > 0.0001:
        direction = (dx / dist, dy / dist)
    else:
        direction = (0.0, 0.0)

    return speed, direction


def vector_angle_degrees(v1: Tuple[float, float], v2: Tuple[float, float]) -> float:
    """Calculate the angle between two 2D unit direction vectors in degrees."""
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    dot = max(-1.0, min(1.0, dot))
    return math.degrees(math.acos(dot))
