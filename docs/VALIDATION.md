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

## Version 0.1.1 connection diagnostics

64 automated tests pass, with 82% combined statement/branch coverage. New tests
cover local/cloud/hybrid status entities, full connection loss, cached fallback,
rate-limit expiry, authentication failures, partial device loss and reloads without
duplicate diagnostic entities. Existing measurement identifiers remain unchanged.

An isolated live hybrid test with real local and cloud reads discovered 107
entities (94 sensors, 13 binary sensors). Data source, site connection and cloud
fallback status followed local operation, simulated local failure, cached cloud
readings and local recovery. Unknown/unavailable measurement counts matched the
0.1.0 checks above. The cloud-only check discovered 12 entities with two unknown
measurements, no unavailable entities and no hybrid-only fallback status. Both
tests unloaded successfully. These tests did not change the production install.

Only the custom component changes in version 0.1.1; the published
`py-neoom-connect==0.1.0` library remains suitable. The checks above were isolated;
production upgrade validation is recorded separately below when completed.

## Production upgrade to 0.1.1

GitHub tests, HACS and Hassfest passed. HACS installed `v0.1.1`, HA restarted and
the existing entry loaded successfully. All 104 existing entity IDs were retained;
three diagnostic entities were added. The source was local, site connection on,
and cloud fallback off. Each of the five main energy counters had six recorded
five-minute intervals with no negative changes in the queried window. This is a
short-term observation, not a long-duration reliability result.

## Version 0.2.0 checks

100 tests pass with 84% combined statement/branch coverage. Reconfigure tests cover
all modes, credential retention/replacement, site mismatch, failed validation and
preserved identity/options. Channel tests cover units, malformed/missing arrays,
invalid numeric values, shrinking/growing arrays, reloads and cloud fallback.
The device link uses `via_device_id`, as required by the current HA registry API.

A six-hour outage is simulated by advancing the retry clock in the test process:
energy counters stay unavailable, 300-second cloud retry limits are respected,
and the original counter value returns after local recovery. No production outage
was induced; this is not a six-hour live soak test.

An isolated live hybrid test found 121 entities, including 14 new input-power,
voltage and current channels. All new channels recovered after simulated fallback.
Initial/recovered states: 11 unknown, zero unavailable. Cloud fallback: two unknown,
108 unavailable local-only measurements. Unload succeeded. Because this sample
was taken at night, nonzero daytime PV channel readings remain to be checked.

## Remaining validation

- This is a point-in-time smoke test, not a long-running reliability test.
- Long-term reliability and Energy Dashboard statistics remain to be validated.
- Nonzero daytime channel readings, other array keys and writable controls are
  not validated. Only the verified read-only channel keys are exposed.
- Migration of existing YAML templates awaits their definition; see [MIGRATION.md](MIGRATION.md).

## Official schemas

- https://developer.neoom.com/reference/sitecontroller_getsiteconfiguration
- https://developer.neoom.com/reference/sitecontroller_getsitestate
- https://developer.neoom.com/reference/thingscontroller_getcurrentstates
- https://developer.neoom.com/reference/get_sites-id-energy-flow-latest
