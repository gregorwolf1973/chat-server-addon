# Chat Server – Home Assistant Add-on

Selbstgehosteter Messenger für den eigenen Haushalt: Direktchats, Gruppen,
Datei- und Bildversand, Online-Anzeige, Tippen-Anzeige und Push-Benachrichtigungen
auf dem Handy. Läuft als Add-on auf dem Pi, Daten bleiben in `/data`.

## Installation

1. In Home Assistant: **Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories**
   und `https://github.com/gregorwolf1973/chat-server-addon` hinzufügen.
2. „Chat Server“ installieren, unter **Konfiguration** `admin_user` und
   `admin_password` setzen, starten.
3. Über **Öffnen** (Ingress) anmelden. Weitere Konten legst du als Administrator
   unter **… → Benutzer verwalten** an.

## Konfiguration

| Option | Bedeutung |
|---|---|
| `admin_user` / `admin_password` | wird beim ersten Start als Administrator angelegt; spätere Änderungen der Option ändern das Passwort **nicht** (das geht in der Oberfläche) |
| `external_url` | vollständige externe Adresse, z. B. `https://chat.biker633.org` – wird für die Ziel-URL der Push-Benachrichtigungen gebraucht |
| `max_upload_mb` | Größenlimit pro Datei (Standard 25) |
| `allow_registration` | ob sich Leute selbst um Zugang bewerben dürfen (Standard: ja). Freigeben musst du sie trotzdem – ohne Freigabe kommt niemand hinein |

## Externer Zugriff über Cloudflare Tunnel

Ingress reicht fürs Heimnetz, für Handy-Push brauchst du eine eigene Subdomain.
In der Tunnel-Konfiguration einen Public Hostname anlegen:

```
chat.biker633.org  ->  http://172.30.32.1:8099
```

`172.30.32.1` statt `homeassistant` verwenden (der Name löst auf IPv6 auf).
Danach `external_url: https://chat.biker633.org` setzen und das Add-on neu starten.

## Push-Benachrichtigungen

* Funktionieren nur über **HTTPS**, also über die externe Adresse – nicht über die
  Ingress-URL, deren Pfad-Token sich ändert.
* Auf dem Handy die Seite öffnen, unten links auf **Push** tippen und erlauben.
* iOS ab 16.4: die Seite muss vorher über **Teilen → Zum Home-Bildschirm** als
  App installiert werden, sonst bietet Safari kein Push an.
* Der VAPID-Schlüssel wird beim ersten Start erzeugt und liegt in `/data/vapid.json`.
  Wird er gelöscht, müssen sich alle Geräte neu für Push anmelden.

## Nachrichten aus Home Assistant

Das Add-on legt ein Konto „Home Assistant“ an. Über `POST /api/notify` schreibt
eine Automation in eine Gruppe oder direkt an eine Person.

Das **Token** findest du als Administrator unter **… → Einstellungen → Home
Assistant** zum Kopieren. Alternativ setzt du die Add-on-Option `api_token`
auf einen eigenen Wert – dann kennst du es ohnehin.

In `secrets.yaml`:

```yaml
chat_token: "Bearer DEIN-TOKEN"
```

Das `Bearer ` davor ist die übliche Form; das nackte Token allein wird
ebenso angenommen. Die Anführungszeichen sind wichtig, wenn das Token
Sonderzeichen wie `&` enthält.

In `configuration.yaml` zwei Dienste – einer für den Alltag, einer für
Dringendes:

```yaml
rest_command:
  chat_nachricht:
    url: "http://172.30.32.1:8099/api/notify"
    method: POST
    headers:
      Authorization: !secret chat_token
      Content-Type: application/json
    payload: '{"room": "{{ room }}", "message": "{{ message }}"}'

  chat_alarm:
    url: "http://172.30.32.1:8099/api/notify"
    method: POST
    headers:
      Authorization: !secret chat_token
      Content-Type: application/json
    payload: '{"room": "{{ room }}", "message": "{{ message }}", "always": true}'
```

Die interne Adresse `172.30.32.1:8099` ist Absicht: So bleibt der Aufruf im
Haus und hängt nicht am Tunnel.

### In einer Automation

```yaml
actions:
  - action: rest_command.chat_nachricht
    data:
      room: Familie          # Gruppenname, Benutzername oder Anzeigename
      message: "Die Waschmaschine ist fertig"
```

**Häufige Stolperfalle:** Der Editor legt `data: {}` als Platzhalter an. Sobald
eigene Felder dazukommen, müssen die geschweiften Klammern weg – sonst meldet
er „bad indentation of a mapping entry“:

