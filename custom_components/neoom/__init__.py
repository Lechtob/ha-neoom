"""Home Assistant integration for neoom CONNECT and local BEAAM APIs."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import PLATFORMS
from .coordinator import NeoomCoordinator
from .device import device_info


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load the site before forwarding its platforms."""
    coordinator = NeoomCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    coordinator.site_device_id = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **device_info(entry.entry_id)
    ).id
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
