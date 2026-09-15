"""
Configuration Loader Module
Parses and validates configuration parameters from YAML.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
try:
    import yaml
except ImportError:
    yaml = None
    import json


@dataclass
class ZoneConfig:
    name: str
    polygon: List[List[int]]


@dataclass
class SystemConfig:
    device_name: str = "RPi5-AI-Guard-01"
    log_level: str = "INFO"
    log_file: str = "logs/safety_monitor.log"
    snapshot_dir: str = "logs/snapshots"
    save_alert_snapshots: bool = True
    mock_hardware: bool = False


@dataclass
class CameraConfig:
    source: Any = 0
    backend: str = "auto"
    width: int = 640
    height: int = 480
    fps: int = 15
    rotation: int = 0


@dataclass
class InferenceConfig:
    model_type: str = "yolov8n-pose.pt"
    confidence_threshold: float = 0.40
    iou_threshold: float = 0.45
    device: str = "cpu"
    num_threads: int = 4
    frame_skip: int = 2
    target_inference_fps: int = 8


@dataclass
class TrackerConfig:
    type: str = "bytetrack"
    max_disappeared: int = 30
    track_history_length: int = 50
    min_hits: int = 3


@dataclass
class GPIOConfig:
    enabled: bool = True
    led_pin: int = 18
    buzzer_pin: int = 17
    panic_button_pin: int = 27
    active_high: bool = True
    alert_duration_sec: float = 2.5
    cooldown_sec: float = 1.0


@dataclass
class OLEDConfig:
    enabled: bool = True
    i2c_port: int = 1
    i2c_address: str = "0x3C"
    width: int = 128
    height: int = 64
    refresh_rate_hz: int = 2
    screen_type: str = "ssd1306"


@dataclass
class HardwareConfig:
    gpio: GPIOConfig = field(default_factory=GPIOConfig)
    oled: OLEDConfig = field(default_factory=OLEDConfig)


@dataclass
class AppConfig:
    system: SystemConfig = field(default_factory=SystemConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    inference: InferenceConfig = field(default_factory=InferenceConfig)
    tracker: TrackerConfig = field(default_factory=TrackerConfig)
    hardware: HardwareConfig = field(default_factory=HardwareConfig)
    detectors: Dict[str, Any] = field(default_factory=dict)


def load_config(config_path: str = "config/config.yaml") -> AppConfig:
    """Load configuration from a YAML file with robust fallback defaults."""
    path = Path(config_path)
    if not path.is_file():
        print(f"[WARN] Config file '{config_path}' not found. Using defaults.")
        return AppConfig()

    data: Dict[str, Any] = {}
    if yaml is not None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[WARN] Failed to parse YAML '{config_path}': {e}. Using defaults.")
    else:
        # Fallback if PyYAML is not installed
        json_path = path.with_suffix(".json")
        if json_path.is_file():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        else:
            print(f"[WARN] PyYAML not installed. To use '{config_path}', install PyYAML: pip install pyyaml. Using defaults.")

    sys_data = data.get("system", {})
    cam_data = data.get("camera", {})
    inf_data = data.get("inference", {})
    trk_data = data.get("tracker", {})
    hw_data = data.get("hardware", {})
    gpio_data = hw_data.get("gpio", {})
    oled_data = hw_data.get("oled", {})
    detectors_data = data.get("detectors", {})

    return AppConfig(
        system=SystemConfig(**sys_data),
        camera=CameraConfig(**cam_data),
        inference=InferenceConfig(**inf_data),
        tracker=TrackerConfig(**trk_data),
        hardware=HardwareConfig(
            gpio=GPIOConfig(**gpio_data),
            oled=OLEDConfig(**oled_data),
        ),
        detectors=detectors_data,
    )
