# Ignis · Feuerbeobachtung

[Öffentliche Plattform auf GitHub Pages](https://kletterrn.github.io/Ignis/) · [Cloud-Collector](https://github.com/kletterrn/Ignis/actions/workflows/collect.yml)

Deutschlandweiter, nichtkommerzieller Feldpilot: Satelliten-Wärmehinweise, modelliertes Wetter, lokale Kameraauswertung und geprüfte Brandflächen mit zeitlichem Vergleich. Der vollständige Python- und Webapp-Quellcode ist unter [Apache-2.0](LICENSE) offen verfügbar; siehe [Mitwirken](CONTRIBUTING.md) und [Drittanbieterhinweise](THIRD_PARTY_NOTICES.md).

## 3D-Ansicht und behördliche Erprobung

Unter **Darstellung → 3D-Gelände** wird ein echtes Höhenmodell mit Höhenmaßstab 1:1 geladen. Näher heranzoomen; mit rechter Maustaste oder Umschalt + Pfeiltasten drehen/neigen. Kartenstil, geprüfte Brandflächen, Zeitverlauf und Wind bleiben nutzbar; Vollbild ist über die Kartensteuerung verfügbar. Ein Ausfall der Höhendaten führt zur beschrifteten 2D-Ansicht zurück. Die DEM-Kacheln kommen aus dem offenen [Terrain-Tiles-Datensatz](https://registry.opendata.aws/terrain-tiles/); Auflösung und Datenalter variieren.

3D zeigt das Gelände mit kartierten Flächen, keine gemessene Flammenhöhe oder Brandvolumen. Hektarangaben bleiben unabhängig davon in EPSG:3035 berechnet. Für Behörden und Einsatzkräfte beschreibt [RESPONDER_READINESS.md](RESPONDER_READINESS.md) die vorhandenen Abläufe und die offenen Abnahmen. Die Plattform ist zur begleiteten Erprobung verfügbar; Einsatzreife ist noch nicht nachgewiesen.

Die lokale Konsole enthält zusätzlich **Stereo-Tiefe mit drehbarer 3D-Punktwolke** und **radiometrische Thermalauswertung**. Benötigt werden echte Kalibrierparameter/synchrone Bildpaare bzw. orthorektifizierte Temperatur-GeoTIFFs mit Sensor-Metadaten. [SENSOR_GUIDE.md](SENSOR_GUIDE.md) dokumentiert Formate, Grenzen, Exporte und reproduzierbare synthetische Testdaten. Normales Video liefert keine Temperaturen; Stereo-Kamerakoordinaten liefern ohne georeferenzierten Kamerapose-Nachweis keinen Brandort.

## Start unter Windows

Voraussetzung: [uv](https://docs.astral.sh/uv/), Python 3.11–3.13 (uv kann Python bereitstellen).

```powershell
Copy-Item .env.example .env # nur bei einer neuen Installation; bestehende .env nicht überschreiben
.\Launch-Ignis.ps1
```

Operator: `http://127.0.0.1:8000/operator`. Öffentliche lokale Ansicht: `http://127.0.0.1:8000/`. Der Operatorserver bindet ausschließlich an Loopback. SQLite, Rohmaterial, Kameraadressen und Modelle liegen im ignorierten Ordner `data/`.

```powershell
uv sync --frozen
uv run pytest -q
node --test tests/*.test.cjs
uv run python -m scripts.collect
```

## Arbeitsablauf

1. Video/Bildfolge hochladen oder eine eigene RTSP-Kamera eintragen. Ein Stream, maximal ein ausgewertetes Bild pro Videosekunde; CPU ist unterstützt. Das aktuelle Bild kann auch ohne automatischen Alarm manuell als Beleg markiert werden.
2. Belege auswählen, Ereignis erstellen. Kameraort oder Rauchbild erzeugen keine Brandkoordinate oder Hektarangabe.
3. GeoJSON-Umriss importieren, auf einer georeferenzierten Drohnenaufnahme zeichnen oder Sentinel-2-Szenen suchen/laden und einen dNBR-Vorschlag erzeugen. Geometrie, Löcher, tatsächliche Abdeckung, Quellennachweis und Aufnahmezeit prüfen.
4. Fläche als neue Version speichern und ausdrücklich freigeben. Zwei kompatible freigegebene Versionen vergleichen.
5. Ereignis veröffentlichen. Nur die ausgewählten JPEG-Vorschaubilder (maximal fünf) und geprüften Flächen werden hochgeladen. „Zurückziehen“ blendet Ereignis, Flächen und Bilder öffentlich aus. Bei Netzwerkfehlern bleibt die Veröffentlichung in der lokalen Outbox und kann erneut gesendet werden.

Satellitenpunkte werden mit dem UBA-PRTR-Register und dem EEA-Industrieanlagenregister für Nachbarländer im Kartenausschnitt (Berichtsjahr 2024) abgeglichen. Hinweise innerhalb von 1 km eines registrierten Betriebs erscheinen grau mit Namen, Abstand und Quelle. Das ist Standortkontext, keine bestätigte Ursache: Auch Industrieanlagen können brennen. Rohbeobachtungen bleiben erhalten und sind standardmäßig sichtbar; „Industriekontext“ blendet sie bei Bedarf aus. Fehlende Registereinträge bedeuten nicht, dass keine Industrie vorhanden ist. Der vollständige Registerabzug wird höchstens wöchentlich geladen und in GitHub Actions ohne Zugangsdaten gecacht.

Die früheren 0,05°-Quadrate sind entfernt. **Sensorumfelder** folgen jetzt einzelnen Beobachtungen: vorhandene FIRMS-Scan-/Track-Maße bestimmen den umschreibenden Kreis, andernfalls wird ein beschrifteter nominaler Sensormaßstab verwendet. Das ist eine ungefähre Pixelumgebung bei unbekannter Scan-Ausrichtung, keine Brandgrenze und keine Hektarmessung. Industriekontext erhält keinen solchen Flächenumriss. Tatsächliche Brandflächen entstehen weiterhin nur aus geprüfter georeferenzierter Kartierung.

Flächen werden in EPSG:3035 berechnet. Verbrannte Fläche, Umrissfläche einschließlich unversehrter Inseln und aktive Fläche werden unterschiedlich bezeichnet. Wachstum ist eine Änderung kartierter Flächen; Windpfeile zeigen Luftbewegung. Fehlende/abweichende Abdeckung, unpassende Daten oder deutliche Flächenkontraktion unterdrücken die Bewegungsbestimmung.

## Zugangsdaten und Veröffentlichung

- `FIRMS_MAP_KEY`: frisch ausgestellter [NASA-FIRMS-Schlüssel](https://firms.modaps.eosdis.nasa.gov/api/map_key/). Der früher öffentliche Schlüssel wurde lokal entfernt. Seine Sperrung muss beim Anbieter erfolgen; Git-Historie wurde nicht umgeschrieben.
- `CDSE_CLIENT_ID`, `CDSE_CLIENT_SECRET`: Copernicus Sentinel-Hub OAuth-Client. Ohne diese Werte funktionieren Szenensuche und lokale Rasterimporte; Szenendownload bleibt unkonfiguriert.
- `IGNIS_SITE_URL`, `IGNIS_OPERATOR_TOKEN`: lokale Veröffentlichung. Niemals in Git einchecken.
- GitHub Actions: Repository-Variable `IGNIS_SITE_URL` und Secret `IGNIS_COLLECTOR_TOKEN`; optional Secret `FIRMS_MAP_KEY`. Der Collector läuft auf dem Default-Branch alle 15 Minuten und zusätzlich manuell. Ohne FIRMS-Schlüssel bleibt NASA ausdrücklich unkonfiguriert; Wetter wird weiterhin gesammelt.
- Sites: separate geheime `IGNIS_COLLECTOR_TOKEN` / `IGNIS_OPERATOR_TOKEN`, D1 `DB`, R2 `BUCKET`. Der öffentliche Dienst nimmt keine Operator-Browseraktionen an.

Die öffentliche Webapp wird durch `.github/workflows/pages.yml` auf **GitHub Pages** veröffentlicht. `uv run python -m scripts.prepare_site --github-pages` erzeugt die statischen Dateien. GitHub Pages führt keinen Python-Server und keine D1/R2-API aus: Diese Daten-API bleibt separat auf Sites; das alte Frontend leitet auf GitHub weiter. CORS erlaubt öffentliche GET-Abrufe von `https://kletterrn.github.io`, Schreibzugriffe bleiben authentifiziert und browserseitig gesperrt. Flask und Python verarbeiten lokale Daten. Gemeinsame Darstellung vor jedem Site-Build mit `uv run python -m scripts.prepare_site` aktualisieren. Unter `site/`: `npm ci`, `npm run db:generate` nur bei Schemaänderungen, `npm run build`. Migrationen liegen unter `site/drizzle/` und werden bei Sites-Veröffentlichung angewendet. Lokale Worker-Tests benötigen `site/.dev.vars` neben der gebauten Wrangler-Konfiguration: `Copy-Item .dev.vars dist/server/.dev.vars`. Diese Testdatei vor dem Packaging entfernen. Die Produktivveröffentlichung verwendet ausschließlich native Sites-Secrets.

Keine kostenpflichtigen Dienste oder Abonnements werden automatisch aktiviert. GitHub-Zeitpläne können sich verzögern und nach 60 Tagen Repository-Inaktivität deaktiviert werden. Der öffentliche Feedstatus zeigt den letzten Erfolg; nach 45 Minuten wird er als veraltet markiert. Rohbeobachtungen werden nach 90 Tagen gelöscht, geprüfte Ereignisse bleiben erhalten. Lokale Rohdateien werden nur bewusst vom Operator gelöscht; vorher Backup erstellen.

## Validierung und Grenzen

Siehe [VALIDATION.md](VALIDATION.md) für Ergebnisse. Der lokale Worker verwendet jetzt einen per SHA256 fixierten Pyronear-YOLO11s-Rauchdetektor mit Bildausschnitten und räumlicher Bestätigung über fünf Samples / mindestens vier Sekunden. Ein Hinweis pro Episode; Wiederbereitschaft nach 30 Sekunden ohne positiven Befund. Das frühere ReXNet bleibt nur für Vergleichsmessungen erhalten. **Die Abnahme ist nicht bestanden:** Auf 66 unabhängigen Archivbildern sanken Fehlpositive von 18 auf 1, gleichzeitig sank die Raucherkennung von 25/34 auf 15/34. Beide positiven Videoclips blieben ohne automatischen Hinweis. Rohscores sind keine Wahrscheinlichkeiten; manuelle Prüfung und Belegsicherung sind erforderlich. Kein Alarm ist keine Entwarnung. Große Bilder erreichen auf dieser CPU nur ungefähr 0,49 Bilder/s; Jobstatus zeigt Durchsatz und verworfene RTSP-Samples.

```powershell
uv run python -m scripts.evaluate_camera --fetch # vier Ereignisse + sieben echte Videos, beide Modelle
uv run python -m scripts.fetch_validation
uv run python -m scripts.benchmark data/validation/manifest.csv
uv run python -m scripts.replay
uv run python -m scripts.validate_perimeter kandidat.geojson referenz.geojson
```

HPWREN-FIgLib-Aufnahmen: © HPWREN / UCSD; FURG Fire Dataset: Steffens et al., CC0. Rohbilder, Videos und Modelle bleiben lokal und werden nicht veröffentlicht. Vier HPWREN-Ereignisse von 2026 liegen nach den fixierten YOLO-Gewichten von 2025; Trainingsüberschneidung der älteren FURG-Videos ist unbekannt. Protokoll, Quell-URLs, Dateiprüfsummen und Ergebnisse stehen unter `validation/`. Drittanbieter-Lizenzen einschließlich widersprüchlicher Modell-Lizenzangaben sind in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) dokumentiert.

Am 18.10.2026 wurden NASA (alle vier Quellen in GitHub Actions) und Copernicus OAuth + echter Vierband-Download erfolgreich geprüft. Zugangsdaten liegen ausschließlich in lokaler `.env` bzw. GitHub Secrets. Für Neuinstallationen müssen eigene Schlüssel gesetzt werden. Sentinel-Abfragen berücksichtigen ±15 Minuten um den STAC-Produktstart, da Kachelzeitpunkte abweichen; Zeitbasis und Szenen-ID bleiben beim Upload erhalten. Leere Abdeckung wird abgelehnt.