```yaml
data: {}                     # FALSCH, wenn darunter Felder folgen
  room: "Familie"

data:                        # RICHTIG
  room: "Familie"
```

`metadata: {}` bleibt unverändert stehen, dort gehört nichts hinein. Ältere
Automationen mit `service:` statt `action:` funktionieren weiterhin.

### Wer eine Benachrichtigung bekommt

Wer den Chat gerade offen hat, bekommt **keine** Benachrichtigung – die
Nachricht steht dann nur im Verlauf. Für Meldungen, die niemand verpassen
darf, nimmst du `chat_alarm` mit `"always": true`; dann klingelt es auch bei
offener App.

Die Antwort nennt unter `pushed`, an wie viele Geräte die Benachrichtigung
ging. Steht dort `0`, obwohl eine erwartet wurde, hat der Empfänger entweder
Push nicht eingeschaltet oder die App offen.

Ist `room` ein Benutzername, entsteht beim ersten Mal automatisch ein
Direktchat mit „Home Assistant“.

### Wenn nichts ankommt

Home Assistant meldet einen `rest_command` **auch dann als erfolgreich**, wenn
der Chat-Server die Nachricht ablehnt. Der Grund steht im **Add-on-Protokoll**
(Add-on → Protokoll):

| Eintrag | Bedeutung |
|---|---|
| `abgelehnt: das Token stimmt nicht` | Token in `secrets.yaml` stimmt nicht mit dem im Add-on überein |
| `abgelehnt: kein Token mitgeschickt` | Die Kopfzeile `Authorization` fehlt im `rest_command` |
| `abgelehnt: weder Gruppe noch Person mit dem Namen '…'` | Der Name unter `room` stimmt nicht; das Protokoll listet die vorhandenen Gruppen auf |
| `zugestellt, 0 benachrichtigt` | Angekommen, aber niemand wurde benachrichtigt – alle hatten den Chat offen. Mit `"always": true` klingelt es trotzdem |

## Zugang beantragen

Auf der Anmeldeseite steht **Zugang beantragen**. Wer das ausfüllt, gibt
Benutzernamen, Anzeigenamen, ein Passwort, **E-Mail oder Telefonnummer** und
eine kurze Begründung an.

Der Antrag legt noch kein nutzbares Konto an: Bis zur Freigabe kommt niemand
hinein, und der Name taucht auch in keiner Auswahlliste auf. Administratoren
finden die Anträge oben unter **… → Benutzer verwalten**, mit Kontaktdaten
und Begründung, und entscheiden mit **Freigeben** oder **Ablehnen**
(letzteres entfernt den Antrag). Wer als Administrator Push eingeschaltet
hat, bekommt bei jedem neuen Antrag eine Benachrichtigung.

Die Seite steht offen im Netz, deshalb nimmt sie höchstens drei Anträge je
Stunde und Absender an. Ganz abschalten lässt sie sich mit der Option
`allow_registration`.

## Benutzer verwalten

Administratoren finden unter **… → Benutzer verwalten** alle Konten mit ihren
Aktionen:

* **Passwort** – setzt ein neues Passwort. Das Konto wird dabei auf allen
  Geräten abgemeldet, damit ein vergessenes Passwort niemanden aussperrt.
  Gib das neue Passwort persönlich weiter und lass es danach selbst ändern.
* **Admin / Kein Admin** – vergibt oder entzieht Administratorrechte.
* **Sperren / Entsperren** – verwehrt den Zugang, ohne etwas zu löschen.
  Laufende Sitzungen enden sofort. Gesperrte Konten erscheinen nicht mehr in
  der Auswahl für neue Unterhaltungen, ihre Nachrichten bleiben stehen.
* **Löschen** – entfernt das Konto endgültig. Die Nachrichten bleiben im
  Verlauf, erscheinen aber unter „Gelöschtes Konto“, damit fremde
  Unterhaltungen keine Lücken bekommen.

Am eigenen Konto steht nur **Passwort** zur Verfügung, und der letzte
verbliebene Administrator lässt sich weder entmachten noch sperren – sonst
könnte niemand mehr Konten verwalten.

## Bilder für Personen und Gruppen

Jeder kann sein eigenes Bild setzen: **… → Einstellungen → Bild wählen**.
Das Gruppenbild ändert man, indem man in der Gruppe oben auf das runde Bild
neben dem Namen tippt – das darf jedes Mitglied. In einem Direktchat steht
dort das Bild der Gegenseite, dort gibt es nichts einzustellen.

