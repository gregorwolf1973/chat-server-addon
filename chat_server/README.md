# Chat Server

Selbstgehosteter Messenger für den eigenen Haushalt: Direktchats und Gruppen,
Bilder und Dateien, Sprachnachrichten, Anrufe und Videoanrufe, Einladungen,
eine Karte mit Standortfreigaben, eine persönliche Galerie und
Push-Benachrichtigungen aufs Handy.

Alles bleibt auf deiner Hardware. Keine Konten bei fremden Anbietern, keine
Telefonnummern.

> **Die ausführliche Anleitung steht im Reiter „Dokumentation".** Dort ist
> jede Funktion beschrieben — hier stehen nur die ersten Schritte.

## Loslegen

1. Unter **Konfiguration** `admin_user` und `admin_password` setzen.
2. Starten, dann **Öffnen**.
3. Anmelden und unter **… → Benutzer verwalten** weitere Konten anlegen.

## Die wichtigsten Optionen

| Option | Bedeutung |
|---|---|
| `admin_user`, `admin_password` | Das erste Konto. Wird nur beim **ersten** Start ausgewertet — später ändert man das Passwort in der Oberfläche |
| `external_url` | Die vollständige Adresse von außen, z. B. `https://chat.example.org`. Ohne sie öffnen Push-Nachrichten die falsche Seite |
| `api_token` | Für Nachrichten aus Automationen. Leer lassen ist die bessere Wahl: dann erzeugt das Add-on eines, zeigt es in den Einstellungen und lässt es dort auch wechseln |
| `max_upload_mb` | Größte Datei, 1 bis 200 |
| `allow_registration` | Ob Fremde einen Zugang beantragen dürfen. Freigeben muss ihn immer ein Administrator |
| `retention_days` | Nachrichten und Anhänge älter als X Tage löschen. `0` heißt: nie |
| `stun_server` / `turn_server` | Nur für Anrufe von unterwegs |

## Von unterwegs

Im Heimnetz genügt **Öffnen** (Ingress). Von außen braucht es **HTTPS** —
Kamera, Mikrofon, Standort und Push gibt kein Browser über eine ungesicherte
Verbindung frei. Ein Cloudflare Tunnel oder ein Reverse Proxy erledigt das;
beides steht in der Dokumentation.

## Gut zu wissen

* Die Daten liegen in `/data`. Hochgeladene Dateien sind vom Backup
  ausgenommen — sonst würde jede Sicherung schnell unhandlich
* **Keine Ende-zu-Ende-Verschlüsselung.** Auf dem Server stehen die
  Nachrichten im Klartext; wer den Server hat, hat sie. Das bist du
* Die Oberfläche ist deutsch
