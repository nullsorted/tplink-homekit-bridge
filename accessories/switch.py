"""HomeKit Switch accessory for TP-Link wall switches."""

import logging
from pyhap.const import CATEGORY_SWITCH

from .base import TPLinkAccessory

logger = logging.getLogger(__name__)


class SmartSwitch(TPLinkAccessory):
    """Exposes a TP-Link wall switch as a HomeKit Switch."""

    category = CATEGORY_SWITCH

    def __init__(self, kasa_device, *args, **kwargs):
        super().__init__(kasa_device, *args, **kwargs)

        serv = self.add_preload_service("Switch")
        self.char_on = serv.configure_char("On", setter_callback=self.set_on)

    def set_on(self, value):
        """Called when Apple Home toggles the switch."""
        if value:
            self.driver.add_job(self._turn_on)
        else:
            self.driver.add_job(self._turn_off)

    async def _turn_on(self):
        if await self._safe_command(self.kasa_device.turn_on()):
            self.char_on.set_value(True, should_notify=True)

    async def _turn_off(self):
        if await self._safe_command(self.kasa_device.turn_off()):
            self.char_on.set_value(False, should_notify=True)

    async def poll_state(self):
        """Poll device state and update HomeKit characteristic."""
        if not await self._safe_update():
            return

        self.char_on.set_value(self.kasa_device.is_on)
