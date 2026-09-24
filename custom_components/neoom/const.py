"""Constants for the neoom integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "neoom"

CONF_MODE = "mode"
CONF_HOST = "host"
CONF_LOCAL_TOKEN = "local_token"
CONF_CLOUD_TOKEN = "cloud_token"
CONF_SITE_ID = "site_id"

MODE_LOCAL = "local"
MODE_CLOUD = "cloud"
MODE_HYBRID = "hybrid"

DEFAULT_LOCAL_SCAN_INTERVAL = timedelta(seconds=20)
DEFAULT_CLOUD_SCAN_INTERVAL = timedelta(minutes=2)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
