"""
Comprehensive Unit Test Suite for All 9 Safety Threat Detectors & Spatial Geometry
"""

import time
import unittest
import numpy as np

from src.detectors import (
    FallingDetector,
    LoiteringDetector,
    UnauthorizedEntryDetector,
    CrowdFormationDetector,
    PanicMovementDetector,
    AltercationDetector,
    SuspiciousFollowingDetector,
    SnatchingDetector,
    EveTeasingDetector,
)
from src.tracking.spatial import (
    point_in_polygon,
    euclidean_distance,
    calculate_iou,
    calculate_trajectory_similarity,
    calculate_velocity,
    vector_angle_degrees,
)
from src.tracking.tracker import TrackedPerson


class TestSpatialMath(unittest.TestCase):
    def test_point_in_polygon(self):
        poly = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
        self.assertTrue(point_in_polygon((50.0, 50.0), poly))
        self.assertTrue(point_in_polygon((10.0, 10.0), poly))
        self.assertFalse(point_in_polygon((150.0, 50.0), poly))
        self.assertFalse(point_in_polygon((-10.0, -10.0), poly))

    def test_calculate_iou(self):
        box1 = [0.0, 0.0, 100.0, 100.0]
        box2 = [50.0, 50.0, 150.0, 150.0]
        iou = calculate_iou(box1, box2)
        # Intersect: 50x50 = 2500. Box1: 10000, Box2: 10000. Union = 17500. iou = 2500/17500 ~ 0.1428
        self.assertAlmostEqual(iou, 2500.0 / 17500.0, places=3)

    def test_trajectory_similarity(self):
        # Parallel trajectories
        traj1 = [(0, 0, 0), (10, 10, 1), (20, 20, 2), (30, 30, 3)]
        traj2 = [(5, 0, 0), (15, 10, 1), (25, 20, 2), (35, 30, 3)]
        sim = calculate_trajectory_similarity(traj1, traj2)
        self.assertGreater(sim, 0.95)

    def test_vector_angle_degrees(self):
        v1 = (1.0, 0.0)
        v2 = (0.0, 1.0)
        angle = vector_angle_degrees(v1, v2)
        self.assertAlmostEqual(angle, 90.0, places=1)


