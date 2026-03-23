# SensorPush Local (Native)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
![Version](https://img.shields.io/badge/version-0.3.8-blue.svg)

A high-precision, **100% local** Home Assistant integration for SensorPush sensors. This integration bypasses the Cloud API and uses Bluetooth Proxies to perform active battery audits, providing millivolt-accurate data even for sensors inside appliances like fridges or freezers.

## ✨ Features

* **Active Battery Audits:** Performs a GATT connection nightly at 3:00am local time to retrieve real-time millivolt data. The initial audit runs in the background on startup so HA is never blocked.
* **Smart Calibration:** Automatically detects hardware generations (HT1 vs HT.w/HTP.xw) to apply correct voltage offsets.
* **Infrastructure Hardened:** Uses a global concurrency lock to prevent Bluetooth proxy contention.
* **Resilient:** If a device is temporarily unreachable, its last-known value is preserved until the next successful audit rather than disappearing from the UI.
* **Native Integration:** Sensors attach directly to your existing SensorPush devices in the Home Assistant UI.
* **Diagnostic Data:** Includes RSSI-at-read, Proxy Source, and Raw Value as entity attributes.

## 🚀 Installation

### Option 1: HACS (Recommended)

1. Open **HACS** in Home Assistant.
2. Click the three dots in the top right and select **Custom repositories**.
3. Paste the URL of this repository and select **Integration** as the category.
4. Click **Install**.
5. Restart Home Assistant.

### Option 2: Manual

1. Download the `sensorpush_local` folder.
2. Copy it into your `/config/custom_components/` directory.
3. Restart Home Assistant.

## ⚙️ Configuration

1. Go to **Settings > Devices & Services**.
2. Click **Add Integration** and search for **SensorPush Local**.
3. Click **Submit** — no further input is required.

## 🛠️ Services

This integration provides a service to trigger an audit of all sensors manually (useful for testing or after a battery swap).

* **Service:** `sensorpush_local.run_audit`

## 📊 Technical Attributes

Every battery entity includes the following attributes for troubleshooting:

* `rssi_at_read`: Signal strength at the moment of the audit.
* `proxy_source`: Friendly name of the Bluetooth adapter or proxy used for the connection, resolved via HA's scanner registry (e.g. "Living Room Hub"). Falls back to the raw source identifier (e.g. `hci0`) if the scanner cannot be found.
* `last_audit`: ISO timestamp of the last successful connection.
* `raw_value`: The raw millivolt count from the sensor firmware.
* `temp_at_read`: Raw temperature value returned alongside the battery read. Units are device-dependent and not calibrated °C.
* `model_type`: Identified hardware generation.

---
