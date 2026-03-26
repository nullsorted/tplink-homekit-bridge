"""TP-Link HomeKit Bridge — main entry point.

Discovers TP-Link devices on the local network and exposes them
as HomeKit accessories via a HAP bridge.
"""

import asyncio
import hashlib
import logging
import os
import signal
import stat

from pyhap.accessory import Accessory, Bridge
from pyhap.accessory_driver import AccessoryDriver
from kasa import DeviceType

from config import load_config, is_device_excluded, get_device_name, CONFIG_FILE
from discovery import discover_devices, print_inventory
from accessories.plug import SmartPlug
from accessories.switch import SmartSwitch
from accessories.dimmer import SmartDimmer

logger = logging.getLogger(__name__)

# Map TP-Link device types to our accessory classes
DEVICE_TYPE_MAP = {
    DeviceType.Plug: SmartPlug,
    DeviceType.WallSwitch: SmartSwitch,
    DeviceType.Dimmer: SmartDimmer,
    DeviceType.Bulb: SmartDimmer,
    DeviceType.LightStrip: SmartDimmer,
}

# Device types we intentionally skip
SKIP_TYPES = {DeviceType.Camera, DeviceType.Hub, DeviceType.Sensor, DeviceType.Unknown}

STATE_DIR = os.path.join(os.path.dirname(__file__), "state")


def stable_aid(device_id, attempt=0):
    """Derive a stable HAP Accessory ID from a device identifier (e.g. MAC).

    Returns an int in [2, 65535], avoiding 7 (iOS bug).
    The attempt parameter shifts the hash window for collision retry.
    """
    digest = hashlib.sha256(device_id.encode()).digest()
    offset = (attempt * 2) % (len(digest) - 1)
    raw = int.from_bytes(digest[offset:offset + 2], "big")
    aid = (raw % 65534) + 2
    if aid == 7:
        aid = 8
    return aid


def _get_device_identity(kasa_device):
    """Get a stable identity string for a kasa device (MAC preferred)."""
    mac = getattr(kasa_device, "mac", None)
    if mac:
        return mac.replace(":", "").replace("-", "").lower()
    device_id = getattr(kasa_device, "device_id", None)
    if device_id:
        return device_id
    logger.warning(
        "No MAC or device_id for %s — falling back to IP (AID may change if IP changes).",
        kasa_device.host,
    )
    return kasa_device.host


def add_with_stable_aid(bridge, accessory, device_identity):
    """Add accessory to bridge with collision retry on AID conflicts."""
    for attempt in range(5):
        try:
            bridge.add_accessory(accessory)
            return True
        except ValueError:
            new_aid = stable_aid(device_identity, attempt=attempt + 1)
            logger.warning(
                "AID collision for %s, retrying with AID %d.",
                accessory.display_name, new_aid,
            )
            accessory.aid = new_aid
    logger.error("Failed to add %s after 5 AID collision retries.", accessory.display_name)
    return False


def create_accessory(driver, kasa_device, config, poll_interval):
    """Create the appropriate HomeKit accessory for a kasa device."""
    ip = kasa_device.host
    alias = kasa_device.alias

    # Check exclusion list
    if is_device_excluded(config, ip, alias):
        logger.info("Excluding device per config: %s (%s)", alias or "(unknown)", ip)
        return None

    accessory_cls = DEVICE_TYPE_MAP.get(kasa_device.device_type)

    if accessory_cls is None:
        if kasa_device.device_type not in SKIP_TYPES:
            logger.warning(
                "Unsupported device type %s for %s (%s) — skipping.",
                kasa_device.device_type,
                alias,
                kasa_device.model,
            )
        else:
            logger.info(
                "Skipping %s device: %s (%s)",
                kasa_device.device_type.name,
                alias or "(unknown)",
                kasa_device.model,
            )
        return None

    # Compute stable AID from device MAC
    device_identity = _get_device_identity(kasa_device)
    aid = stable_aid(device_identity)

    # Apply name override from config
    name = get_device_name(config, ip, alias or f"{kasa_device.model}_{ip}")
    logger.info(
        "Creating %s accessory for: %s (%s @ %s, AID=%d)",
        accessory_cls.__name__,
        name,
        kasa_device.model,
        ip,
        aid,
    )
    accessory = accessory_cls(kasa_device, driver, name, aid=aid)
    accessory.POLL_INTERVAL = poll_interval
    return accessory


