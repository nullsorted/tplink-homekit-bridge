"""HomeKit Lightbulb accessory for TP-Link dimmers and bulbs."""

import logging
from pyhap.const import CATEGORY_LIGHTBULB
from kasa import Module

from .base import TPLinkAccessory

logger = logging.getLogger(__name__)


class SmartDimmer(TPLinkAccessory):
    """Exposes a TP-Link dimmer or bulb as a HomeKit Lightbulb."""

    category = CATEGORY_LIGHTBULB

    def __init__(self, kasa_device, *args, **kwargs):
        super().__init__(kasa_device, *args, **kwargs)

        serv = self.add_preload_service("Lightbulb", chars=["On", "Brightness"])
        self.char_on = serv.configure_char("On", setter_callback=self.set_on)
        self.char_brightness = serv.configure_char(
            "Brightness", setter_callback=self.set_brightness
        )

    def set_on(self, value):
        """Called when Apple Home toggles the light."""
        if value:
            self.driver.add_job(self._turn_on)
        else:
            self.driver.add_job(self._turn_off)

    def set_brightness(self, value):
        """Called when Apple Home adjusts brightness."""
        self.driver.add_job(self._set_brightness, value)

    async def _turn_on(self):
        if await self._safe_command(self.kasa_device.turn_on()):
            self.char_on.set_value(True, should_notify=True)

    async def _turn_off(self):
        if await self._safe_command(self.kasa_device.turn_off()):
            self.char_on.set_value(False, should_notify=True)

    async def _set_brightness(self, value):
        light = self.kasa_device.modules.get(Module.Light)
        if light:
            if await self._safe_command(light.set_brightness(value)):
                self.char_brightness.set_value(value, should_notify=True)
                # Setting brightness also turns the light on
                if value > 0:
                    self.char_on.set_value(True, should_notify=True)

    async def poll_state(self):
        """Poll device state and update HomeKit characteristics."""
        if not await self._safe_update():
            return

        self.char_on.set_value(self.kasa_device.is_on)

        light = self.kasa_device.modules.get(Module.Light)
        if light and hasattr(light, "brightness"):
            try:
                self.char_brightness.set_value(light.brightness)
            except Exception:
                pass
