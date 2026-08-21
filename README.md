# Chat Server – Home Assistant Add-on

Selbstgehosteter Messenger für den eigenen Haushalt. Läuft als Add-on auf Home
Assistant OS, alle Daten bleiben auf der eigenen Hardware.

[![Add-Repository zu Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fgregorwolf1973%2Fchat-server-addon)

## Funktionen

- Direktchats und Gruppen, Anmeldung mit eigenem Konto
- Bilder und Dateien senden (Standard bis 25 MB)
- Antworten mit Zitat, Nachrichten löschen
- Online-Anzeige, Tippen-Anzeige, Ungelesen-Zähler
- Push-Benachrichtigungen aufs Handy über Web Push
- Nachrichten aus Home-Assistant-Automationen über `POST /api/notify`
- Zugriff über Ingress im Heimnetz, über den Cloudflare Tunnel von unterwegs

## Add-ons in diesem Repository

| Add-on | Beschreibung |
|---|---|
| [Chat Server](./chat_server) | Messenger-Server mit Gruppen, Dateien und Push |

## Installation

1. In Home Assistant: **Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories**
   und `https://github.com/gregorwolf1973/chat-server-addon` hinzufügen
   (oder den Knopf oben verwenden).
2. „Chat Server" installieren, unter **Konfiguration** `admin_user` und
   `admin_password` setzen, starten.
3. Über **Öffnen** anmelden und weitere Konten anlegen.

Die vollständige Anleitung steht in [chat_server/DOCS.md](./chat_server/DOCS.md).

## Lizenz

MIT – siehe [LICENSE](./LICENSE).
