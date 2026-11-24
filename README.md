# SensorPush Local

[![Marketplace: custom repository](https://img.shields.io/badge/Marketplace-Custom-41BDF5.svg)](https://www.home-assistant.io/integrations/marketplace/)
![Version](https://img.shields.io/badge/version-1.0.9-blue.svg)

Battery voltage for your SensorPush sensors in Home Assistant, read straight from each sensor over Bluetooth. No SensorPush cloud account, no gateway, and nothing leaves your network.

Home Assistant's built-in [SensorPush](https://www.home-assistant.io/integrations/sensorpush/) integration already picks up temperature and humidity from the sensors' Bluetooth broadcasts. This integration adds a **Battery Voltage** entity to each of those sensors: once a day it connects to every sensor, through a local Bluetooth adapter or an ESPHome Bluetooth proxy, and reads the battery in millivolts. That's enough warning to swap a battery before a sensor in the freezer goes quiet.

## ✨ Features

* **Daily battery audits:** Connects to each sensor once a day (3:00am local time by default, configurable) and reads its battery voltage. The first audit runs in the background at startup, so it never holds up Home Assistant.
* **Knows your hardware:** Detects the sensor generation (HT1 or HT.w/HTP.xw) and applies the right voltage conversion for it.
* **Gentle on your proxies:** Connects to one sensor at a time, so audits don't fight over a Bluetooth proxy. A failed connection (a timeout or BLE error) is retried after a 10-second pause, and the retry can go through a different proxy.
* **Keeps the last good reading:** A sensor that's out of reach keeps its last value until the next successful audit instead of going blank. Readings are also saved to storage, so they survive a restart.
* **Lives on your existing devices:** The Battery Voltage entity attaches to the SensorPush device the core integration already created, rather than adding a second device. Add or remove a sensor in the core integration and its Battery Voltage entity follows, without a reload.
* **Cleans up after Home Assistant 2026.8:** That release's device registry migration left a duplicate of every SensorPush device. On setup, this integration removes the duplicates and moves their entities back onto the core SensorPush device.
* **Troubleshooting built in:** Each reading records the signal strength, the proxy that took it and the raw value, and the integration supports Home Assistant's diagnostics download.

## 📋 Requirements

* Home Assistant 2026.10.0 or newer.
* The core [SensorPush](https://www.home-assistant.io/integrations/sensorpush/) integration, set up with your sensors. Every sensor it owns gets audited.
* A Bluetooth adapter or Bluetooth proxy in range of each sensor that can make active (connectable) connections. ESPHome Bluetooth proxies work well.

## 🚀 Installation

### Option 1: Marketplace (Home Assistant 2026.11 and newer, recommended)

Since Home Assistant 2026.11, HACS is built into Home Assistant as the **Marketplace**, under **Settings > Marketplace**. SensorPush Local isn't in the Marketplace's catalog, so you add it as a custom repository. That needs a GitHub account connected to the Marketplace; the Marketplace asks you to connect one the first time.

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=kyleberry&repository=sensorpush_local&category=integration)

1. Click the button above. Or go to **Settings > Marketplace**, select **Add from link** in the upper-right corner, enter `kyleberry/sensorpush_local` and pick **Integration** if asked for a type.
2. Open **SensorPush Local** and click **Install**.
3. Set it up as described under **Configuration** below. A first install loads without a restart. After an update, restart Home Assistant; a repair reminds you.

Already installed it with HACS? The upgrade to 2026.11 moves it into the Marketplace for you, and updates keep arriving there. There's nothing to reinstall.

### Option 2: HACS (Home Assistant 2026.10)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=kyleberry&repository=sensorpush_local&category=integration)

1. Click the button above, or open **HACS** and add this repository as a custom repository under the **Integration** category.
2. Click **Download**.
3. Restart Home Assistant.

### Option 3: Manual

1. Download the `custom_components/sensorpush_local` folder from the [latest release](https://github.com/kyleberry/sensorpush_local/releases/latest).
2. Copy it into your `/config/custom_components/` directory.
3. Restart Home Assistant.

Manual installs don't get update notifications.

## ⚙️ Configuration

1. Go to **Settings > Devices & services**.
2. Click **Add integration** and search for **SensorPush Local**.
3. Click **Submit**. There's nothing else to fill in, and only one instance can be added.

### Options

Click **Configure** on the integration to change:

* **Daily audit hour** (0–23, default `3`): the hour of the day, in local time, when the automatic audit runs.
* **Max retry attempts** (0–5, default `2`): how many times a failed connection is retried before the sensor is skipped until the next audit.

Saving the options reloads the integration.

## 🛠️ Actions

`sensorpush_local.run_audit` audits every sensor now instead of waiting for the daily run. It's handy after a battery swap, or to check a new proxy.

If an audit is already running (scheduled, startup or manual), the call is skipped and the current values are kept.

## 📊 Attributes

Each Battery Voltage entity (in volts) carries these attributes for troubleshooting:

* `rssi_at_read`: signal strength when the reading was taken.
* `proxy_source`: the Bluetooth adapter or proxy that took the reading, by its friendly name (e.g. "Living Room Hub"), or its raw identifier (e.g. `hci0`) if Home Assistant doesn't know the name.
* `last_audit`: ISO timestamp (UTC) of the last successful reading.
* `raw_value`: the raw millivolt count from the sensor firmware, before the HT1 voltage offset is applied.
* `temp_at_read`: the raw temperature value returned alongside the battery reading. Its units depend on the device; it isn't calibrated °C.
* `model_type`: the detected hardware generation, `Legacy (HT1)` or `Modern (HT.w/HTP.xw)`.

## 🐛 Issues and contributing

Found a bug or have an idea? Open an issue on [GitHub](https://github.com/kyleberry/sensorpush_local/issues). If you can, attach the diagnostics download (**Settings > Devices & services > SensorPush Local > ⋮ > Download diagnostics**). For development setup, see [CONTRIBUTING.md](CONTRIBUTING.md).

## 📄 License

MIT. See [LICENSE](LICENSE).
