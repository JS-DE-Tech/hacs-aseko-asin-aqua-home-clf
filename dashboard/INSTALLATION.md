# Pool Cockpit v2.7.9

1. `pool-cockpit.js` nach `/config/www/` kopieren.
2. Die JavaScript-Modul-Ressource `/local/pool-cockpit.js?v=2.7.9` eintragen.
3. In der Kartenkonfiguration `type: custom:pool-cockpit` verwenden.
4. Browser beziehungsweise Home-Assistant-App vollständig neu laden. Die übrige Kartenkonfiguration kann beibehalten werden.

Änderungen nur in der vollständigen Cockpit-Ansicht (view: full bzw. Standard):
- Überschrift Wasser & Kreislauf und bisherige Temperatur-Kachel entfallen.
- Pooltemperatur rechts über Poolsteuerung. Beschriftungen, Temperaturwert, Betriebsstatus und Zeitsteuerung beginnen an derselben linken Kante. Schriftgröße wie Betriebsstatus.
- Reihenfolge: Poolchemie & Pflege → Deine Vorräte → Technikübersicht.

Mobile Ansicht bleibt auf Stand v2.7.6. Die HTML-Vorschauen verwenden Beispieldaten ohne Live-Verbindung.

Neu v2.7.9: Technikübersicht als Überschrift oberhalb des Rahmens (vollständiges Cockpit). Status bleibt im Feld. Im gemeinsamen Technikschaubild: Doppelpunkte bei Arbeitsdruck, Speicherdruck und Filterdruck; Filtertitel höher; Druckfeld zweizeilig mit Filterdruck max. aus der vorhandenen Zuordnung filter_max_bar (sensor.poolfilter_druck_max).
