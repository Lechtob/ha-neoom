# neoom / BEAAM Home Assistant Integration - Konzept

Stand: 2026-06-19

## Ziel

Wir wollen eine Home-Assistant-Integration fuer neoom Energiemanagement, Speicher und angeschlossene Energiegeraete bauen. Die Integration soll beide von neoom dokumentierten Schnittstellen abbilden:

- Cloud/Public API ueber `https://api.ntuity.io/v1`
- Lokale BEAAM API ueber `http://<beaam_ip>/api/v1/...`

Die Integration soll im Alltag bevorzugt lokal arbeiten, weil das schneller, robuster und unabhaengiger von Cloud-Verfuegbarkeit ist. Die Cloud API bleibt wichtig fuer Standortauswahl, Remote-Zugriff und Setups ohne lokalen Zugriff.

## Quellenlage aus der neoom-Dokumentation

Die neoom CONNECT-Dokumentation beschreibt als zentrale Modellbegriffe:

- `Site`: oberste logische Gruppierung, typischerweise ein Haushalt oder Standort.
- `Thing`: physisches oder logisches Geraet, z.B. Batterie, Wechselrichter, Zaehler, Ladepunkt oder Waermepumpe.
- `Data Point`: einzelner Messwert, Zustand oder steuerbarer Wert mit `key`, `dataType` und `unitOfMeasure`.
- `Energy Flow`: abgeleitete Standortansicht fuer PV, Netz, Speicher, Verbrauch, Ladepunkte, Heizung und Autarkie.

Wichtige Cloud-Endpunkte:

- `GET /sites/`: erreichbare Sites
- `GET /sites/{id}`: Site-Details
- `GET /sites/{id}/energy-flow/latest`: aktueller Energiefluss

Wichtige lokale BEAAM-Endpunkte:

- `GET /api/v1/site/configuration`: Site-Konfiguration mit Things und DataPoints
- `GET /api/v1/site/state`: aggregierter Site-/Energy-Flow-State
- `GET /api/v1/things/{thingId}/states`: States eines Things
- `GET /api/v1/things/{thingId}/settings`: Settings eines Things
- `POST /api/v1/things/{thingId}/commands`: steuerbare Commands, z.B. `TARGET_POWER`
- `POST /api/v1/things/{thingId}/states`: State-Ingest fuer Generic Devices
- `GET /api/v1/externalPlantControls`: External Plant Controls
- `GET /api/v1/externalPlantControls/{epcId}/states`: EPC-States
- `POST /api/v1/externalPlantControls/{epcId}/commands`: EPC-Commands

Authentifizierung:

- Cloud: Bearer Token
- Lokal: BEAAM API Key, laut Doku als Bearer oder Basic verwendbar; Token-Format `sk_beaam_****`

## Paketentscheidung

Empfehlung: ein gemeinsames PyPI-Paket fuer die Python-Client-Library, aber mit klar getrennten Client-Klassen.

Vorgeschlagener Paketname:

- `neoom-connect` oder `pyneoom-connect`

Nicht empfohlen:

- Zwei getrennte Pakete wie `neoom-cloud` und `neoom-beaam-local`

Begruendung:

- Beide APIs teilen dasselbe Domaenenmodell: Site, Things, DataPoints, EnergyFlow, States, Commands.
- Home Assistant braucht in einer Integration beide Modi. Ein gemeinsames Paket verhindert doppelte Datenmodelle, doppelte Exceptions und abweichendes Verhalten.
- Die Schnittstellen unterscheiden sich vor allem in Transport, Auth und verfuegbaren Endpunkten. Das laesst sich sauber ueber getrennte Clients im selben Paket modellieren.
- Nutzer sollen spaeter nicht zwei Python-Abhaengigkeiten installieren muessen.

Sinnvolle interne Trennung:

```text
neoom_connect/
  __init__.py
  cloud.py          # NeoomCloudClient
  local.py          # BeaamLocalClient
  models.py         # Site, Thing, DataPoint, State, EnergyFlow
  auth.py
  exceptions.py
  discovery.py      # optional: lokale IP/BEAAM-Erkennung
  units.py          # HA-nahe Unit Normalisierung
```

Optional koennen Extras angeboten werden:

```text
neoom-connect[ha]
neoom-connect[dev]
```

