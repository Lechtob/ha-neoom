"""Read-only integration smoke test in an isolated, temporary Home Assistant core."""

import argparse
import asyncio
import json
import logging
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from aiohttp import ClientSession, TCPConnector, ThreadedResolver
from homeassistant import loader
from homeassistant.helpers import frame
from neoom_connect import BeaamLocalClient, NeoomCloudClient
from neoom_connect.exceptions import ApiUnavailableError
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_test_home_assistant


def summarize(hass, entry) -> dict:
    """Report counts and source without names, IDs or credentials."""
    states = hass.states.async_all()
    return {
        "entities": len(states),
        "platforms": dict(Counter(state.domain for state in states)),
        "unknown": sum(state.state == "unknown" for state in states),
        "unavailable": sum(state.state == "unavailable" for state in states),
        "source": entry.runtime_data.data.source,
    }


async def check(
    host: str,
    token: str,
    *,
    mode: str = "local",
    cloud_token: str | None = None,
    site_id: str | None = None,
) -> None:
    with TemporaryDirectory(prefix="neoom-ha-") as config_dir:
        async with (
            ClientSession(connector=TCPConnector(resolver=ThreadedResolver())) as session,
            async_test_home_assistant(config_dir=config_dir) as hass,
        ):
            hass.data.pop(loader.DATA_CUSTOM_COMPONENTS, None)
            frame.async_setup(hass)
            config = None
            if mode != "cloud":
                config = await BeaamLocalClient(
                    host, token, session=session
                ).get_site_configuration()
                if site_id and site_id != config.site_id:
                    raise RuntimeError("Local and requested site do not match")
                site_id = config.site_id
            if mode != "local":
                if not cloud_token or not site_id:
                    raise RuntimeError("Cloud key and site ID are required")
                sites = await NeoomCloudClient(cloud_token, session=session).get_sites()
                if site_id not in {site.id for site in sites}:
                    raise RuntimeError("Requested site not accessible with this cloud key")
            entry = MockConfigEntry(
                domain="neoom",
                title="neoom live test",
                data={
                    "host": host,
                    "local_token": token,
                    "mode": mode,
                    "site_id": site_id,
                    "cloud_token": cloud_token,
                },
            )
            entry.add_to_hass(hass)
            try:
                with patch(
                    "custom_components.neoom.coordinator.async_get_clientsession",
                    return_value=session,
                ):
                    if not await hass.config_entries.async_setup(entry.entry_id):
                        raise RuntimeError("Home Assistant setup failed")
                    await hass.async_block_till_done()
                    await entry.runtime_data.async_refresh()
                    report = {"mode": mode, "initial": summarize(hass, entry)}
                    if config:
                        report["devices"] = len(config.things)
                    if mode == "hybrid":
                        coordinator = entry.runtime_data
                        with patch.object(
                            coordinator.local,
                            "get_site_state",
                            side_effect=ApiUnavailableError("Simulated local outage"),
                        ):
                            await coordinator.async_refresh()
                            if (
                                not coordinator.last_update_success
                                or coordinator.data.source != "cloud"
                            ):
                                raise RuntimeError("Cloud fallback failed")
                            report["fallback"] = summarize(hass, entry)
                            await coordinator.async_refresh()
                            report["cached_fallback"] = summarize(hass, entry)
                        await coordinator.async_refresh()
                        if (
                            not coordinator.last_update_success
                            or coordinator.data.source != "local"
                        ):
                            raise RuntimeError("Local recovery failed")
                        report["recovery"] = summarize(hass, entry)
                    report["unload_ok"] = await hass.config_entries.async_unload(entry.entry_id)
                    print(
                        json.dumps(
                            report,
                            indent=2,
                        )
                    )
            finally:
                await hass.async_stop(force=True)
                await hass.async_block_till_done()
                frame.async_setup(None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host")
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--mode", choices=["local", "cloud", "hybrid"], default="local")
    parser.add_argument("--cloud-key-file", type=Path)
    parser.add_argument("--site-id-file", type=Path)
    args = parser.parse_args()
    if args.mode != "cloud" and args.key_file is None:
        parser.error("--key-file is required for local/hybrid tests")
    if args.mode != "local" and (args.cloud_key_file is None or args.site_id_file is None):
        parser.error("--cloud-key-file and --site-id-file are required for cloud/hybrid tests")
    logging.basicConfig(level=logging.CRITICAL)
    try:
        asyncio.run(
            check(
                args.host,
                args.key_file.read_text(encoding="utf-8-sig").strip() if args.key_file else "",
                mode=args.mode,
                cloud_token=args.cloud_key_file.read_text(encoding="utf-8-sig").strip()
                if args.cloud_key_file
                else None,
                site_id=args.site_id_file.read_text(encoding="utf-8-sig").strip()
                if args.site_id_file
                else None,
            )
        )
    except Exception as err:
        # Never let an HTTP traceback expose request URLs or credential context.
        print(json.dumps({"result": "failed", "error_type": type(err).__name__}))
        raise SystemExit(1) from None
