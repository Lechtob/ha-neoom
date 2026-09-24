# Validation status (2026-09-24)

## Local BEAAM

Read-only requests to site configuration, site state and each device's state
endpoint succeeded against the user's BEAAM. Eight devices were discovered:
three inverters, two PV components, one battery, one electricity meter and one
AC charging point.

An isolated Home Assistant 2026.9.3 core loaded the integration with real local
HTTP requests: 93 numeric sensors and 11 binary sensors, followed by another
refresh and successful unload. Eleven measurements were unknown, zero entities
were unavailable. This did not install into or modify the user's production HA.

Observed API behavior used in the implementation:

- Aggregated energy is in Wh; power is in W; battery state of charge is in percent.
- Storage discharge was positive in the site energy flow. Storage discharge
  plus grid import matched calculated consumption in the validation sample.
- Device-level power signs can differ from aggregated energy-flow signs.
  Raw device signs are preserved; no global sign reversal is applied.
- Direct consumption may be null while calculated consumption is available.
- Timestamps can stay unchanged for stable measurements and cumulative counters.
  Availability follows successful polling, presence and device connection status,
  not age alone. A negative timestamp is treated as uninitialized.
- Some metadata describes writable fields. All HA entities remain read-only.

## Cloud and hybrid

The supplied cloud key successfully retrieved the accessible sites. The supplied
site ID matched both that list and the local BEAAM configuration. No identifiers
or credentials were printed or added to the repository.

An isolated HA 2026.9.3 core loaded cloud-only mode using real HTTPS requests:
10 sensors, two unknown readings, zero unavailable entities and successful unload.

The hybrid check used real local and cloud requests. Only the local client's
state-read method inside the test process was made to raise a connection error;
the BEAAM, network and production HA were not interrupted.

| Phase | Source | Entities | Unknown | Unavailable |
| --- | --- | --- | --- | --- |
| Normal operation | Local | 104 | 11 | 0 |
| Simulated local outage | Cloud | 104 | 2 | 94 |
| Immediate repeated refresh | Cached cloud | 104 | 2 | 94 |
| Local recovery | Local | 104 | 11 | 0 |

The 94 unavailable entities during fallback are local-only device measurements,
status entities and energy counters that are absent from the cloud response.
They recovered when local reading resumed. Unload succeeded in both modes.

## Automated checks

Automated checks at this milestone: 54 tests passed, including actual HA
config flows, site selection, duplicate detection, credential renewal, polling
options, setup/unload, entity registry behavior, hybrid startup/recovery,
rate-limit backoff, unavailable counters and privacy checks. Ruff and bytecode
compilation passed. Source distribution, wheel and component ZIP were built;
archive inspection confirmed no local key or diagnostic report was included.
Overall statement/branch coverage reported by pytest-cov was 81%; the probe CLI
was exercised manually against the real BEAAM instead of in the unit suite.

## Published package and production installation

`py-neoom-connect==0.1.0` was published through GitHub Trusted Publishing and
installed directly from PyPI into a fresh virtual environment. Both public
client classes imported successfully in isolated Python mode. GitHub tests,
Hassfest and HACS validation passed. The integration release is `v0.1.0`.

HACS installed that release into Home Assistant 2026.9.3. Configuration validation
passed before the restart. After restart, the official config flow created a
hybrid entry, which reached the `loaded` state using the real local BEAAM and
cloud credentials. Nine device-registry entries represent the site and eight
devices; 93 numeric sensors and 11 binary sensors were registered. Eleven
measurements were unknown, zero entities were unavailable, and the active source
was local. A subsequent automatic poll updated consumption, grid and storage power.

Energy counters expose Wh and `total_increasing` metadata where appropriate.
The current log window contained the expected custom-integration loader warning,
but no neoom integration error. Existing template sensors and the Energy Dashboard
were not changed. Production cloud fallback was not forced; it was tested in the
isolated core as described above.

## Remaining validation

- This is a point-in-time smoke test, not a long-running reliability test.
- Long-term reliability and Energy Dashboard statistics remain to be validated.
- Numeric array channels (for example individual PV strings) and writable
  controls are not exposed yet.

## Official schemas

- https://developer.neoom.com/reference/sitecontroller_getsiteconfiguration
- https://developer.neoom.com/reference/sitecontroller_getsitestate
- https://developer.neoom.com/reference/thingscontroller_getcurrentstates
- https://developer.neoom.com/reference/get_sites-id-energy-flow-latest