class TestSafetyDetectors(unittest.TestCase):
    def setUp(self):
        self.dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    def test_condition_1_snatching(self):
        detector = SnatchingDetector({
            "enabled": True,
            "min_approach_speed": 100.0,
            "min_escape_speed": 180.0,
            "max_interaction_dist": 60.0,
            "max_interaction_time": 1.5,
        })
        now = time.time()

        # Phase 1: Attacker approaches victim (within 50px)
        t_attacker = TrackedPerson(
            track_id=1, bbox=[100, 100, 140, 200], confidence=0.9
        )
        t_attacker.speed_px_per_sec = 120.0

        t_victim = TrackedPerson(
            track_id=2, bbox=[120, 100, 160, 200], confidence=0.9
        )
        tracks = {1: t_attacker, 2: t_victim}

        # Step 1: In proximity
        alerts = detector.detect(self.dummy_frame, tracks, 10.0, now)
        self.assertEqual(len(alerts), 0)

        # Phase 2: Attacker sprints away at high escape speed (300px distance, 250px/s)
        t_attacker.bbox = [400, 100, 440, 200]
        t_attacker.speed_px_per_sec = 260.0
        alerts = detector.detect(self.dummy_frame, tracks, 10.0, now + 0.8)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].threat_type, "SNATCHING_ATTEMPT")

    def test_condition_2_eve_teasing(self):
        detector = EveTeasingDetector({
            "enabled": True,
            "proximity_threshold": 60.0,
            "duration_threshold": 2.0,
        })
        now = time.time()

        # Two persons within 40px
        t1 = TrackedPerson(track_id=1, bbox=[100, 100, 130, 180], confidence=0.9)
        t2 = TrackedPerson(track_id=2, bbox=[115, 100, 145, 180], confidence=0.9)
        tracks = {1: t1, 2: t2}

        # First encounter
        alerts = detector.detect(self.dummy_frame, tracks, 10.0, now)
        self.assertEqual(len(alerts), 0)

        # Still hovering after 2.5 seconds
        alerts = detector.detect(self.dummy_frame, tracks, 10.0, now + 2.5)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].threat_type, "EVE_TEASING_PROXIMITY")

    def test_condition_3_suspicious_following(self):
        detector = SuspiciousFollowingDetector({
            "enabled": True,
            "min_tracking_duration": 2.0,
            "trajectory_similarity": 0.75,
            "min_distance": 20.0,
            "max_distance": 150.0,
            "min_distance_traveled": 50.0,
        })
        now = time.time()

        t_lead = TrackedPerson(track_id=1, bbox=[200, 100, 240, 200], confidence=0.9)
        t_foll = TrackedPerson(track_id=2, bbox=[140, 100, 180, 200], confidence=0.9)

        # Build trajectory history showing both moving eastward over 100px
        for i in range(15):
            t_lead.history.append((50 + i * 10, 100, now - (15 - i) * 0.2))
            t_foll.history.append((0 + i * 10, 100, now - (15 - i) * 0.2))

        tracks = {1: t_lead, 2: t_foll}
        detector.detect(self.dummy_frame, tracks, 10.0, now)
        # Advance time by 2.5 seconds
        alerts = detector.detect(self.dummy_frame, tracks, 10.0, now + 2.5)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].threat_type, "SUSPICIOUS_FOLLOWING")

    def test_condition_4_loitering(self):
        detector = LoiteringDetector({
            "enabled": True,
            "dwell_time_threshold": 3.0,
            "zones": [{"name": "Lobby", "polygon": [[0, 0], [200, 0], [200, 200], [0, 200]]}],
        })
        now = time.time()

        t = TrackedPerson(track_id=1, bbox=[50, 50, 90, 150], confidence=0.9)
        tracks = {1: t}

        # Enter zone
        detector.detect(self.dummy_frame, tracks, 10.0, now)
        # Check before threshold
        alerts = detector.detect(self.dummy_frame, tracks, 10.0, now + 1.5)
        self.assertEqual(len(alerts), 0)

        # Dwell beyond 3.0s
        alerts = detector.detect(self.dummy_frame, tracks, 10.0, now + 3.5)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].threat_type, "LOITERING")

    def test_condition_5_panic_movement(self):
        detector = PanicMovementDetector({
            "enabled": True,
            "speed_threshold": 180.0,
            "crowd_scatter_threshold": 2,
        })
        now = time.time()

        t1 = TrackedPerson(track_id=1, bbox=[100, 100, 140, 200], confidence=0.9)
        t1.speed_px_per_sec = 220.0
        t1.history.append((10, 100, now - 0.2))
        t1.history.append((50, 100, now - 0.1))
        t1.history.append((100, 100, now))

        tracks = {1: t1}
        alerts = detector.detect(self.dummy_frame, tracks, 10.0, now)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].threat_type, "PANIC_MOVEMENT")

    def test_condition_6_altercation(self):
        detector = AltercationDetector({
            "enabled": True,
            "overlap_iou_threshold": 0.10,
            "contact_duration": 0.5,
        })
        now = time.time()

        # Overlapping bounding boxes with high kinetic speed
        t1 = TrackedPerson(track_id=1, bbox=[100, 100, 160, 200], confidence=0.9)
        t1.speed_px_per_sec = 100.0
        t2 = TrackedPerson(track_id=2, bbox=[120, 100, 180, 200], confidence=0.9)
        t2.speed_px_per_sec = 110.0

        tracks = {1: t1, 2: t2}
        detector.detect(self.dummy_frame, tracks, 10.0, now)
        alerts = detector.detect(self.dummy_frame, tracks, 10.0, now + 0.8)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].threat_type, "PHYSICAL_ALTERCATION")

    def test_condition_7_falling(self):
        detector = FallingDetector({
            "enabled": True,
            "aspect_ratio_threshold": 1.15,
            "downward_velocity_thresh": 100.0,
        })
        now = time.time()

        # Fallen person: Wide bounding box [x1, y1, x2, y2] width = 160, height = 80 -> aspect_ratio = 2.0
        t = TrackedPerson(track_id=1, bbox=[100, 300, 260, 380], confidence=0.9)
        t.history.append((180, 200, now - 0.5))
        t.history.append((180, 340, now))  # Dropped from y=200 to y=340 (vy = 280 px/s)

        tracks = {1: t}
        alerts = detector.detect(self.dummy_frame, tracks, 10.0, now)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].threat_type, "FALLING")

    def test_condition_8_crowd_formation(self):
        detector = CrowdFormationDetector({
            "enabled": True,
            "cluster_distance_threshold": 60.0,
            "min_cluster_size": 3,
        })
        now = time.time()

        # 3 people tightly grouped around (100, 100)
        t1 = TrackedPerson(track_id=1, bbox=[90, 80, 110, 120], confidence=0.9)
        t2 = TrackedPerson(track_id=2, bbox=[100, 85, 120, 125], confidence=0.9)
        t3 = TrackedPerson(track_id=3, bbox=[105, 90, 125, 130], confidence=0.9)

        tracks = {1: t1, 2: t2, 3: t3}
        alerts = detector.detect(self.dummy_frame, tracks, 10.0, now)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].threat_type, "UNUSUAL_CROWD_FORMATION")

    def test_condition_9_unauthorized_entry(self):
        detector = UnauthorizedEntryDetector({
            "enabled": True,
            "zones": [{"name": "Vault", "polygon": [[50, 50], [150, 50], [150, 150], [50, 150]]}],
        })
        now = time.time()

        # Person inside the vault polygon
        t = TrackedPerson(track_id=1, bbox=[80, 80, 120, 140], confidence=0.9)
        tracks = {1: t}

        alerts = detector.detect(self.dummy_frame, tracks, 10.0, now)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].threat_type, "UNAUTHORIZED_ENTRY")


if __name__ == "__main__":
    unittest.main()
