"""
Threaded Camera Capture Module
Provides low-latency frame streaming with support for Raspberry Pi Camera IMX219,
V4L2, GStreamer, USB webcams, and synthetic video inputs.
"""

import threading
import time
from typing import Any, Optional, Tuple
import cv2
import numpy as np
from src.config_loader import CameraConfig


class ThreadedCamera:
    """
    Spawns a dedicated I/O thread to continuously capture frames from the camera,
    preventing hardware buffer build-up and ensuring real-time zero-lag frame access.
    """

    def __init__(self, config: CameraConfig):
        self.config = config
        self.source = config.source
        self.width = config.width
        self.height = config.height
        self.target_fps = config.fps
        self.rotation = config.rotation

        self.cap: Optional[cv2.VideoCapture] = None
        self.picam2 = None
        self.is_picam2 = False

        self.latest_frame: Optional[np.ndarray] = None
        self.frame_lock = threading.Lock()
        self.running = False
        self.grabbed = False
        self.capture_thread: Optional[threading.Thread] = None
        self.actual_fps = 0.0

        self._init_source()

    def _init_source(self) -> None:
        # Check for Picamera2 on Raspberry Pi
        if str(self.source).lower() == "rpicam" or self.config.backend.lower() == "picamera2":
            try:
                from picamera2 import Picamera2

                self.picam2 = Picamera2()
                config = self.picam2.create_video_configuration(
                    main={"size": (self.width, self.height), "format": "RGB888"}
                )
                self.picam2.configure(config)
                self.picam2.start()
                self.is_picam2 = True
                self.grabbed = True
                print("[CAM] Successfully initialized Picamera2 backend for IMX219.")
                return
            except Exception as e:
                print(f"[CAM-WARN] Picamera2 unavailable ({e}). Falling back to OpenCV backend.")

        # Determine camera backend and index
        if isinstance(self.source, str) and self.source.isdigit():
            src_index = int(self.source)
        elif isinstance(self.source, int):
            src_index = self.source
        else:
            src_index = None

        if src_index is not None:
            # First try DirectShow on Windows (fastest & most reliable on Windows)
            import platform
            is_windows = platform.system() == "Windows"

            backends = [cv2.CAP_DSHOW, cv2.CAP_ANY] if is_windows else [cv2.CAP_V4L2, cv2.CAP_ANY]
            candidate_indexes = [src_index]
            # If default index 0, also allow checking index 1 (many laptops have IR camera on 0 and RGB on 1)
            if src_index == 0:
                candidate_indexes.extend([1, 2])

            opened = False
            for idx in candidate_indexes:
                for backend in backends:
                    try:
                        temp_cap = cv2.VideoCapture(idx, backend)
                        if temp_cap and temp_cap.isOpened():
                            ret, test_frame = temp_cap.read()
                            if ret and test_frame is not None and test_frame.size > 0:
                                self.cap = temp_cap
                                self.source = idx
                                opened = True
                                print(f"[CAM] Successfully connected to Camera Index {idx} (Backend: {backend})")
                                break
                            else:
                                temp_cap.release()
                    except Exception:
                        pass
                if opened:
                    break

            if not opened:
                # Final fallback attempt
                self.cap = cv2.VideoCapture(src_index)
        else:
            # Video file path or RTSP URL
            self.cap = cv2.VideoCapture(self.source)

        if self.cap and self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.target_fps)
            self.grabbed, frame = self.cap.read()
            if self.grabbed and frame is not None:
                self.latest_frame = frame
            print(f"[CAM] Camera ready: Source '{self.source}' ({self.width}x{self.height} @ {self.target_fps}fps)")
        else:
            print(f"[CAM-WARN] Failed to open camera source '{self.source}'. Will produce synthetic test frames.")
            self.grabbed = True

    def start(self) -> "ThreadedCamera":
        self.running = True
        self.capture_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.capture_thread.start()
        return self

    def _update_loop(self) -> None:
        last_time = time.time()
        frame_count = 0
        fps_timer = time.time()

        while self.running:
            frame: Optional[np.ndarray] = None

            if self.is_picam2 and self.picam2:
                try:
                    rgb_frame = self.picam2.capture_array()
                    frame = cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2BGR)
                    self.grabbed = True
                except Exception as e:
                    time.sleep(0.05)
                    continue
            elif self.cap and self.cap.isOpened():
                ret, raw_frame = self.cap.read()
                if ret and raw_frame is not None:
                    frame = raw_frame
                    self.grabbed = True
                else:
                    # Auto-reconnect or loop video
                    if isinstance(self.source, str) and not self.source.isdigit():
                        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    time.sleep(0.02)
                    continue
            else:
                # Generate synthetic test frame if no hardware camera is present
                frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                cv2.putText(
                    frame,
                    "CAMERA SIMULATION / NO HARDWARE",
                    (30, self.height // 2),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2,
                )
                time.sleep(1.0 / max(1, self.target_fps))

            if frame is not None:
                # Resize if necessary
                if frame.shape[1] != self.width or frame.shape[0] != self.height:
                    frame = cv2.resize(frame, (self.width, self.height))

                # Rotate if configured
                if self.rotation == 90:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                elif self.rotation == 180:
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                elif self.rotation == 270:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

                with self.frame_lock:
                    self.latest_frame = frame

                frame_count += 1
                now = time.time()
                if now - fps_timer >= 1.0:
                    self.actual_fps = frame_count / (now - fps_timer)
                    frame_count = 0
                    fps_timer = now

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Returns the freshest frame with zero buffering latency."""
        with self.frame_lock:
            if self.latest_frame is None:
                return False, None
            return True, self.latest_frame.copy()

    def stop(self) -> None:
        self.running = False
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=1.0)
        if self.cap:
            self.cap.release()
        if self.picam2:
            try:
                self.picam2.stop()
            except Exception:
                pass
        print("[CAM] Camera capture stopped.")
