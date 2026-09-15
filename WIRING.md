# Hardware Wiring & Pinout Guide - Raspberry Pi 5

This document details the physical pin connections for the **3 Risk-Level LEDs (Low, Medium, High)**, **Piezo Buzzer (Active only on HIGH/CRITICAL)**, **Hardware Panic Button**, **4.3" / 0.96" I2C OLED Display**, and **IMX219 Camera Module**.

---

## 1. Raspberry Pi 5 40-Pin Header Reference

```
                             3.3V Power [01] [02] 5V Power
             (I2C1 SDA) GPIO 2 / Pin  3 [03] [04] 5V Power
             (I2C1 SCL) GPIO 3 / Pin  5 [05] [06] Ground
                        GPIO 4 / Pin  7 [07] [08] GPIO 14 (UART TX)
                                Ground [09] [10] GPIO 15 (UART RX)
    [BUZZER]            GPIO 17 / Pin 11 [11] [12] GPIO 18 [RED LED - HIGH/CRITICAL]
    [PANIC BTN]         GPIO 27 / Pin 13 [13] [14] Ground
                        GPIO 22 / Pin 15 [15] [16] GPIO 23 [YELLOW LED - MEDIUM]
                              3.3V Power [17] [18] GPIO 24 [GREEN LED - LOW/SECURE]
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

## 2. Component Pinout Table

| Component | Color / Risk | Component Pin | Raspberry Pi 5 Pin | Physical Pin # | Resistor / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **LED 1** | 🟢 **GREEN (LOW / Secure)** | Anode (+) | **GPIO 24** | **Pin 18** | **220Ω - 330Ω resistor** in series |
| | | Cathode (-) | **GND** | **Pin 20** | Direct to Ground |
| **LED 2** | 🟡 **YELLOW (MEDIUM Risk)** | Anode (+) | **GPIO 23** | **Pin 16** | **220Ω - 330Ω resistor** in series |
| | | Cathode (-) | **GND** | **Pin 14** | Direct to Ground |
| **LED 3** | 🔴 **RED (HIGH / Critical)** | Anode (+) | **GPIO 18** | **Pin 12** | **220Ω - 330Ω resistor** in series |
| | | Cathode (-) | **GND** | **Pin 14 / Pin 6**| Direct to Ground |
| **Piezo Buzzer** | 🔊 **HIGH / CRITICAL ONLY** | Positive (+) | **GPIO 17** | **Pin 11** | Direct connection (Active 3.3V/5V Buzzer) |
| | *(Silent on Low/Medium)* | Negative (-) | **GND** | **Pin 09** | Direct to Ground |
| **Panic Button** | 🚨 **Emergency Trigger** | Terminal 1 | **GPIO 27** | **Pin 13** | Software pull-up enabled |
| | | Terminal 2 | **GND** | **Pin 20** | Direct to Ground |
| **OLED Display** | 🖥️ **Status / Banner** | VCC | **3.3V Power** | **Pin 01** | Power supply (3.3V) |
| | | GND | **GND** | **Pin 06** | Ground |
| | | SDA | **GPIO 2 (SDA)** | **Pin 03** | I2C Data bus |
| | | SCL | **GPIO 3 (SCL)** | **Pin 05** | I2C Clock bus |

---

## 3. Risk Level Behavior Logic

```
   [NORMAL / SECURE]       -->  🟢 GREEN LED ON (GPIO 24)       | Buzzer SILENT
   [MEDIUM RISK / WARNING] -->  🟡 YELLOW LED PULSING (GPIO 23) | Buzzer SILENT
   [HIGH RISK / ALARM]     -->  🔴 RED LED STROBING (GPIO 18)   | 🔊 BUZZER ACTIVE (GPIO 17)
```

- **LOW Severity** (Normal secure monitoring):
  - **Green LED** is solid **ON**.
  - Yellow & Red LEDs are OFF.
  - Buzzer is **SILENT**.

- **MEDIUM Severity** (Loitering, Suspicious Following warnings):
  - **Yellow LED** pulses at **0.30s cadence**.
  - Green & Red LEDs are OFF.
  - Buzzer is **SILENT**.

- **HIGH / CRITICAL Severity** (Altercations, Snatching, Falling, Panic, Panic Button):
  - **Red LED** rapid strobe (**0.08s - 0.15s**).
  - **Buzzer** emits loud audio alarm chirps/sirens.
  - Green & Yellow LEDs are OFF.

---

## 4. Breadboard Wiring Instructions

1. **Ground Rail**: Connect **Pin 6, 9, 14, or 20 (GND)** to your breadboard's blue/negative ground rail.
2. **Green LED (LOW)**:
   - Long leg (Anode) $\rightarrow$ 220Ω resistor $\rightarrow$ Jumper wire to **Pin 18 (GPIO 24)**.
   - Short leg (Cathode) $\rightarrow$ Ground rail.
3. **Yellow LED (MEDIUM)**:
   - Long leg (Anode) $\rightarrow$ 220Ω resistor $\rightarrow$ Jumper wire to **Pin 16 (GPIO 23)**.
   - Short leg (Cathode) $\rightarrow$ Ground rail.
4. **Red LED (HIGH)**:
   - Long leg (Anode) $\rightarrow$ 220Ω resistor $\rightarrow$ Jumper wire to **Pin 12 (GPIO 18)**.
   - Short leg (Cathode) $\rightarrow$ Ground rail.
5. **Active Buzzer**:
   - `+` (longer pin) $\rightarrow$ Jumper wire to **Pin 11 (GPIO 17)**.
   - `-` (shorter pin) $\rightarrow$ Ground rail.
