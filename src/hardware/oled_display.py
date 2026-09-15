"""
OLED Display Controller Module
Renders real-time threat alerts, FPS, track counts, and system status onto I2C OLED (SSD1306/SH1106).
"""

import threading
import time
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
from src.config_loader import OLEDConfig


class OLEDDisplayController:
    """Controls the 4.3" / 0.96" OLED screen via I2C with status screens and alert banners."""

    def __init__(self, config: OLEDConfig, mock_mode: bool = False):
        self.config = config
        self.mock_mode = mock_mode
        self.device = None
        self._active_alert: Optional[str] = None
        self._alert_expiry: float = 0.0
        self._fps: float = 0.0
        self._person_count: int = 0
        self._running = False
        self._render_thread: Optional[threading.Thread] = None

        self._init_display()

        # Load fonts
        try:
            self.font_small = ImageFont.load_default()
        except Exception:
            self.font_small = None

    def _init_display(self) -> None:
        if not self.config.enabled:
            print("[OLED] Display is disabled in config.")
            return

        if self.mock_mode:
            print("[OLED] Mock mode enabled - simulated display active.")
            return

        try:
            from luma.core.interface.serial import i2c
            from luma.oled.device import ssd1306, sh1106

            serial = i2c(port=self.config.i2c_port, address=int(self.config.i2c_address, 16))
            if self.config.screen_type.lower() == "sh1106":
                self.device = sh1106(serial, width=self.config.width, height=self.config.height)
            else:
                self.device = ssd1306(serial, width=self.config.width, height=self.config.height)

            print(f"[OLED] Initialized {self.config.screen_type} on I2C {self.config.i2c_address}")
        except Exception as e:
            print(f"[OLED-WARN] Failed to initialize hardware OLED ({e}). Running in mock mode.")
            self.mock_mode = True

    def start(self) -> None:
        """Start the background display update loop."""
        if not self.config.enabled:
            return
        self._running = True
        self._render_thread = threading.Thread(target=self._update_loop, daemon=True)
        self._render_thread.start()

    def update_metrics(self, fps: float, person_count: int) -> None:
        self._fps = fps
        self._person_count = person_count

    def show_alert(self, threat_name: str, duration_sec: float = 3.0) -> None:
        self._active_alert = threat_name
        self._alert_expiry = time.time() + duration_sec

    def _update_loop(self) -> None:
        interval = 1.0 / max(1, self.config.refresh_rate_hz)
        while self._running:
            self._render_frame()
            time.sleep(interval)

    def _render_frame(self) -> None:
        image = Image.new("1", (self.config.width, self.config.height), 0)
        draw = ImageDraw.Draw(image)

        now = time.time()
        is_alerting = self._active_alert and (now < self._alert_expiry)

        if is_alerting:
            # High-visibility inverted Alert Banner
            draw.rectangle((0, 0, self.config.width - 1, self.config.height - 1), outline=1, fill=1)
            draw.text((8, 6), "!!! THREAT ALERT !!!", fill=0, font=self.font_small)
            alert_text = str(self._active_alert)[:18]
            draw.text((8, 26), alert_text, fill=0, font=self.font_small)
            draw.text((8, 46), f"TIME: {time.strftime('%H:%M:%S')}", fill=0, font=self.font_small)
        else:
            # Standard System Status Screen
            draw.text((2, 2), "AI SAFETY GUARD", fill=1, font=self.font_small)
            draw.line((0, 14, self.config.width, 14), fill=1)
            draw.text((2, 18), f"STATUS: SECURE", fill=1, font=self.font_small)
            draw.text((2, 32), f"PEOPLE: {self._person_count}", fill=1, font=self.font_small)
            draw.text((2, 46), f"FPS: {self._fps:.1f} | CPU", fill=1, font=self.font_small)

        if self.device:
            try:
                self.device.display(image)
            except Exception as e:
                pass

    def stop(self) -> None:
        self._running = False
        if self.device:
            try:
                self.device.clear()
            except Exception:
                pass
