# SensorPush Local (Native)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
![Version](https://img.shields.io/badge/version-1.0.5-blue.svg)

A high-precision, **100% local** Home Assistant integration for SensorPush sensors. This integration bypasses the Cloud API and uses Bluetooth Proxies to perform active battery audits, providing millivolt-accurate data even for sensors inside appliances like fridges or freezers.

## ✨ Features

* **Active Battery Audits:** Performs a GATT connection once a day (3:00am local time by default, configurable) to retrieve real-time millivolt data. The initial audit runs in the background on startup so HA is never blocked.
* **Smart Calibration:** Automatically detects hardware generations (HT1 vs HT.w/HTP.xw) to apply correct voltage offsets.
* **Infrastructure Hardened:** Uses a global concurrency lock to prevent Bluetooth proxy contention. Failed connections (timeouts or BLE errors) are retried after a 10-second pause, and each retry may be routed through a different proxy.
* **Resilient:** If a device is temporarily unreachable, its last-known value is preserved until the next successful audit rather than disappearing from the UI. Last-known values are also saved to storage, so readings survive a Home Assistant restart.
* **Native Integration:** Sensors attach directly to your existing SensorPush devices in the Home Assistant UI. Sensors added to or removed from the core SensorPush integration get their Battery Voltage entity added or removed automatically, without a reload.
* **Duplicate Clean-up:** On setup, removes the duplicate SensorPush devices left behind by Home Assistant 2026.8's device registry migration, moving their entities back onto the core SensorPush device.
* **Diagnostic Data:** Includes RSSI-at-read, Proxy Source, and Raw Value as entity attributes, plus a downloadable diagnostics report.

## 📋 Requirements

* Home Assistant 2026.10.0 or newer.
* The core [SensorPush](https://www.home-assistant.io/integrations/sensorpush/) Bluetooth integration, set up with your sensors. This integration audits every device owned by the core SensorPush integration and adds its entity to that device.
* A Bluetooth adapter or Bluetooth proxy in range of each sensor that supports active (connectable) connections.

## 🚀 Installation

### Option 1: HACS (Recommended)

[![Open your Home Assistant instance and add a custom repository.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=kyleberry&repository=sensorpush_local&category=integration)

1. Click the button above, or open **HACS** and add this repository manually as a custom repository under the **Integration** category.
2. Click **Install**.
3. Restart Home Assistant.

### Option 2: Manual

1. Download the `custom_components/sensorpush_local` folder from this repository.
2. Copy it into your `/config/custom_components/` directory.
3. Restart Home Assistant.

## ⚙️ Configuration

1. Go to **Settings > Devices & Services**.
2. Click **Add Integration** and search for **SensorPush Local**.
3. Click **Submit** — no further input is required. Only one instance can be added.

### Options

Click **Configure** on the integration to change:

* **Daily audit hour** (0–23, default `3`): the hour of the day, in local time, when the automatic audit runs.
* **Max retry attempts** (0–5, default `2`): how many times a failed GATT connection is retried before the device is skipped until the next audit.

Saving the options reloads the integration.

## 🛠️ Services

This integration provides a service to trigger an audit of all sensors manually (useful for testing or after a battery swap).

* **Service:** `sensorpush_local.run_audit`

If an audit is already in progress, the call is skipped and the existing values are kept.

## 📊 Technical Attributes

Each sensor gets a **Battery Voltage** entity (in volts). Every battery entity includes the following attributes for troubleshooting:

* `rssi_at_read`: Signal strength at the moment of the audit.
* `proxy_source`: Friendly name of the Bluetooth adapter or proxy used for the connection, resolved via HA's scanner registry (e.g. "Living Room Hub"). Falls back to the raw source identifier (e.g. `hci0`) if the scanner cannot be found.
* `last_audit`: ISO timestamp (UTC) of the last successful connection.
* `raw_value`: The raw millivolt count from the sensor firmware, before the HT1 voltage offset is applied.
* `temp_at_read`: Raw temperature value returned alongside the battery read. Units are device-dependent and not calibrated °C.
* `model_type`: Identified hardware generation: `Legacy (HT1)` or `Modern (HT.w/HTP.xw)`.

---
