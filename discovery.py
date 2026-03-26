"""TP-Link device discovery module.

Uses python-kasa to discover all TP-Link Kasa/Tapo devices on the local network
and prints a formatted inventory.
"""

import asyncio
import logging
from kasa import Discover

logger = logging.getLogger(__name__)


async def discover_devices(timeout=5):
    """Discover all TP-Link devices on the local network.

    Args:
        timeout: Discovery timeout in seconds.

    Returns:
        Dict mapping IP addresses to device objects.
    """
    logger.info("Discovering TP-Link devices on the local network...")
    devices = await Discover.discover(timeout=timeout)

    if not devices:
        logger.warning("No TP-Link devices found. Ensure devices are on the same LAN.")
        return {}

    # Update each device to populate full state; remove failures
    failed = []
    for ip, device in devices.items():
        try:
            await device.update()
        except Exception as e:
            logger.error("Failed to update device at %s: %s — removing from results.", ip, e)
            failed.append(ip)

    for ip in failed:
        del devices[ip]

    logger.info("Found %d device(s) (%d failed update).", len(devices), len(failed))
    return devices


def print_inventory(devices):
    """Print a formatted table of discovered devices."""
    if not devices:
        print("\nNo devices found.")
        return

    print(f"\n{'='*80}")
    print(f"  TP-Link Device Inventory — {len(devices)} device(s) found")
    print(f"{'='*80}\n")

    header = f"  {'Alias':<25} {'Model':<12} {'Type':<15} {'IP Address':<17} {'State':<8}"
    print(header)
    print(f"  {'-'*25} {'-'*12} {'-'*15} {'-'*17} {'-'*8}")

    for ip, device in sorted(devices.items(), key=lambda item: item[1].alias or ""):
        alias = device.alias or "(unknown)"
        model = device.model or "?"
        device_type = device.device_type.name if device.device_type else "?"
        state = "ON" if device.is_on else "OFF"

        print(f"  {alias:<25} {model:<12} {device_type:<15} {ip:<17} {state:<8}")

        # Show extra info if available
        if hasattr(device, "brightness") and device.is_on:
            print(f"    └─ Brightness: {device.brightness}%")
        if hasattr(device, "has_emeter") and device.has_emeter:
            try:
                emeter = device.emeter_realtime
                if emeter:
                    power = emeter.get("power", emeter.get("power_mw", 0))
                    if isinstance(power, (int, float)) and power > 1000:
                        power = power / 1000  # Convert mW to W if needed
                    print(f"    └─ Power: {power:.1f}W")
            except Exception:
                pass

    print(f"\n{'='*80}\n")


async def main():
    """Run discovery and print inventory."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    devices = await discover_devices()
    print_inventory(devices)
    return devices


if __name__ == "__main__":
    asyncio.run(main())