class RediscoveryAccessory(Accessory):
    """Hidden accessory that periodically scans for new TP-Link devices."""

    def __init__(self, driver, bridge, config, poll_interval, known_devices, *args, **kwargs):
        super().__init__(driver, "Rediscovery Agent", *args, **kwargs)
        self._bridge = bridge
        self._config = config
        self._poll_interval = poll_interval
        self._known_devices = known_devices
        self._interval = config.get("rediscovery", {}).get("interval_seconds", 60)

    async def run(self):
        """Periodically scan for new devices and add them to the bridge."""
        while not self.driver.stop_event.is_set():
            await asyncio.sleep(self._interval)
            try:
                await self._check_for_new_devices()
            except Exception as e:
                logger.error("Rediscovery scan failed: %s", e)

    async def _check_for_new_devices(self):
        logger.info("Running rediscovery scan...")
        devices = await discover_devices(timeout=3)

        new_count = 0
        for ip, device in devices.items():
            device_identity = _get_device_identity(device)
            if device_identity in self._known_devices:
                continue

            accessory = create_accessory(
                self.driver, device, self._config, self._poll_interval
            )
            if accessory is None:
                self._known_devices.add(device_identity)
                continue

            if add_with_stable_aid(self._bridge, accessory, device_identity):
                self._known_devices.add(device_identity)
                new_count += 1
                logger.info(
                    "New device discovered and added: %s (%s @ %s)",
                    device.alias or "(unknown)",
                    device.model,
                    ip,
                )

        if new_count:
            logger.info("Rediscovery added %d new device(s).", new_count)
            self.driver.config_changed()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    # Quiet down noisy libraries
    logging.getLogger("pyhap").setLevel(logging.WARNING)
    logging.getLogger("zeroconf").setLevel(logging.WARNING)

    # Load configuration
    config = load_config()

    bridge_name = config["bridge"]["name"]
    bridge_port = config["bridge"]["port"]
    poll_interval = config["polling"]["interval_seconds"]
    persist_file = os.path.join(STATE_DIR, "hap_persist.json")

    # Discover devices (async) before starting the HAP driver
    devices = asyncio.run(discover_devices())
    print_inventory(devices)

    if not devices:
        logger.warning("No devices found, but starting bridge anyway (devices may appear later).")

    # Set up the HAP driver and bridge
    driver_kwargs = {"port": bridge_port, "persist_file": persist_file}
    pin = config["bridge"].get("pin")
    if pin:
        driver_kwargs["pincode"] = pin.encode()
    driver = AccessoryDriver(**driver_kwargs)
    bridge = Bridge(driver, bridge_name)

    # Create accessories for each discovered device
    known_devices = set()  # Track by device identity (MAC), not IP
    count = 0
    for ip, kasa_device in devices.items():
        device_identity = _get_device_identity(kasa_device)
        known_devices.add(device_identity)
        accessory = create_accessory(driver, kasa_device, config, poll_interval)
        if accessory:
            if add_with_stable_aid(bridge, accessory, device_identity):
                count += 1

    # Set up auto-rediscovery
    if config.get("rediscovery", {}).get("enabled", True):
        rediscovery = RediscoveryAccessory(
            driver, bridge, config, poll_interval, known_devices, aid=65535
        )
        bridge.add_accessory(rediscovery)
        logger.info(
            "Auto-rediscovery enabled (every %ds).",
            config["rediscovery"]["interval_seconds"],
        )

    logger.info("Added %d accessory/accessories to bridge.", count)
    driver.add_accessory(bridge)

    # Lock down sensitive files
    for sensitive_file in [persist_file, CONFIG_FILE]:
        if os.path.exists(sensitive_file):
            os.chmod(sensitive_file, stat.S_IRUSR | stat.S_IWUSR)

    logger.info("Starting %s on port %d...", bridge_name, bridge_port)
    # Print PIN to console only — don't persist in logs (security)
    print(f"Setup code: {driver.state.pincode.decode()}")

    # Handle graceful shutdown
    signal.signal(signal.SIGTERM, lambda *_: driver.stop())

    # driver.start() blocks, handles its own event loop, and catches SIGINT
    try:
        driver.start()
    except KeyboardInterrupt:
        pass

    logger.info("Bridge stopped.")


if __name__ == "__main__":
    main()
