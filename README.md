# neoom CONNECT / BEAAM fuer Home Assistant

Lesende Integration fuer Speicher, PV, Netz und angeschlossene Energiegeraete.
Ein gemeinsames Python-Paket `py-neoom-connect` enthaelt getrennte Clients fuer die
lokale BEAAM-API und die neoom-Cloud.

## Aktueller Stand

Die lokale API wurde an einem echten BEAAM geprueft. Ein isolierter Test mit
Home Assistant 2026.9.3 hat acht Geraete und 104 Entitaeten eingerichtet,
aktualisiert und wieder entladen. Details stehen in [docs/VALIDATION.md](docs/VALIDATION.md).
Auch Cloud-only mit zehn Sensoren sowie Hybrid mit echten Cloud-Abfragen,
simuliertem lokalem Ausfall und lokaler Wiederherstellung wurden erfolgreich geprueft.

## Installation

Voraussetzung: Home Assistant 2026.9 oder neuer und HACS. Die Python-Abhaengigkeit
[`py-neoom-connect==0.1.0`](https://pypi.org/project/py-neoom-connect/0.1.0/)
ist auf PyPI veroeffentlicht.

1. In HACS `https://github.com/Lechtob/ha-neoom` als benutzerdefiniertes Repository
   der Kategorie **Integration** hinzufuegen.
2. **neoom CONNECT / BEAAM** herunterladen und Home Assistant neu starten.
3. Unter **Einstellungen > Geraete & Dienste > Integration hinzufuegen** nach
   **neoom** suchen und Lokal, Cloud oder Hybrid auswaehlen.
4. Fuer Lokal die BEAAM-Adresse und den lokalen API-Key eingeben. Fuer Cloud
   den Cloud-Token eingeben und den Standort auswaehlen. Hybrid benoetigt beide
   Zugaenge zum selben Standort und bevorzugt die lokale Verbindung.

Home Assistant installiert die Python-Abhaengigkeit automatisch. Die Schluessel
werden nur im Einrichtungsdialog eingegeben; sie gehoeren nicht ins Repository.
Die Bibliothek kann unabhaengig mit `pip install py-neoom-connect` genutzt werden;
der Python-Import lautet `neoom_connect`.

## Verbindungsarten

| Modus | Einrichtung | Betrieb |
| --- | --- | --- |
| Lokal | BEAAM-Adresse und API-Key | Standardmaessig alle 20 Sekunden |
| Cloud | Cloud-Token und Standortauswahl | Standardmaessig alle 120 Sekunden |
| Hybrid | Beide Zugaenge zum selben Standort | Lokal bevorzugt, Cloud bei Verbindungsausfall |

Im Hybridbetrieb werden Cloud-Abfragen begrenzt und lokale Abfragen weiterhin
versucht. Bei lokaler Erholung schaltet die Integration zurueck. Lokale
Geraetewerte und Energiezaehler, die die Cloud nicht liefert, werden waehrend
des Fallbacks nicht verfuegbar. Sie werden weder als Null noch als alter Wert ausgegeben.

Abfrageintervalle sind in den Integrationsoptionen einstellbar. Ungueltige
Zugangsdaten starten eine erneute Anmeldung. Derselbe Standort wird auch bei
unterschiedlichen Verbindungsarten nicht doppelt eingerichtet.

Ab Version 0.2.0 lassen sich ueber **Neu konfigurieren** die BEAAM-Adresse und
API-Schluessel aendern. Leere Schluesselfelder behalten den bisherigen Schluessel.
Die Verbindungen werden vor dem Speichern geprueft; der Standort und die
Verbindungsart bleiben unveraendert. Entitaets-IDs und Historie bleiben erhalten.

## Messwerte

- Standort: PV, Netz, Speicherleistung, Ladezustand, Verbrauch und Energiezaehler.
- Geraete: skalare numerische Datenpunkte aus BEAAM-Metadaten, mit den gelieferten Einheiten.
- Status: Verbindung und Fehlerstatus, sofern vom Geraet angeboten.
- Diagnoseexport ohne API-Schluessel, Adressen, Standortnamen oder originale Geraete-IDs.

Ab Version 0.1.1 ergaenzen Diagnoseentitaeten den Standort:

- **Datenquelle**: lokaler BEAAM oder Cloud.
- **Standortverbindung**: gueltige Standortdaten vorhanden. Im Hybridbetrieb gilt
  das auch fuer Cloud-Daten innerhalb des vorgesehenen Cache-Intervalls; es ist
  keine separate Echtzeit-Erreichbarkeitspruefung beider Schnittstellen.
- **Cloud-Rueckfall aktiv**: nur im Hybridbetrieb, aktiv bei Cloud-Ersatzbetrieb.

Bei vollstaendigem Ausfall zeigt die Standortverbindung getrennt an; Datenquelle
und Cloud-Rueckfall werden nicht verfuegbar. Ein einzelnes ausgefallenes Geraet
macht die weiterhin funktionierende Standortverbindung nicht getrennt.
Der Diagnoseexport enthaelt ausserdem die eingestellten Abfrageintervalle.

Technische Messwerte erscheinen als Diagnoseentitaeten. Nicht gelieferte Werte
bleiben unbekannt; unveraenderte Zeitstempel allein machen einen Wert nicht
unverfuegbar. Energiezaehler nutzen Wh und passende Statistikklassen fuer das
Energy Dashboard. Cloud-only liefert laut dokumentierter API keine Energiezaehler.

Ab Version 0.2.0 werden `INPUTS_POWER`, `VOLTAGES` und `CURRENTS` als einzelne
Kanaele mit festen, bei 1 beginnenden Nummern angezeigt. Diese Nummern folgen der
Reihenfolge in der BEAAM-API und sind keine zugesicherte physische String-Zuordnung.
Die Erkennung erfolgt bei lokalen Abfragen und ist auf 64 Kanaele je Datenpunkt
begrenzt. Fehlende Kanaele werden nicht verfuegbar; ungueltige Werte bleiben unbekannt.
Andere Arraytypen und Steuerfunktionen sind weiterhin nicht umgesetzt.
Vorzeichen der API bleiben erhalten: Geraete- und Standortwerte koennen
unterschiedliche Vorzeichenkonventionen haben.

## Entwicklung und Tests

Python 3.14 fuer die HA-Tests, mindestens Python 3.11 fuer die Bibliothek:

```console
python -m pip install -e ".[test,build]" -r requirements_test.txt
python -m pytest
ruff check packages custom_components tests tools
```

Die Tests verwenden den echten Home-Assistant-Kern und dessen Registries,
mit ersetztem HTTP-Transport. Der Linux-Runner des pytest-Plugins wird nicht
geladen, sodass diese Tests auch unter Windows laufen.

Nur Bibliothek: `python -m pip install -e ".[test]"`, danach
`python -m pytest --ignore=tests/ha`.

Lesender Zugriff auf einen eigenen BEAAM, mit verdeckter Schluesselabfrage:

```console
python -m neoom_connect.probe 192.0.2.10 --output diagnostics-local.json
```

Alternativ nimmt `--key-file BEAAM_API-Key.txt` eine lokale Schluesseldatei.
Der Bericht entfernt Identitaetsdaten; Messwerte bleiben fuer den Abgleich erhalten.

Ein isolierter HA-Livetest ist mit `python -m tools.check_live_ha HOST --key-file PATH`
aus dem Projektverzeichnis moeglich. Er verwendet echte Leseabfragen, einen
temporaeren HA-Kern und aendert keine produktive HA-Installation.

Cloud und Hybrid lassen sich mit separaten Schluesseldateien pruefen:

```console
python -m tools.check_live_ha HOST --mode cloud --cloud-key-file CONNECT_API-Key.txt --site-id-file CONNECT_Site-ID.txt
python -m tools.check_live_ha HOST --mode hybrid --key-file BEAAM_API-Key.txt --cloud-key-file CONNECT_API-Key.txt --site-id-file CONNECT_Site-ID.txt
```

Der Hybridtest simuliert den lokalen Ausfall ausschliesslich im Testprozess.
Schluessel und Standort-ID werden nicht ausgegeben und sind von Git ausgeschlossen.

Build und Veroeffentlichung: [docs/RELEASE.md](docs/RELEASE.md).
Architektur: [CONCEPT.md](CONCEPT.md).