Fuer Home Assistant reicht meist ein schlankes Runtime-Paket mit `aiohttp`, `pydantic` oder `dataclasses`, `typing-extensions` und Tests ohne schwere Abhaengigkeiten.

## Python-Client-Design

Die Library sollte voll async sein, weil Home Assistant async-first ist.

Kernklassen:

```python
class NeoomCloudClient:
    async def get_sites(self) -> list[Site]: ...
    async def get_site(self, site_id: str) -> Site: ...
    async def get_latest_energy_flow(self, site_id: str) -> EnergyFlow: ...

class BeaamLocalClient:
    async def get_site_configuration(self) -> SiteConfiguration: ...
    async def get_site_state(self, keys: list[str] | None = None) -> SiteState: ...
    async def get_thing_states(self, thing_id: str, keys: list[str] | None = None) -> ThingState: ...
    async def get_thing_settings(self, thing_id: str) -> ThingSettings: ...
    async def call_thing_commands(self, thing_id: str, commands: list[Command]) -> list[CommandResult]: ...
    async def update_thing_states(self, thing_id: str, states: list[StateWrite]) -> None: ...
```

Gemeinsame Designregeln:

- Eigene Exceptions: `AuthenticationError`, `NotFoundError`, `ApiUnavailableError`, `CommandRejectedError`, `RateLimitError`.
- Keine Home-Assistant-Typen in der Library.
- Rohdaten optional erreichbar machen, aber stabile Python-Modelle als primaere API anbieten.
- Zeitstempel aus `ts` in UTC-`datetime` umwandeln, Rohwert behalten.
- Datenpunkte ueber `key`, `dataPointId`, `thingId` und `thing.type` eindeutig adressieren.
- Einheiten normalisieren, aber nicht heimlich Vorzeichen drehen.

## Home-Assistant-Integration

Vorgeschlagener Integration-Domainname:

```text
neoom
```

Config-Flow:

1. Modusauswahl:
   - Lokal / BEAAM
   - Cloud / ntuity
   - Hybrid
2. Lokal:
   - Host/IP
   - BEAAM API Key
   - Verbindungstest gegen `/api/v1/site/configuration`
3. Cloud:
   - Bearer Token
   - Sites laden
   - Site auswaehlen
4. Hybrid:
   - Cloud fuer Site-Metadaten und optional Remote-Fallback
   - Lokal fuer schnelle States und Commands

Empfohlene Runtime-Architektur:

- Ein `DataUpdateCoordinator` fuer Site/EnergyFlow.
- Ein zweiter Coordinator fuer Thing-States, falls wir viele Einzelgeraete abbilden.
- ConfigEntry-Optionen fuer Polling-Intervalle und Entity-Auswahl.
- Standard-Polling lokal z.B. 10-30 Sekunden fuer Leistung und SOC.
- Cloud-Polling konservativer, z.B. 60-300 Sekunden, um API und Rate Limits zu schonen.

## Entity-Mapping

MVP-Sensoren aus Energy Flow:

- PV-/Produktion: `POWER_PRODUCTION`, `ENERGY_PRODUCED`
- Hausverbrauch: `POWER_CONSUMPTION` oder `POWER_CONSUMPTION_CALC`
- Netz: `POWER_GRID`, `ENERGY_IMPORTED`, `ENERGY_EXPORTED`
- Speicher: `POWER_STORAGE`, `STATE_OF_CHARGE`, `ENERGY_CHARGED`, `ENERGY_DISCHARGED`
- Autarkie: `SELF_SUFFICIENCY`
- Ladepunkte: `POWER_CHARGING_POINTS`, `ENERGY_CHARGED_CHARGING_POINTS`
- Heizung: `POWER_HEATING`, `ENERGY_HEATING`

Device-Klassen in HA:

- `SensorEntity` fuer Leistung, Energie, Spannung, Strom, Frequenz, Temperatur, SOC.
- `BinarySensorEntity` fuer Verbindung, Online-Status, Fehlerstatus.
- `NumberEntity` fuer steuerbare numerische Werte wie Batteriezielpower oder Ladeleistung.
- `SwitchEntity` oder `ButtonEntity` fuer start/stop/pause Charging, nur wenn DataPoint als `controllable` markiert ist.
- `SelectEntity` fuer Betriebsmodi, falls stabile Enum-Werte sichtbar sind.

