# SensorPush Local (Native)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
![Version](https://img.shields.io/badge/version-1.2.0-blue.svg)

A high-precision, **100% local** Home Assistant integration for SensorPush sensors. This integration bypasses the Cloud API and uses Bluetooth Proxies to perform active battery audits, providing millivolt-accurate data even for sensors inside appliances like fridges or freezers.

## ✨ Features

* **Active Battery Audits:** Performs a daily GATT connection to retrieve real-time millivolt data.
* **Smart Calibration:** Automatically detects hardware generations (HT1 vs HT.w/HTP.xw) to apply correct voltage offsets.
* **Infrastructure Hardened:** Uses a global concurrency lock to prevent Bluetooth proxy contention.
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
3. Follow the UI prompts to complete the setup.

## 🛠️ Services

This integration provides a service to trigger an audit of all sensors manually (useful for testing or after a battery swap).

* **Service:** `sensorpush_local.run_audit`

## 📊 Technical Attributes

Every battery entity includes the following attributes for troubleshooting:

* `rssi_at_read`: Signal strength at the moment of the audit.
* `proxy_source`: The MAC of the Bluetooth Proxy/Adapter used.
* `last_audit`: ISO timestamp of the last successful connection.
* `raw_value`: The raw millivolt count from the sensor firmware.
* `model_type`: Identified hardware generation.

---
