# Änderungsverlauf

## 0.2.1

- PWA-Manifest korrigiert: Symbole und Startadresse zeigten wegen der relativen
  Pfade ins Leere, die zum Home-Bildschirm hinzugefügte App landete auf einer
  Fehlerseite
- Kein doppelter Tagestrenner mehr vor jeder eingehenden Nachricht, und der
  Absendername wiederholt sich in Gruppen nicht mehr bei jeder Zeile
- Das Antippen einer Push-Benachrichtigung springt jetzt in den passenden Raum,
  auch wenn der Chat schon in einem Fenster offen ist
- Hochgeladene Dateien werden nur noch dann im Browser angezeigt, wenn sie
  wirklich ein Bild sind – ein selbst gesetztes `text/html` konnte sonst als
  Seite im Chat ausgeführt werden
- Dateien lassen sich nur noch an eigene Nachrichten anhängen; fremde Datei-IDs
  werden abgewiesen
- Das Token der Home-Assistant-Schnittstelle steht nicht mehr im Add-on-Log
- Architektur `armv7` entfernt: Home Assistant und der Add-on-Builder
  unterstützen keine 32-Bit-Architekturen mehr

## 0.2.0

- Antworten auf einzelne Nachrichten mit Zitat im Verlauf
- Nachrichten löschen (eigene immer, fremde nur als Administrator)
- Schnittstelle `POST /api/notify` für Nachrichten aus Home Assistant,
  inklusive automatischem Direktchat mit dem Konto „Home Assistant"
- Neue Räume erhalten Nachrichten sofort, ohne die Seite neu zu laden
- Bestehende Datenbanken werden beim Start automatisch migriert

## 0.1.0

- Erste Version: Anmeldung, Kontenverwaltung, Direkt- und Gruppenchats
- Datei- und Bildversand, Online- und Tippen-Anzeige, Ungelesen-Zähler
- Push-Benachrichtigungen über Web Push (VAPID)
- Zugriff über Ingress und über Port 8099 für den Cloudflare Tunnel