Wer kein Bild hat, erscheint mit seinen Initialen auf farbigem Grund. Die
Farbe bleibt für dieselbe Person immer gleich.

Bilder werden **im Browser** auf 256 Pixel verkleinert und mittig quadratisch
zugeschnitten, bevor sie hochgeladen werden – aus einem Handyfoto werden so
rund 30 KB statt mehrerer Megabyte. Ein ersetztes Bild wird vom Server
gelöscht, es sammelt sich nichts an.

## Wie Nachrichten aussehen

In Gruppen steht an jeder fremden Nachricht das Bild des Absenders und sein
Name in einer eigenen Farbe – dieselbe Person hat immer dieselbe Farbe.
Eigene Nachrichten stehen rechts, ohne Bild und Namen. Im Direktchat
entfällt beides, dort ist ohnehin klar, wer schreibt.

Die Uhrzeit sitzt unten rechts in der Sprechblase.

**Angaben zur Unterhaltung:** Ein Tipp auf den Namen oben in der Kopfzeile
öffnet sie. Dort findest du:

* das Gruppenbild (bei Gruppen änderbar von jedem Mitglied),
* die **Farbe** der eigenen Sprechblasen – neun Töne zur Auswahl. Die Wahl
  gilt nur für dich, alle anderen behalten ihre,
* **Chat löschen** – entfernt die Unterhaltung nur bei dir. Die anderen
  behalten sie samt Verlauf. Bleibt danach niemand mehr übrig, verschwindet
  sie ganz,
* **Für alle löschen** (nur Administratoren) – entfernt sie endgültig,
  mitsamt Nachrichten und Anhängen, auch von der Platte.

**Profilbilder groß ansehen:** Ein Tipp auf das runde Bild neben einer
Nachricht oder auf das Bild in den Angaben zur Unterhaltung zeigt es
formatfüllend. Ein weiterer Tipp schließt die Ansicht.

## Abstimmung

Der Knopf 📊 öffnet eine neue Abstimmung: Frage, bis zu zwölf Antworten und
auf Wunsch **mehrere Antworten erlaubt**. Sie erscheint als Nachricht in der
Unterhaltung.

Ein Tipp auf eine Antwort gibt die Stimme ab, ein weiterer nimmt sie zurück.
Bei Einfachwahl ersetzt eine neue Stimme die vorherige. Balken und Zahlen
aktualisieren sich bei allen sofort, ohne die Seite neu zu laden. Wer für
welche Antwort gestimmt hat, zeigt der Tooltip.

Wer die Unterhaltung gerade nicht offen hat, bekommt eine Benachrichtigung
über die neue Abstimmung.

## Standort senden

Der Knopf 📍 neben der Büroklammer schickt den eigenen Standort. In der
Unterhaltung erscheint eine **Kartenvorschau** mit einer Nadel, darunter die
Koordinaten und **In Karten öffnen**.

Die Karte steckt als Umrissdatei im Add-on (102 KB, gemeinfreie Daten von
Natural Earth). Sie zeigt Länder- und Küstenlinien – genug, um die Gegend zu
erkennen, aber keine Straßen. **Es wird nichts von fremden Servern
nachgeladen**; erst ein Tipp auf „In Karten öffnen“ ruft eine
Kartenanwendung auf, und das ist dann eine bewusste Entscheidung.

Der Browser gibt den Standort **nur über HTTPS** heraus – also über
`external_url`, nicht über den Ingress im Heimnetz. Dort erscheint ein
entsprechender Hinweis.

## Einladungen und Termine

Der Knopf 📅 legt eine **Einladung** an: Titel, Zeitpunkt, Ort in Worten,
Beschreibung, ein Bild und Merkmale wie 🎵 Musik, 💃 Tanz, 🍺 Alkohol,
🍕 Essen, 🎬 Film, ⚽ Sport, 🎲 Spiele, 🌳 Draußen, 🎭 Kultur, 💬 Reden.
**Aktuellen Ort anhängen** setzt zusätzlich eine Kartenvorschau in die
Einladung.

Sie erscheint als Karte in der Unterhaltung. Jeder Teilnehmer antwortet mit
**Bin dabei**, **Vielleicht** oder **Kann nicht**; ein zweiter Tipp auf
dieselbe Antwort nimmt sie zurück. Wer eingeladen hat, steht automatisch auf
„Bin dabei“. Die Zusagen aktualisieren sich bei allen sofort.

