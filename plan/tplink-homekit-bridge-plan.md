# TP-Link → HomeKit Bridge: Claude Code Implementation Plan

## Goal

Build a Python service that discovers TP-Link Kasa/Tapo devices on the local network and exposes them as HomeKit accessories via the HomeKit Accessory Protocol (HAP). This eliminates the need for the Kasa/Tapo app and makes all TP-Link switches, plugs, and dimmers controllable through Apple Home.

## Network Environment

- **Router**: UniFi Dream Router 7 (UDR7)
- **Target devices**: TP-Link Kasa and/or Tapo smart switches, plugs, and potentially cameras (cameras are stretch goal — see Phase 3)
- **All devices are on the same LAN** — the bridge communicates with TP-Link devices over local API, no cloud dependency

## Architecture

```
┌──────────────┐         Local LAN (python-kasa)        ┌──────────────────┐
│  TP-Link     │◄──────────────────────────────────────► │                  │
│  Switches    │   device discovery, state, commands     │                  │
│  Plugs       │                                         │   Bridge Service │
│  Dimmers     │                                         │   (Python)       │
└──────────────┘                                         │                  │
                                                         │  - Discovery     │
┌──────────────┐         HomeKit (HAP-python)            │  - State Sync    │
│  Apple Home  │◄──────────────────────────────────────► │  - Accessory Map │
│  (iPhone,    │   mDNS advertisement, pair, control     │                  │
│   HomePod,   │                                         │                  │
│   Mac)       │                                         └──────────────────┘
└──────────────┘
```

## Core Libraries

| Library | Purpose | Install |
|---------|---------|---------|
| `python-kasa` | Async library for local communication with TP-Link devices. Handles discovery, state queries, and commands. | `pip install python-kasa` |
| `HAP-python` | Implements HomeKit Accessory Protocol. Registers accessories, handles pairing, advertises via mDNS. | `pip install HAP-python[QRCode]` |
| `asyncio` | Both libraries are async-native. The bridge event loop must coordinate both. | stdlib |
| `pyyaml` or `toml` | Configuration file for overrides (custom names, rooms, excluded devices). | `pip install pyyaml` |

## Phase 1: Discovery & Inventory

**Objective**: Connect to the local network, discover all TP-Link devices, and print an inventory with device type, model, IP, and current state.

### Steps

1. Create project structure:
   ```
   tplink-homekit-bridge/
   ├── bridge.py              # Main entry point
   ├── discovery.py           # TP-Link device discovery
   ├── accessories/
   │   ├── __init__.py
   │   ├── switch.py          # HomeKit switch accessory
   │   ├── plug.py            # HomeKit outlet accessory
   │   ├── dimmer.py          # HomeKit lightbulb accessory (dimmable)
   │   └── base.py            # Shared accessory base class
   ├── config.yaml            # User configuration
   ├── state/
   │   └── hap_persist.json   # HAP-python pairing state (auto-generated)
   ├── requirements.txt
   └── README.md
   ```

2. Write `discovery.py`:
   - Use `kasa.Discover.discover()` to find all devices on the LAN
   - For each device, extract: `alias`, `model`, `device_type`, `host` (IP), `is_on`, `hw_info`
   - Print a formatted table of discovered devices
   - Return a list of device objects for the bridge to consume

3. Test discovery standalone:
   ```bash
   python discovery.py
   ```
   This should print all TP-Link devices. Verify against what the Kasa app shows.

## Phase 2: HomeKit Bridge for Switches & Plugs

**Objective**: Expose discovered TP-Link switches and plugs as HomeKit accessories that can be paired with Apple Home.

### Device → HomeKit Mapping

| TP-Link Type | python-kasa Class | HomeKit Service | Key Characteristics |
|---|---|---|---|
| Smart Switch | `SmartDevice` (switch) | `Switch` | `On` (bool) |
| Smart Plug | `SmartDevice` (plug) | `Outlet` | `On` (bool), `OutletInUse` (bool, based on power draw if available) |
| Dimmer Switch | `SmartDimmer` | `Lightbulb` | `On` (bool), `Brightness` (int 0-100) |
| Smart Bulb | `SmartBulb` | `Lightbulb` | `On`, `Brightness`, optionally `Hue`, `Saturation`, `ColorTemperature` |

