# Changelog

## 0.2.0 (2026-09-24)

- Reconfigure BEAAM address and optional replacement API keys through Home Assistant;
  validate both connections before saving and reject any change of site.
- Keep existing keys when replacement fields are empty; retain entry identity,
  polling options and existing measurement unique IDs.
- Link devices to the site using the current Home Assistant device registry API;
  show device types and distinguish duplicate device names with stable suffixes.
- Translate common technical measurements into English and German.
- Discover individual BEAAM input-power, voltage and current channels from verified
  numeric arrays; keep channel IDs stable on reload and mark absent channels unavailable.
- Add regression checks for six simulated hours of rate-limited connection failure.
- The Python dependency remains `py-neoom-connect==0.1.0`; this release is read-only.

## 0.1.1 (2026-09-24)

- Add diagnostic entities for the active data source and site connection.
- Show cloud fallback as a separate problem entity in hybrid mode.
- Keep the connection status readable during outages; make source and fallback
  unavailable when no valid local or cloud reading remains.
- Include configured polling intervals in redacted diagnostics.
- Test diagnostic states across fallback, cache expiry, authentication errors,
  recovery, partial device outages and entry reloads.
- Keep existing measurement IDs and the `py-neoom-connect==0.1.0` dependency.

## 0.1.0 (2026-09-24)

- Async local BEAAM and cloud clients in one standalone Python package.
- Parse documented cloud time-series objects, UTC timestamps and local metadata.
- Setup for local, cloud and hybrid connections with site selection, credential
  renewal, duplicate-site checks and polling options.
- Local-first polling with cloud fallback, retry throttling and local recovery.
- Discover numeric sensors and device connection/error status from BEAAM metadata.
- Keep missing counters unavailable during cloud fallback; never replace them with zero.
- Preserve unchanged measurements regardless of their last-change timestamp.
- Redacted diagnostics, a read-only device probe and an isolated HA live check.
- Library and actual Home Assistant setup, entity, failure and config-flow tests.
- HACS metadata and reproducible package checks; Python package published as `py-neoom-connect`.