**Ändern:** Wer eingeladen hat – und der Administrator – kann die Einladung
später über **Bearbeiten** anpassen: Titel, Zeit, Ort, Beschreibung, Merkmale
und Bild. Die Zusagen bleiben dabei erhalten. Wird ein Bild ersetzt,
verschwindet das alte von der Platte.

**Ort auf der Karte antippen:** Im Dialog öffnet **Auf der Karte wählen** eine
Straßenkarte. Ein Tipp setzt die Nadel, ein weiterer verschiebt sie.
**Aktueller Ort** übernimmt stattdessen die eigene Position, **Ort entfernen**
streicht ihn wieder. Ist die Straßenkarte abgeschaltet, steht dort ein Hinweis
mit einem Knopf, der sie einschaltet – auf der Umrisskarte läge ein Punkt
leicht mehrere Kilometer daneben, die taugt dafür nicht.

**Absagen** darf allein, wer eingeladen hat – bewusst auch der Administrator
nicht. Wer zu einer Feier lädt, entscheidet auch, ob sie stattfindet. Der
Termin bleibt danach sichtbar, nimmt aber keine Zusagen mehr an; über
**Absage zurücknehmen** steht er wieder, mit allen Zusagen von vorher.

Der Administrator kann fremde Termine also **ändern, aber nicht absagen**.
Wird ein Termin zum Problem, bleibt ihm die Unterhaltung selbst: Wer sie
löscht, nimmt die Termine darin mit.

## Was ist wo los?

Über der Live-Karte lässt sich einschränken, welche Einladungen sie zeigt:
nach Zeitraum (**Heute**, **Morgen**, **7 Tage**, **Alles**) und nach
Merkmalen. Mehrere Merkmale wirken als *oder* – „Musik" und „Tanz" zusammen
zeigt alles, wo eines von beidem läuft. Angeboten werden nur Merkmale, die in
den vorhandenen Einladungen auch vorkommen.

