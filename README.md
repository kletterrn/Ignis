1. PowerShell in diesem Ordner öffnen.
2. Abhängigkeiten installieren:

   ```powershell
   python.exe -m pip install -r requirements.txt
   ```

3. Für NASA API `https://firms.modaps.eosdis.nasa.gov/api/area/` . Für Basemaps `https://carto.com/basemaps/apikey/`

   ```powershell
   python.exe app.py
   ```

4. Im Browser `http://127.0.0.1:8000` öffnen.