# Pool Cockpit v2.7.9

1. Bisherige /config/www/pool-cockpit.js sichern.
2. pool-cockpit.js aus diesem ZIP nach /config/www/ kopieren und ersetzen.
3. Vorhandene JavaScript-Modul-Ressource auf /local/pool-cockpit.js?v=2.7.9 ändern.
4. Browser/App vollständig neu laden. Bestehende Kartenkonfiguration behalten.

Änderungen nur in der vollständigen Cockpit-Ansicht (view: full bzw. Standard):
- Überschrift Wasser & Kreislauf und bisherige Temperatur-Kachel entfallen.
- Pooltemperatur rechts über Poolsteuerung. Beschriftungen, Temperaturwert, Betriebsstatus und Zeitsteuerung beginnen an derselben linken Kante. Schriftgröße wie Betriebsstatus.
- Reihenfolge: Poolchemie & Pflege → Deine Vorräte → Technikübersicht.

Mobile Ansicht bleibt auf Stand v2.7.6. Backup enthält die vorherigen JavaScript-Dateien. Die HTML-Vorschauen verwenden Beispieldaten ohne Live-Verbindung.

Neu v2.7.9: Technikübersicht als Überschrift oberhalb des Rahmens (vollständiges Cockpit). Status bleibt im Feld. Im gemeinsamen Technikschaubild: Doppelpunkte bei Arbeitsdruck, Speicherdruck und Filterdruck; Filtertitel höher; Druckfeld zweizeilig mit Filterdruck max. aus der vorhandenen Zuordnung filter_max_bar (sensor.poolfilter_druck_max).