Eine Zeile sagt, wie viel der Filter übrig lässt (*„2 von 6 Einladungen"*),
und **Filter aufheben** setzt ihn zurück. Der Filter bleibt beim Schließen
erhalten. Die Standortfreigaben bleiben immer sichtbar – sie sind das, was
gerade passiert, nicht etwas Geplantes.

Termine ohne Zeitpunkt erscheinen nur unter **Alles**; bei ihnen lässt sich
nicht sagen, ob sie in einen Zeitraum fallen.

Im Abschnitt **Termine** der Seitenleiste stehen alle anstehenden Termine aus
allen Unterhaltungen, der nächste zuerst. Das ist nötig, weil eine Einladung
im Verlauf sonst nach oben rutscht und aus dem Blick gerät. Zwölf Stunden
nach Beginn fällt ein Termin aus der Liste – die laufende Feier ist noch zu
sehen, die von vorletzter Woche nicht mehr.

Wer die Unterhaltung gerade nicht offen hat, bekommt eine Benachrichtigung
über die Einladung.

## Live-Standort und der Abschnitt „Karten“

Über **Teilen** im Abschnitt **Karten** gibst du deinen Standort für eine
gewählte Dauer frei: 15 Minuten, 1 Stunde, 3 Stunden oder 8 Stunden. Länger
als acht Stunden geht nicht, und die Freigabe endet von selbst.

Die Freigabe gehört immer zu **einer Unterhaltung**. Damit ist ohne weiteres
Zutun klar, wer mitsehen darf: ihre Mitglieder. Wer eine Gruppe verlässt,
teilt dort sofort nicht mehr. Über **Beenden** hörst du jederzeit auf.

Solange eine Freigabe läuft, steht sie mit Name, Unterhaltung und Restzeit im
Abschnitt **Karten**. Ein Tipp öffnet die **Live-Karte** mit allen Punkten auf
einem gemeinsamen Ausschnitt.

Auf der Live-Karte stehen auch die **Einladungen**: jeder anstehende Termin,
bei dem ein Ort hinterlegt ist. Personen tragen ihr Profilbild, Einladungen
eine 📅-Fahne – so ist auf einen Blick klar, was was ist, auch wenn beides
dicht beieinanderliegt. Ein Tipp auf eine Fahne öffnet den Termin mit
Beschreibung, Merkmalen und Zusagen. Unter der Karte stehen beide Listen
getrennt: *Wer teilt gerade* und *Einladungen*.

Ein Termin ohne Ort erscheint nicht auf der Karte, ein abgesagter ebenso
wenig.

Solange du selbst teilst, schickt die Oberfläche alle zwei Minuten die neue
Position. Ohne eigene Freigabe wird der Standort **gar nicht abgefragt**.

Die Karte zeigt dieselben groben Umrisse wie die Ortsvorschau – Küsten und
Grenzen, keine Straßen. Liegen alle Punkte dicht beieinander, wird der
Ausschnitt trotzdem nicht enger als etwa zwölf Längengrade gezeichnet, sonst
wäre schlicht nichts zu sehen. Für Straßen führt **Öffnen** zu einer
Kartenanwendung. Wie beim Standort in Nachrichten wird **nichts von fremden
Servern nachgeladen**.

Auch hier gilt: Der Browser gibt den Standort **nur über HTTPS** heraus.

## Die Reiter in der Seitenleiste

Oben in der Seitenleiste stehen fünf Reiter, wie die Filterknöpfe bei
WhatsApp. Sichtbar ist immer genau einer:

| Reiter | Inhalt | Zahl daneben |
|---|---|---|
| **Unterhaltungen** | die Chatliste | ungelesene Nachrichten |
| **Karten** | laufende Standortfreigaben, Zugang zur Live-Karte | aktive Freigaben |
| **Stimmung** | worauf dein Kreis gerade Lust hat | gültige Meldungen |
| **Termine** | alles Anstehende aus allen Unterhaltungen | Anzahl |
| **Zugesagt** | nur die Termine, bei denen du „Bin dabei“ bist | Anzahl |

Der zuletzt gewählte Reiter bleibt am Gerät gespeichert und ist nach dem
Neuladen wieder da. Das sagt nichts über deine Daten aus, sondern nur, worauf
du an diesem Bildschirm zuletzt geschaut hast – deshalb hängt es am Gerät und
nicht am Konto.

Die frühere Begrenzung auf drei Zeilen je Abschnitt ist damit entfallen: Es
steht ohnehin nur eine Liste auf einmal da, und die bekommt die volle Höhe.

## Straßenkarte oder Umrisse

Es gibt zwei Karten im Chat, und der Unterschied ist Absicht:

**Die Umrisskarte** steckt als 102 KB große Datei im Add-on (gemeinfreie
Daten von Natural Earth). Sie zeigt Küsten und Grenzen, keine Straßen, und
**fragt niemanden**. Sie steht in jeder Sprechblase mit Standort und in jeder
Terminkarte im Verlauf.

**Die Straßenkarte** (Leaflet, ebenfalls im Add-on) erscheint nur dort, wo
eine ganze Karte gezeigt wird: in der **Live-Karte** und in der
**Terminansicht** aus der Seitenleiste. Erst dann werden Kacheln von
OpenStreetMap geholt – das ist die einzige Stelle, an der dieser Chat etwas
von einem fremden Server lädt. Beim Start der App passiert das nicht, und in
Sprechblasen auch nicht.

Was OpenStreetMap dabei erfährt: deine IP-Adresse und welchen Ausschnitt du
ansiehst. Der Chat schickt `Referrer-Policy: no-referrer` mit, die Adresse
deines Servers bleibt also außen vor.

**Abschalten:** In den Einstellungen unter *Karten* nimmst du den Haken bei
**Straßenkarte verwenden** weg. Dann bleibt es überall bei den Umrissen und
es geht keine einzige Anfrage nach draußen. Die Einstellung hängt am Konto,
nicht am Gerät – sie gilt also auch auf dem Telefon.

Fehlt die Bibliothek oder kommt sie nicht durch, bleibt die Umrisskarte
stehen und ein Hinweis sagt, warum.

## Stimmung

Über **Setzen** im Abschnitt **Stimmung** sagst du, worauf du gerade Lust
hättest – ein Emoji, ein Satz, eine Geltungsdauer von zwei Stunden bis morgen
und auf Wunsch dein Standort. Andere tippen auf **Ich mach mit**; ein zweiter
Tipp nimmt es zurück.

Sichtbar ist eine Meldung für alle, mit denen du **mindestens eine
Unterhaltung teilst**. Solange es keine gegenseitigen Freundschaften gibt,
ist das die ehrlichste Abgrenzung: Wer nie mit dir geschrieben hat, sieht
deine Stimmung nicht.

Je Person gilt immer nur **eine** Meldung – eine neue ersetzt die alte, sonst
stünde die Pinnwand nach einer Woche voller alter Launen. Abgelaufene
Meldungen verschwinden von selbst.

## Bilder und Dateien

Der Knopf **Medien** unten links öffnet alles, was in deinen Unterhaltungen
geteilt wurde – Bilder als Raster, Dateien als Liste, jeweils mit Absender,
Unterhaltung und Zeitpunkt. Über die Auswahl oben lässt sich auf eine
einzelne Unterhaltung einschränken.

Sichtbar ist nur, was ohnehin sichtbar wäre: Medien aus Unterhaltungen, in
denen du Mitglied bist.

**Videos und Musik** erscheinen mit Abspieler samt Vorschaubild und
Abspielknopf; geladen wird zunächst nur der Anfang, nicht die ganze Datei.
Alles Übrige bleibt ein Anhang zum Herunterladen.

**Emoji:** Der Knopf links neben der Büroklammer öffnet eine Auswahl mit
rund 375 Zeichen in elf Gruppen. Eingefügt wird an der Stelle, an der die
Schreibmarke steht. Auf dem Handy geht natürlich auch die Tastatur.

**Mehrere auf einmal:** Über die Büroklammer lassen sich mehrere Dateien
zugleich auswählen. Sind Bilder dabei, erscheinen sie als **Album** in einer
Sprechblase mit einer Uhrzeit – zwei nebeneinander, bei dreien eines breit
oben und zwei darunter, ab vier gleichmäßig. Jedes Bild bleibt dabei eine
eigene Nachricht und lässt sich einzeln löschen. Der Fortschritt steht
während des Hochladens am unteren Rand.

**Mehrere auf einmal entfernen:** Der Knopf **Auswählen** über der Liste
schaltet den Auswahlmodus ein. Angetippte Kacheln bekommen einen Haken,
**Alle** markiert alles Sichtbare, **Löschen** entfernt die ganze Auswahl auf
einmal. **Fertig** beendet den Modus.

Beim Löschen verschwindet die Datei aus dem Verlauf **und vom Server** – die
Bytes bleiben nicht liegen. Eigene Dateien darf jeder löschen, fremde nur ein
Administrator. Dasselbe gilt, wenn du eine Nachricht mit Anhang löschst: der
Anhang geht mit.

## Antworten und Löschen

* Auf eine Sprechblase tippen blendet **Antworten** und **Löschen** ein.
* Zitate erscheinen als Balken über der Nachricht; ein Tipp darauf springt zum
  Original im Verlauf.
* Gelöschte Nachrichten verschwinden bei allen sofort und hinterlassen den
  Hinweis „Nachricht gelöscht". Administratoren dürfen fremde Nachrichten löschen.

## Technik

* Flask + Flask-SocketIO im `threading`-Modus mit `simple-websocket` – kein
  gevent/eventlet, dadurch keine Kompilierung auf aarch64.
* SQLite unter `/data/chat.db` (WAL), Uploads unter `/data/uploads`.
* Ingress über `ReverseProxied`-Middleware, die **nach** `SocketIO(app)` gewrappt
  wird, damit auch `/socket.io` den Prefix verliert.
* Der eingebaute Werkzeug-Server ist für eine Handvoll Nutzer ausreichend. Bei
  spürbarer Last wäre gunicorn mit gevent-websocket der nächste Schritt.

## Sicherheit und Sicherungen

Die Anmeldung ist gegen Durchprobieren gebremst: Nach **acht Fehlversuchen**
ist ein Konto eine Viertelstunde gesperrt – auch mit richtigem Passwort. Je
Absender greift eine weit höhere Grenze, weil hinter Tunnel und Reverse
Proxy alle dieselbe Adresse haben; sonst sperrte ein Angriff auf ein
einzelnes Konto gleich alle aus. Gebremste Versuche stehen im
Add-on-Protokoll.

Hochgeladene Dateien unter `/data/uploads` sind vom Backup **ausgenommen** –
bei 99 MB je Datei würde jedes Vollbackup sonst schnell unhandlich.
Datenbank, Schlüssel und Profilbilder werden weiterhin gesichert. Wer die
geteilten Dateien mitsichern will, kopiert das Verzeichnis von Hand oder
entfernt `backup_exclude` aus `config.yaml`.

## Grenzen

* Transportverschlüsselung über TLS, **keine** Ende-zu-Ende-Verschlüsselung.
* Keine Sprach- oder Videoanrufe, keine Lesebestätigungen über den
  Ungelesen-Zähler hinaus.
* Gelöschte Nachrichten werden als gelöscht markiert, der Datensatz bleibt in der
  Datenbank (Text und Dateiverweis werden geleert).
