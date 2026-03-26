"""Base accessory class for TP-Link devices."""

import asyncio
import logging
from pyhap.accessory import Accessory

logger = logging.getLogger(__name__)


class TPLinkAccessory(Accessory):
    """Base class for all TP-Link HomeKit accessories.

    Handles common patterns: storing the kasa device reference,
    polling state, and error handling for offline devices.
    """

    POLL_INTERVAL = 5  # seconds, overridden by config via bridge.py

    def __init__(self, kasa_device, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kasa_device = kasa_device
        self._reachable = True

    async def run(self):
        """Poll device state at the configured interval."""
        while not self.driver.stop_event.is_set():
            await self.poll_state()
            await asyncio.sleep(self.POLL_INTERVAL)

    async def poll_state(self):
        """Override in subclasses to update HomeKit characteristics."""
        pass

    async def _safe_update(self):
        """Update device state, handling offline devices gracefully."""
        try:
            await self.kasa_device.update()
            if not self._reachable:
                logger.info("%s is back online.", self.kasa_device.alias)
                self._reachable = True
            return True
        except Exception as e:
            if self._reachable:
                logger.warning(
                    "%s is unreachable: %s", self.kasa_device.alias, e
                )
                self._reachable = False
            return False

    async def _safe_command(self, coro):
        """Execute a device command with error handling."""
        try:
            await coro
            return True
        except Exception as e:
            logger.error(
                "Command failed for %s: %s", self.kasa_device.alias, e
            )
            self._reachable = False
            return False

    async def stop(self):
        """Clean up on shutdown."""
        logger.debug("Stopping accessory: %s", self.display_name)
