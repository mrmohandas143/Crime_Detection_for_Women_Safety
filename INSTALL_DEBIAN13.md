# Installation & Setup Guide for Raspberry Pi 5 (Debian 13 Trixie)

This guide walks you through setting up the AI Safety Monitoring System on a **Raspberry Pi 5 (8GB RAM)** running **Debian GNU/Linux 13 (Trixie)** with kernel `6.18+ aarch64`.

---

## 1. Operating System & Firmware Updates

Open a terminal on your Raspberry Pi 5:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git build-essential cmake python3-dev python3-venv \
    python3-pip i2c-tools v4l-utils libgpiod2 python3-lgpio libatlas-base-dev \
    libavcodec-dev libavformat-dev libswscale-dev
```

---

## 2. IMX219 Camera Configuration (Debian 13 Trixie)

> [!IMPORTANT]
> **Debian 13 (Trixie) Command Update**:
> In Debian 13 / Raspberry Pi OS Trixie, the camera stack commands have been renamed from `libcamera-*` to `rpicam-*` (`rpicam-hello`, `rpicam-vid`, `rpicam-still`).

### Step 2.1: Enable the IMX219 Camera Overlay

Edit the boot configuration file:

```bash
sudo nano /boot/firmware/config.txt
```

Ensure the following lines are present in the `[all]` section:

```ini
# Disable auto-detect if using explicit IMX219 camera port
camera_auto_detect=0
dtoverlay=imx219,cam0
# If connected to CAM1 (Port 1), use:
# dtoverlay=imx219,cam1

# Enable I2C for the OLED Display
dtparam=i2c_arm=on
```

Save (`Ctrl+O`, `Enter`) and exit (`Ctrl+X`), then reboot the Pi:

```bash
sudo reboot
```

### Step 2.2: Test the Camera with `rpicam`

After reboot, verify the IMX219 camera is detected:

```bash
# 1. Check if camera is recognized
rpicam-hello --list-cameras

# 2. Open a 5-second test preview
rpicam-hello -t 5000
```

If using a USB webcam instead, check with:

```bash
v4l2-ctl --list-devices
```

---

## 3. Enable I2C for the OLED Display

Verify I2C bus detection:

```bash
sudo i2cdetect -y 1
```

You should see address `0x3c` (or `0x3d`) appearing in the matrix table.

---

## 4. Python Virtual Environment Setup (PEP 668 Compliance)

Debian 13 enforces PEP 668 (`EXTERNALLY-MANAGED`). You must use a Python virtual environment:

```bash
# Navigate to project directory
cd /home/pi/Crime_Detection

# Create virtual environment
python3 -m venv venv --system-site-packages

# Activate environment
source venv/bin/activate

# Upgrade pip & wheel
pip install --upgrade pip setuptools wheel
```

---

## 5. Install Dependencies

Install all project dependencies from `requirements.txt`:

```bash
pip install -r requirements.txt
```

> [!TIP]
> **CPU Inference Optimization on Raspberry Pi 5**:
> The 4× Cortex-A76 cores @ 2.4 GHz in the Pi 5 easily achieve 8–15 FPS on `yolov8n-pose.pt`.
> Pre-download the model weights:
> ```bash
> python3 -c "from ultralytics import YOLO; YOLO('yolov8n-pose.pt')"
> ```

---

## 6. Verifying the Installation

Run the automated test suite to ensure all 9 detector engines and spatial math algorithms are functioning correctly:

```bash
source venv/bin/activate
python -m unittest discover -s tests -p "test_*.py"
```

Expected output:
```
Ran 13 tests in 0.005s
OK
```

Run a hardware dry-run test:

```bash
python main.py --dry-run --mock-hardware --headless
```

---

## 7. Starting the System

### Live Feed with GUI Window (Desktop environment):
```bash
source venv/bin/activate
python main.py
```

### Headless Mode (Background / SSH):
```bash
source venv/bin/activate
python main.py --headless
```

### Specifying a Camera / Video Source:
```bash
# For IMX219 via Picamera2 backend
python main.py --source rpicam

# For USB Webcam on /dev/video0
python main.py --source 0

# For testing with a prerecorded video file
python main.py --source demo_video.mp4
```
