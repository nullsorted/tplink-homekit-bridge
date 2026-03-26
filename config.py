"""Configuration loader for the TP-Link HomeKit Bridge."""

import copy
import logging
import os

import yaml

logger = logging.getLogger(__name__)

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.yaml")

DEFAULTS = {
    "bridge": {
        "name": "TP-Link Bridge",
        "port": 51826,
        "pin": None,
    },
    "devices": {
        "overrides": {},
        "exclude": [],
    },
    "polling": {
        "interval_seconds": 5,
    },
    "rediscovery": {
        "enabled": True,
        "interval_seconds": 60,
    },
}


def load_config(path=None):
    """Load configuration from YAML file, falling back to defaults."""
    path = path or CONFIG_FILE
    config = copy.deepcopy(DEFAULTS)

    if not os.path.exists(path):
        logger.info("No config file found at %s, using defaults.", path)
        return config

    try:
        with open(path) as f:
            user_config = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error("Failed to read config file: %s. Using defaults.", e)
        return config

    # Merge each top-level section
    for section in DEFAULTS:
        if section in user_config and isinstance(user_config[section], dict):
            config[section] = {**DEFAULTS[section], **user_config[section]}
        elif section in user_config:
            config[section] = user_config[section]

    logger.info("Loaded configuration from %s", path)
    return config


def is_device_excluded(config, ip, alias):
    """Check if a device should be excluded based on config."""
    exclude_list = config.get("devices", {}).get("exclude") or []
    for entry in exclude_list:
        if entry == ip or (alias and entry == alias):
            return True
    return False


def get_device_name(config, ip, default_alias):
    """Get the display name for a device, applying config overrides."""
    overrides = config.get("devices", {}).get("overrides") or {}
    if ip in overrides and isinstance(overrides[ip], dict) and "name" in overrides[ip]:
        return overrides[ip]["name"]
    return default_alias