Wichtig fuer Energy Dashboard:

- Energie-Sensoren brauchen `state_class=total_increasing` oder passende HA-Semantik.
- Leistungs-Sensoren `state_class=measurement`.
- Einheiten sauber nach HA-Konstanten mappen: `W`, `kWh`, `Wh`, `%`, `V`, `A`, `Hz`, `°C`.
- Fuer Energie ggf. Wh nach kWh konvertieren, wenn HA das fuer Langzeitstatistik besser erwartet.

## Steuerung und Sicherheit

Commands sollten nicht im ersten MVP breit freigeschaltet werden.

Empfohlene Phasen:

1. Read-only MVP.
2. Kontrollierte Batteriesteuerung fuer explizit controllable DataPoints, z.B. `TARGET_POWER`.
3. Ladepunktsteuerung fuer `MAX_POWER_CHARGE`, `MAX_CURRENT_CHARGE`, `ENABLE_CHARGING`, `PAUSE_CHARGING`.
4. External Plant Controls separat und mit klarer UI-Warnung, weil diese Werte systemkritischer sein koennen.

Sicherheitsregeln:

- Commands nur fuer DataPoints mit `controllable: true`.
- Wertebereiche aus Settings/Metadaten beachten, falls vorhanden.
- Keine Automatik, die ohne Nutzeraktion Zielwerte setzt.
- Service Calls mit Validierung und klarer Fehlermeldung.
- HA-Entity fuer kritische Commands standardmaessig deaktiviert oder nur ueber Options-Flow aktivierbar.

## Umsetzung in Phasen

Phase 1: Research und lokale Probe

- BEAAM-IP und API-Key testen.
- `/api/v1/site/configuration` sichern/anonymisieren.
- `/api/v1/site/state` und relevante Thing-States lesen.
- Datenpunkte, Einheiten und Vorzeichen aus realem System validieren.

Phase 2: Python-Library

- Projekt mit `pyproject.toml`, Ruff, pytest, pytest-asyncio.
- Async HTTP Client mit Mock-Tests.
- Modelle fuer Site, Thing, DataPoint, State, EnergyFlow.
- Lokaler Client zuerst, Cloud-Client danach.

Phase 3: Home-Assistant Custom Component

- `custom_components/neoom/`
- Config Flow fuer lokal/cloud/hybrid.
- Sensoren aus EnergyFlow.
- Device Registry pro Site und Thing.
- Diagnostics mit anonymisierten IDs.

Phase 4: Erweiterung

- Thing-spezifische Sensoren.
- Options-Flow zur Entity-Auswahl.
- Command-Entities fuer Batterie und Ladepunkt.
- Repairs/Warnings fuer veraltete API-Versionen oder fehlende DataPoints.

Phase 5: Veroeffentlichung

- PyPI-Paket veroeffentlichen.
- HACS-Repository fuer die HA-Integration.
- README mit lokaler und Cloud-Konfiguration.
- Beispiel-Diagnostics und bekannte DataPoint-Mappings dokumentieren.

## Offene Fragen

- Welche Hardware ist konkret vorhanden: BEAAM, KJUUBE, BLOKK, Ladepunkt, Waermepumpe, Zaehler?
- Ist ein BEAAM API-Key bereits vorhanden?
- Soll Cloud nur Fallback sein oder vollwertig parallel nutzbar?
- Gibt es mehrere Sites oder nur einen Standort?
- Welche Steuerfunktionen sind gewuenscht: nur Monitoring, Batteriezielpower, Ladepunkt, Generic Device Ingest?
- Welche realen DataPoints liefert das System, insbesondere fuer Speicher-SOC, Netzleistung und PV?

## Empfehlung fuer den naechsten Schritt

Als naechstes sollten wir ein gemeinsames Repository mit zwei Artefakten anlegen:

```text
packages/neoom-connect/          # PyPI Library
custom_components/neoom/         # HA Integration, solange noch nicht separiert
```

Sobald die Library stabil ist, koennen wir entscheiden, ob die HA-Integration im selben Repo bleibt oder als eigenes HACS-Repo ausgekoppelt wird. Die Paketlogik sollte aber gemeinsam bleiben: ein PyPI-Paket, zwei API-Clients.
