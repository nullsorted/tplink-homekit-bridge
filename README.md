# TP-Link HomeKit Bridge

A Python service that discovers TP-Link Kasa and Tapo smart devices on your local network and exposes them as HomeKit accessories. Control your TP-Link switches, plugs, and dimmers through Apple Home — no cloud dependency, no Kasa app required.

## Supported Devices

| TP-Link Device | HomeKit Accessory | Features |
|---|---|---|
| Smart Plug (HS100, HS103, EP10, etc.) | Outlet | On/Off, OutletInUse (with energy monitoring) |
| Wall Switch (HS200, etc.) | Switch | On/Off |
| Dimmer (HS220, etc.) | Lightbulb | On/Off, Brightness |
| Smart Bulb (KL series, etc.) | Lightbulb | On/Off, Brightness |
| Light Strip | Lightbulb | On/Off, Brightness |

Cameras, hubs, and sensors are detected but not bridged.

## Requirements

- Python 3.9+
- A machine on the same LAN as your TP-Link devices (Linux, macOS, or Raspberry Pi)
- Avahi/Bonjour for mDNS (included by default on macOS; install `avahi-daemon` on Linux)
- An Apple Home hub (HomePod, Apple TV, or iPad) for remote access

## Installation

```bash
git clone <repo-url> homekit-bridge
cd homekit-bridge

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Verify Discovery

Before starting the bridge, confirm your devices are visible:

```bash
python3 discovery.py
```

This prints a table of all TP-Link devices found on your network with their alias, model, IP, and current state.

## Usage

```bash
source venv/bin/activate
python3 bridge.py
```

On first run, the bridge prints a **setup code** (e.g. `617-94-973`) and a QR code to the console. To pair:

1. Open **Apple Home** on your iPhone or iPad
2. Tap **+** > **Add Accessory**
3. Enter the setup code or scan the QR code
4. All discovered devices appear as separate accessories in Apple Home

Pairing state is saved to `state/hap_persist.json`. Subsequent restarts reconnect automatically without re-pairing.

## Configuration

Edit `config.yaml` to customize the bridge:

```yaml
bridge:
  name: "TP-Link Bridge"
  port: 51826
  # pin: "031-45-154"  # Set a fixed pairing code

devices:
  # Override display names by IP address
  overrides:
    "192.168.0.31":
      name: "Office Lamp"
    "192.168.0.76":
      name: "Living Room Lamp"

  # Exclude devices by IP or alias
  exclude:
    - "192.168.0.99"
    - "Guest Room Plug"

polling:
  interval_seconds: 5  # How often to sync state from devices

rediscovery:
  enabled: true
  interval_seconds: 60  # How often to scan for new devices
```

New devices added to your network are automatically detected and added to the bridge within the rediscovery interval. There is no need to restart.

## Running as a System Service (Linux)

A systemd unit file is included. Adjust the `User` and paths if your setup differs:

```bash
# Edit paths in the service file if needed
sudo cp tplink-homekit-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tplink-homekit-bridge
sudo systemctl start tplink-homekit-bridge
```

Check status and logs:

```bash
sudo systemctl status tplink-homekit-bridge
journalctl -u tplink-homekit-bridge -f
```

The service restarts automatically on failure after a 10-second delay.

## Project Structure

```
homekit-bridge/
├── bridge.py              # Main entry point — discovery, bridge setup, rediscovery
├── discovery.py           # TP-Link device discovery via python-kasa
├── config.py              # Configuration loader
├── config.yaml            # User configuration
├── accessories/
│   ├── base.py            # TPLinkAccessory base class (polling, error handling)
│   ├── plug.py            # HomeKit Outlet (smart plugs)
│   ├── switch.py          # HomeKit Switch (wall switches)
│   └── dimmer.py          # HomeKit Lightbulb (dimmers, bulbs)
├── state/
│   └── hap_persist.json   # HomeKit pairing state (auto-generated)
├── requirements.txt
└── tplink-homekit-bridge.service  # systemd unit file
```

## How It Works

1. **Discovery** — Uses [python-kasa](https://github.com/python-kasa/python-kasa) to broadcast on the local network and find all TP-Link devices
2. **Accessory Mapping** — Each device is mapped to the appropriate HomeKit service type (Outlet, Switch, or Lightbulb)
3. **Stable Identity** — Each device gets a deterministic HomeKit Accessory ID derived from its MAC address, so devices keep their names and room assignments across restarts
4. **HAP Bridge** — [HAP-python](https://github.com/ikalchev/HAP-python) runs a HomeKit Accessory Protocol bridge, handling mDNS advertisement, pairing, and encrypted communication with Apple Home
5. **State Polling** — Each accessory polls its TP-Link device at the configured interval and pushes state changes to HomeKit
6. **Rediscovery** — A background task periodically scans for new devices and adds them to the bridge without requiring a restart

## Troubleshooting

**Bridge not discoverable in Apple Home**
- Ensure the bridge machine and your iPhone/Apple TV are on the same network and subnet
- On Linux, verify Avahi is running: `systemctl status avahi-daemon`
- Check that port 51826 is not blocked by a firewall

**Devices show as "No Response" in Apple Home**
- The TP-Link device may be offline or unreachable. Check the bridge logs for "unreachable" warnings
- Devices automatically recover when they come back online (within the polling interval)

**Devices shuffled after restart**
- This was fixed by stable AID assignment. If you're on an older version, update `bridge.py` and delete `state/hap_persist.json` to re-pair with stable IDs

**"Externally managed environment" error when installing**
- Use a virtual environment (see Installation above). Do not use `--break-system-packages`

## Moving to a New Machine

1. Copy the entire `homekit-bridge/` directory including `state/hap_persist.json`
2. Install dependencies in a new venv on the target machine
3. Start the bridge — it reconnects to Apple Home using the saved pairing state

If you don't copy `state/hap_persist.json`, you'll need to remove the bridge from Apple Home and re-pair.
