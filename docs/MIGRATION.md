# Existing neoom energy counters

Do not add a second grid, solar or battery source for measurements already in
the Energy Dashboard. Existing template entities can keep their entity IDs,
unique IDs, units, state classes, rounding and recorded statistics while their
input is changed to the new integration. This requires the actual old template
configuration, a backup, consumer checks and a validated template reload.

## Verified mapping

| Existing entity | New integration source |
| --- | --- |
| `sensor.neoom_energie_importiert` | `sensor.neoom_energy_management_netzbezug` |
| `sensor.neoom_energie_exportiert` | `sensor.neoom_energy_management_netzeinspeisung` |
| `sensor.neoom_energie_produktion` | `sensor.neoom_energy_management_erzeugte_energie` |
| `sensor.neoom_energie_geladen` | `sensor.neoom_energy_management_geladene_energie` |
| `sensor.neoom_energie_entladen` | `sensor.neoom_energy_management_entladene_energie` |

These pairs matched during the live comparison, allowing for rounding and
different polling times. All use Wh. Preserve the existing rounding expression
when replacing its input; do not manufacture a zero when a source is missing.
Use an availability check so cloud fallback cannot create a counter reset.

## Safe sequence

1. Obtain the existing YAML definition and its include location; remove secrets
   from any copy shared for review. Do not remove the running REST source yet.
2. Search every consumer of the old raw source and all template entities.
3. Back up the relevant configuration. Replace only the five templates' input
   expressions and availability guards, retaining identifiers and energy metadata.
4. Validate HA configuration, reload templates and compare the five pairs again.
5. Verify existing Energy Dashboard sources, forecasts, prices and nested device
   consumption settings are unchanged. Check statistics for unexpected resets.
6. Retire the old REST source only when no consumers remain. Otherwise retain it
   until the remaining consumers have been migrated deliberately.

Rollback: restore the previous template definitions and reload templates. Do not
rename entities or delete recorder statistics as part of this migration.

## Current status

The existing YAML has not yet been provided, and the available HA tools cannot
edit those YAML-defined entities. No template source has been changed. The Energy
Dashboard still uses the original five counters; the new state-of-charge sensor
is the only added source. No history migration or duplicate-source setup occurred.