### Steps

1. **Create `accessories/base.py`** — a base class that:
   - Accepts a `python-kasa` device object
   - Stores the device reference and a `pyhap.accessory.Accessory` instance
   - Implements a `_poll_state()` coroutine that periodically reads device state via `device.update()` and pushes it to the HAP characteristic
   - Implements `_set_state()` callbacks that HAP-python invokes when Apple Home sends a command, forwarding to the kasa device (e.g., `device.turn_on()`, `device.turn_off()`)

2. **Create `accessories/switch.py`** — maps to HAP `Switch` service:
   - Register `On` characteristic
   - `set_on(value)` → calls `await device.turn_on()` or `await device.turn_off()`
   - Poll loop reads `device.is_on` and updates the characteristic

3. **Create `accessories/plug.py`** — maps to HAP `Outlet` service:
   - Same as switch but adds `OutletInUse` characteristic
   - If device supports energy monitoring (`device.has_emeter`), set `OutletInUse` based on wattage > 0

4. **Create `accessories/dimmer.py`** — maps to HAP `Lightbulb` service:
   - `On` + `Brightness` characteristics
   - `set_brightness(value)` → calls `await device.set_brightness(value)`

5. **Create `bridge.py`** — the main entry point:
   - Run device discovery
   - For each discovered device, instantiate the appropriate accessory class
   - Create a `pyhap.accessory_driver.AccessoryDriver`
   - Create a `pyhap.accessory.Bridge` accessory and add all device accessories to it
   - Start the driver (this handles mDNS advertisement, pairing, and the HAP event loop)
   - Handle graceful shutdown on SIGTERM/SIGINT

6. **Key implementation detail — async coordination**:
   - `python-kasa` is async. `HAP-python` has its own event loop but supports async accessories.
   - Use `HAP-python`'s `AsyncAccessory` subclass and its `run()` coroutine for the polling loop
   - The `AccessoryDriver` can be started with an existing asyncio event loop

7. **Pairing flow**:
   - On first run, HAP-python generates a setup code (like `031-45-154`)
   - Print this to stdout and optionally generate a QR code (via the `[QRCode]` extra)
   - User opens Apple Home → Add Accessory → enters code or scans QR
   - Pairing state persists in `state/hap_persist.json` — subsequent runs reconnect automatically

### Test Checklist

- [ ] Bridge starts and prints setup code
- [ ] Apple Home discovers the bridge via mDNS
- [ ] Pairing completes successfully
- [ ] Each TP-Link switch appears as a separate tile in Apple Home
- [ ] Toggling in Apple Home physically toggles the switch
- [ ] Toggling the physical switch updates state in Apple Home (within polling interval)
- [ ] Bridge survives device temporarily going offline and recovers when it reconnects

## Phase 3: Stretch Goals (Implement Only After Phase 2 Is Solid)

### 3a. Camera Support

TP-Link cameras (Tapo C-series) are significantly harder:
- They use RTSP for video streams — you'd need to expose this as a HomeKit camera accessory
- HomeKit cameras require SRTP (encrypted RTP) streams
- HAP-python does support camera accessories, but the implementation is complex
- May require `ffmpeg` for transcoding

**Recommendation**: Get switches working first. If cameras are desired, consider whether Homebridge's `homebridge-tplink-smarthome` or `scrypted` handles this better than a custom build.

### 3b. Configuration File

Create `config.yaml` for user customization:

```yaml
bridge:
  name: "TP-Link Bridge"
  port: 51826
  pin: "031-45-154"  # Or auto-generate

devices:
  # Override display names in Apple Home
  overrides:
    "192.168.1.50":
      name: "Office Lamp"
      room: "Office"
    "192.168.1.51":
      name: "Porch Light"
      room: "Front Porch"

  # Devices to ignore (by IP or alias)
  exclude:
    - "192.168.1.99"
    - "Guest Room Plug"

polling:
  interval_seconds: 5  # How often to poll TP-Link device state
```

### 3c. Auto-Rediscovery

