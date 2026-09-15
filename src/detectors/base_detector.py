"""
Base Threat Detector Module
Defines the standard data structures and abstract interface for all safety condition detectors.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import numpy as np
from src.tracking.tracker import TrackedPerson


@dataclass
class ThreatAlert:
    """Represents a validated threat event detected in the video stream."""
    threat_type: str        # e.g., 'FALLING', 'UNAUTHORIZED_ENTRY', 'SNATCHING'
    severity: str           # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    confidence: float       # 0.0 to 1.0
    description: str        # Human-readable explanation
    track_ids: List[int]    # Involved person track IDs
    details: Dict[str, Any] # Additional telemetry (coordinates, velocities, zone names)


class BaseDetector(ABC):
    """Abstract base class for all 9 threat detection sub-engines."""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.enabled = config.get("enabled", True)

    @abstractmethod
    def detect(
        self,
        frame: np.ndarray,
        tracks: Dict[int, TrackedPerson],
        fps: float,
        timestamp: float,
    ) -> List[ThreatAlert]:
        """
        Evaluate current frame and active tracks for threat conditions.
        Returns a list of ThreatAlert instances.
        """
        pass
