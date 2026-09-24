"""Read-only BEAAM probe: python -m neoom_connect.probe HOST --key-file PATH."""

import argparse
import asyncio
import json
from getpass import getpass
from pathlib import Path

from .diagnostics import diagnostic_report
from .exceptions import NeoomConnectError
from .local import BeaamLocalClient


async def probe(host: str, token: str) -> dict:
    async with BeaamLocalClient(host, token, timeout=10) as client:
        configuration = await client.get_site_configuration()
        flow = await client.get_site_state()
        things = {}
        for thing_id in configuration.things:
            try:
                things[thing_id] = await client.get_thing_states(thing_id)
            except NeoomConnectError:
                things[thing_id] = {}
        return diagnostic_report(configuration, flow, things)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host")
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    token = (
        args.key_file.read_text(encoding="utf-8-sig").strip()
        if args.key_file
        else getpass("BEAAM API key: ")
    )
    try:
        report = asyncio.run(probe(args.host, token))
    except NeoomConnectError as err:
        parser.exit(1, f"BEAAM probe failed: {type(err).__name__}\n")
    text = json.dumps(report, indent=2, ensure_ascii=True)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"Read {len(report['devices'])} devices; diagnostic report written.")
    else:
        print(text)


if __name__ == "__main__":
    main()