- Periodically re-run discovery (e.g., every 60 seconds)
- If a new device appears, dynamically add it to the bridge
- If a device disappears, mark it as unreachable in HomeKit (don't remove — it may come back)

### 3d. Systemd Service

Create a systemd unit file so the bridge starts on boot and restarts on failure:

```ini
[Unit]
Description=TP-Link HomeKit Bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=kevin
WorkingDirectory=/home/kevin/tplink-homekit-bridge
ExecStart=/usr/bin/python3 bridge.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Implementation Notes for Claude Code

### Error handling priorities
- TP-Link devices go offline frequently (power loss, network blips). The bridge must not crash when a device is unreachable. Wrap all `python-kasa` calls in try/except, log the error, mark the accessory as unreachable in HAP, and retry on next poll cycle.
- If discovery finds zero devices, log a warning and keep running — devices may appear later.

### State consistency
- The biggest UX issue with bridges is stale state. If someone toggles a switch physically, Apple Home won't know until the next poll. Keep the polling interval short (5 seconds) but make it configurable.
- When a command is sent from HomeKit, update the HAP characteristic immediately (optimistic update), then verify on the next poll cycle.

### Logging
- Use Python's `logging` module with configurable levels
- Default to INFO (device discovery, state changes, commands received)
- DEBUG for protocol-level details (raw kasa responses, HAP events)

### Testing approach
- Start with a single switch. Get the full round-trip working (discover → expose → pair → control → state sync) before adding complexity.
- Use `hap-python`'s mock driver if you need to test without an iOS device, but real-device testing is strongly preferred here.

### Key python-kasa API reference
```python
from kasa import Discover

# Discover all devices
devices = await Discover.discover()

# Each device:
await device.update()        # Refresh state from device
device.alias                 # Display name
device.model                 # e.g., "HS200", "KP115"
device.device_type           # DeviceType enum
device.is_on                 # bool
await device.turn_on()
await device.turn_off()

# Dimmers:
device.brightness            # int 0-100
await device.set_brightness(75)

# Energy monitoring (plugs like KP115):
device.has_emeter            # bool
emeter = await device.get_emeter_realtime()
emeter["power"]              # current wattage
```

### Key HAP-python API reference
```python
from pyhap.accessory import Accessory, Bridge
from pyhap.accessory_driver import AccessoryDriver
from pyhap.const import CATEGORY_BRIDGE
import pyhap.loader as loader

# Create bridge
driver = AccessoryDriver(port=51826)
bridge = Bridge(driver, "TP-Link Bridge")

# Create accessory (simplified)
class SmartSwitch(Accessory):
    category = CATEGORY_SWITCH

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        serv = self.add_preload_service("Switch")
        self.char_on = serv.configure_char(
            "On", setter_callback=self.set_on
        )

    def set_on(self, value):
        # Called when Apple Home toggles the switch
        # Forward to TP-Link device here
        pass

    @Accessory.run_at_interval(5)
    async def run(self):
        # Poll TP-Link device state and update characteristic
        self.char_on.set_value(device.is_on)

bridge.add_accessory(switch_accessory)
driver.add_accessory(bridge)
driver.start()
```

## Where to Run This

**Option A: Directly on a machine on the LAN** (simplest)
- Any Linux box, Mac, or Raspberry Pi on the same network as the TP-Link devices
- Avahi/Bonjour must be running for mDNS (usually default on Linux/macOS)

**Option B: Docker container**
- Must use `--network=host` for mDNS discovery and TP-Link device communication
- Mount a volume for `state/hap_persist.json` so pairing survives container restarts

**Option C: On the UDR7 itself**
- Possible but constrained — UniFi OS has limited package support
- A container approach would be more appropriate here
- Test on a regular machine first, then migrate if desired

## Success Criteria

1. All TP-Link switches and plugs on the network are automatically discovered
2. Each appears as a controllable accessory in Apple Home
3. Commands from Apple Home reliably toggle the physical device
4. Physical device changes are reflected in Apple Home within 5 seconds
5. The bridge runs as a persistent background service and survives reboots
6. Bridge handles device disconnects/reconnects gracefully without crashing
