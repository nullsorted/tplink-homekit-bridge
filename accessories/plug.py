"""HomeKit Outlet accessory for TP-Link smart plugs."""

import logging
from pyhap.const import CATEGORY_OUTLET
from kasa import Module

from .base import TPLinkAccessory

logger = logging.getLogger(__name__)


class SmartPlug(TPLinkAccessory):
    """Exposes a TP-Link plug as a HomeKit Outlet."""

    category = CATEGORY_OUTLET

    def __init__(self, kasa_device, *args, **kwargs):
        super().__init__(kasa_device, *args, **kwargs)

        serv = self.add_preload_service("Outlet", chars=["On", "OutletInUse"])
        self.char_on = serv.configure_char("On", setter_callback=self.set_on)
        self.char_in_use = serv.configure_char("OutletInUse")

    def set_on(self, value):
        """Called when Apple Home toggles the outlet."""
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
        """Poll device state and update HomeKit characteristics."""
        if not await self._safe_update():
            return

        self.char_on.set_value(self.kasa_device.is_on)

        # Determine OutletInUse from energy monitoring if available
        energy = self.kasa_device.modules.get(Module.Energy)
        if energy:
            try:
                in_use = energy.current_consumption > 0
            except Exception:
                in_use = self.kasa_device.is_on
        else:
            in_use = self.kasa_device.is_on

        self.char_in_use.set_value(in_use)
