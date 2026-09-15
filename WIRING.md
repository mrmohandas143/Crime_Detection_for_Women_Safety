# Hardware Wiring & Pinout Guide - Raspberry Pi 5

This document details the physical pin connections for the **LED Visual Alert**, **Piezo Buzzer Audio Alert**, **Hardware Panic Button**, **4.3" / 0.96" I2C OLED Display**, and **IMX219 Camera Module**.

---

## 1. Raspberry Pi 5 40-Pin Header Reference

```
                             3.3V Power [01] [02] 5V Power
             (I2C1 SDA) GPIO 2 / Pin  3 [03] [04] 5V Power
             (I2C1 SCL) GPIO 3 / Pin  5 [05] [06] Ground
                        GPIO 4 / Pin  7 [07] [08] GPIO 14 (UART TX)
                                Ground [09] [10] GPIO 15 (UART RX)
    [BUZZER]            GPIO 17 / Pin 11 [11] [12] GPIO 18 [ALERT LED]
    [PANIC BTN]         GPIO 27 / Pin 13 [13] [14] Ground
                        GPIO 22 / Pin 15 [15] [16] GPIO 23
                              3.3V Power [17] [18] GPIO 24
                        GPIO 10 / Pin 19 [19] [20] Ground
                        GPIO 9  / Pin 21 [21] [22] GPIO 25
                        GPIO 11 / Pin 23 [23] [24] GPIO 8
                                Ground [25] [26] GPIO 7
                                 ID_SD [27] [28] ID_SC
                        GPIO 5  / Pin 29 [29] [30] Ground
                        GPIO 6  / Pin 31 [31] [32] GPIO 12
                        GPIO 13 / Pin 33 [33] [34] Ground
                        GPIO 19 / Pin 35 [35] [36] GPIO 16
                        GPIO 26 / Pin 37 [37] [38] GPIO 20
                                Ground [39] [40] GPIO 21
```

---

## 2. Component Wiring Table

| Component | Component Pin | Raspberry Pi 5 Pin | Physical Pin # | Notes / Resistor Required |
| :--- | :--- | :--- | :--- | :--- |
| **Alert LED (Red)** | Anode (+) | **GPIO 18** | **Pin 12** | In series with **220Ω - 330Ω resistor** |
| | Cathode (-) | **GND** | **Pin 14** | Connect to ground rail |
| **Piezo Buzzer** | Positive (+) | **GPIO 17** | **Pin 11** | Direct connection (Active Buzzer 3.3V/5V) |
| | Negative (-) | **GND** | **Pin 09** | Connect to ground rail |
| **Panic Button** | Terminal 1 | **GPIO 27** | **Pin 13** | Software pull-up enabled in `gpiozero` |
| | Terminal 2 | **GND** | **Pin 20** | Direct connection |
| **OLED Display** | VCC | **3.3V Power** | **Pin 01** | Power supply (3.3V) |
| | GND | **GND** | **Pin 06** | Ground |
| | SDA | **GPIO 2 (SDA)** | **Pin 03** | I2C Data bus |
| | SCL | **GPIO 3 (SCL)** | **Pin 05** | I2C Clock bus |

---

## 3. Detailed Circuit Descriptions

### A. Visual Alert LED Circuit (GPIO 18)
- Connect a **220Ω or 330Ω current-limiting resistor** to the Long Lead (Anode `+`) of the LED.
- Connect the other side of the resistor to **GPIO 18 (Pin 12)**.
- Connect the Short Lead (Cathode `-` / flat side) of the LED directly to **GND (Pin 14)**.
- *Behavior*: Pulses at 0.15s interval for High alerts and rapid 0.08s strobe for Critical emergencies.

### B. Piezo Buzzer Audio Alert (GPIO 17)
- Connect the **`+` (positive lead)** of an active 3.3V/5V buzzer to **GPIO 17 (Pin 11)**.
- Connect the **`-` (negative lead)** to **GND (Pin 9)**.
- *Behavior*: Emits prioritized audible chirps synchronized with the LED flashes.

### C. Physical Panic Button (GPIO 27)
- Connect one terminal of a momentary tactile push-button switch to **GPIO 27 (Pin 13)**.
- Connect the opposing terminal to **GND (Pin 20)**.
- `gpiozero` enables an internal software pull-up resistor. When the button is pressed, GPIO 27 is pulled to Ground, instantly firing a `CRITICAL` priority alert.

### D. 4.3" / 0.96" OLED Display (I2C Bus 1)
- Connect `VCC` -> **Pin 1 (3.3V)**
- Connect `GND` -> **Pin 6 (GND)**
- Connect `SDA` -> **Pin 3 (GPIO 2 - I2C1 SDA)**
- Connect `SCL` -> **Pin 5 (GPIO 3 - I2C1 SCL)**
- The default I2C address is `0x3C` (or `0x3D`). Verify with `sudo i2cdetect -y 1`.

---

## 4. IMX219 Camera CSI Connection

1. Locate the **CAM/DISP0** or **CAM/DISP1** FPC connector on the Raspberry Pi 5.
2. Gently pull up the locking collar of the connector.
3. Insert the 15-pin to 22-pin adapter ribbon cable with the **copper contacts facing toward the HDMI ports / board center**.
4. Push the locking collar back down until it clicks flush.
5. In `/boot/firmware/config.txt`, specify `dtoverlay=imx219,cam0` (or `cam1`).
