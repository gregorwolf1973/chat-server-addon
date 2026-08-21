# Änderungsverlauf

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
