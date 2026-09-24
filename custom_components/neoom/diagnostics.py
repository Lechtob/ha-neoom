"""Download diagnostics without credentials or site/device identity."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from neoom_connect.diagnostics import diagnostic_report


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry):
    coordinator = entry.runtime_data
    return {
        "mode": coordinator.mode,
        "source": coordinator.data.source,
        "last_update_success": coordinator.last_update_success,
        "polling_intervals": {
            "local_seconds": coordinator.local_interval,
            "cloud_seconds": coordinator.cloud_interval,
        },
        **diagnostic_report(
            coordinator.configuration, coordinator.data.flow, coordinator.data.things
        ),
    }
