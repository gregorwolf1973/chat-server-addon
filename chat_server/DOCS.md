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
* Beim Öffnen der Seite meldet sich das Gerät **von selbst** an, sobald die
  Erlaubnis einmal erteilt ist. Beim allerersten Mal fragt ein schmaler
  Streifen unten nach – der Browser verlangt für diese Frage eine echte
  Berührung, ein Fenster von selbst wäre stumm abgelehnt.
* Nachträglich geht es unter **Einstellungen → Benachrichtigungen**. Steht dort
  „vom Browser abgelehnt", hilft nur das Schloss neben der Adresszeile.
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

**Nur im Kopf, nicht in der Adresse.** Ein `?token=…` an der Adresse weist der
Server ab. Der Zugriffsprotokollant schreibt jede Anfragezeile mit – das Token
stünde damit im Klartext im Add-on-Log, und Protokolle werden weitergereicht.

**Neues Token:** Unter *Einstellungen → Home Assistant* steht neben *Kopieren*
der Knopf **Neu**. Er erzeugt ein frisches Token; das alte gilt sofort nicht
mehr, jede Automation damit schlägt fehl, bis du dort das neue einträgst. Das
ist der Weg, wenn das alte irgendwo aufgetaucht ist, wo es nicht hingehört –
in einem Protokollauszug, einem Bildschirmfoto, einer Nachricht. Steht das
Token in der Add-on-Option `api_token`, gehört es dorthin und der Knopf ist
ausgeblendet.

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

## Passwort vergessen

Unter dem Anmeldeformular steht **Passwort vergessen?**. Eine Mail verschickt
dieser Chat nicht – stattdessen erfährt der **Administrator** davon:

1. Du gibst deinen Benutzernamen ein und schickst ab
2. Alle Administratoren bekommen eine Push-Nachricht, und der Antrag steht
   unter *Einstellungen → Benutzer verwalten* ganz oben
3. Dort liegt neben dem Namen **Neues Passwort** – der Administrator setzt
   eins und sagt dir, wie es lautet. Damit ist die Bitte erledigt. **Erledigt**
   hakt sie ab, ohne etwas zu ändern

Ob es das Konto gibt oder nicht, **die Antwort ist immer dieselbe**. Sonst
ließe sich hier durchprobieren, welche Benutzernamen vergeben sind. Drei
Bitten je Stunde und Absender, dann ist Schluss.

Am Passwortfeld selbst steht **Zeigen** – falls du dir nicht sicher bist, ob
du dich vertippt hast.

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

## Wie der Chat heißt

In den Einstellungen unter **Name** trägt ein Administrator ein, wie die
Oberfläche heißen soll – voreingestellt „Wosislos". Der Name erscheint in der
Seitenleiste, im Fenstertitel, auf der Anmeldeseite und im Manifest (also auch
unter dem Symbol auf dem Home-Bildschirm). Er gilt für alle und wechselt bei
allen offenen Fenstern sofort, ohne Neuladen. Leeren stellt die Voreinstellung
wieder her.

Das **Add-on** im Home-Assistant-Store heißt davon unabhängig weiter
„Chat Server" – dieser Name steht in `config.yaml` und würde sich beim
Umbenennen wie eine neue Installation verhalten.

## Woran du einen neuen Antrag merkst

Drei Wege, und nur die ersten beiden melden sich von selbst:

1. **Push-Nachricht** an alle aktiven Administratoren: „Neuer Zugangsantrag –
   <Name>". Der einzige Weg, der dich auch bei geschlossener App erreicht.
   Setzt eingeschaltete Benachrichtigungen und HTTPS voraus
2. **Ein kurzer Hinweis** unten im Bild, solange die App offen ist – der
   verschwindet nach ein paar Sekunden wieder
3. **Eine rote Zahl am Zahnrad** unten links. Sie bleibt stehen, bis der
   Antrag beantwortet ist, und ist damit der verlässliche Hinweis. Nur
   Administratoren sehen sie

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

## Farbe der Sprechblasen

In den Einstellungen unter **Sprechblasen** wählst du die Farbe deiner
eigenen Nachrichten. Sie gilt in allen Unterhaltungen und nur für dich.

Die Auswahl ist eine feste Liste – bei freier Farbwahl landet man schnell bei
Tönen, auf denen die eigene Schrift nicht mehr zu lesen ist.

## Töne

### Klingelton

Darunter steht die Auswahl **Klassisch**, **Sanft**, **Perlen**, **Tief** und
**Kleine Folge**. Ein Tipp auf einen Namen spielt ihn gleich vor und merkt ihn
sich. Die Töne entstehen im Browser aus einzelnen Sinusschwingungen – im
Add-on liegt keine Tondatei, es wird also nichts nachgeladen. Eine eigene
Tondatei lässt sich deshalb auch nicht hinterlegen.

### Wann es überhaupt klingelt

In den Einstellungen unter **Töne** wählst du **Alle Töne**, **Nur Anrufe**
oder **Stumm**. Die Einstellung hängt am Konto, gilt also auf allen deinen
Geräten.

Einzelne Unterhaltungen lassen sich zusätzlich stummschalten: in den Angaben
zur Unterhaltung unter *Töne* – für **1 Stunde**, **8 Stunden** oder **für
immer**. In der Liste steht dann ein 🔕 hinter dem Namen. Auch die
Push-Nachrichten bleiben dann aus.

Ein Anruf klingelt auch bei „Nur Anrufe" – aber nicht, wenn genau diese
Unterhaltung stummgeschaltet ist. Stummschaltung gilt immer nur für dich.

Alle Töne werden erzeugt, keiner wird geladen: Das hält das Add-on klein und
klingt überall gleich.

## Anrufe, Videoanrufe und Gruppenrunden

Oben in der Unterhaltung stehen 📞 und 🎥. Ein Tipp startet den Anruf.

Bei allen anderen **klingelt es**: oben im Bild erscheint ein Balken mit
Name, Unterhaltung und den Knöpfen **Annehmen** und **Ablehnen**, dazu ein
Klingelton und – auf dem Telefon – ein Rütteln. Der Balken hängt **nicht** an
der geöffneten Unterhaltung: Du siehst ihn, egal wo du gerade bist, und
*Annehmen* springt in die richtige Unterhaltung. Wer die App gar nicht offen
hat, bekommt zusätzlich eine Push-Nachricht.

Nach 45 Sekunden hört das Klingeln von selbst auf; der Balken bleibt stehen,
solange der Anruf läuft, damit du noch dazukommen kannst.

Welcher Klingelton es ist, steht in den Einstellungen. Der Ton wird erzeugt,
nicht aus einer Datei geladen. Browser lassen Ton erst
zu, nachdem man die Seite einmal angefasst hat – deshalb öffnet der Chat den
Tonkanal schon beim ersten Tippen. Wer die Seite frisch geladen und noch
nichts angefasst hat, sieht den Balken, hört aber nichts.

Es ist immer eine **Runde**, kein Klingeln zu zweit: Wer will, kommt dazu,
wer geht, geht – der Anruf läuft weiter, bis der Letzte auflegt. Schaltet
jemand die Kamera zu, wird für alle ein Videoanruf daraus. Höchstens **sechs**
Personen gleichzeitig.

Im Anruf gibt es Mikrofon an/aus, Kamera an/aus und Auflegen. Ohne Bild zeigt
die Kachel das Profilbild.

**Bild und Ton laufen direkt von Gerät zu Gerät, nie über den Pi.** Der Server
sagt nur, wer mitmacht, und reicht die Aushandlungsdaten weiter – er kann
nichts mithören. Jeder spricht mit jedem einzeln; für eine Familienrunde ist
das genau richtig und spart einen Medienserver. Bei sechs Leuten sendet jeder
allerdings fünfmal sein eigenes Bild, das braucht eine ordentliche
Upload-Leitung.

### Anrufe von unterwegs

Im Heimnetz finden sich die Geräte direkt. Von unterwegs kennt ein Gerät
seine öffentliche Adresse nicht – dafür ist ein **STUN-Server** da. Er
erfährt nur diese Adresse, **nie Bild oder Ton**.

Voreingestellt ist Googles öffentlicher STUN-Server. Wer gar nichts nach
draußen geben will, trägt in den Add-on-Optionen unter `stun_server` ein
`aus` ein – dann funktionieren Anrufe im Heimnetz, aber nicht von unterwegs.

Scheitert die Verbindung auch mit STUN – das kommt in manchen Mobilfunknetzen
vor –, hilft nur ein **TURN-Server**, der die Daten weiterreicht. Einen
brauchbaren kostenlosen gibt es nicht; er muss selbst betrieben werden
(z. B. coturn). Die Zugangsdaten stehen dann unter `turn_server`,
`turn_username` und `turn_password`.

Mikrofon und Kamera gibt der Browser – wie den Standort – nur in einem
sicheren Kontext frei: über HTTPS, also deine externe Adresse.

## Altes automatisch löschen

In den Add-on-Optionen legt `retention_days` fest, nach wie vielen Tagen
**Nachrichten und Anhänge** verschwinden. Voreingestellt ist **0**, also nie
– ein Messenger, der ungefragt Erinnerungen wegwirft, wäre eine Zumutung.

Ist eine Frist gesetzt, sieht der Server alle sechs Stunden nach. In den
Einstellungen steht, wie viele Nachrichten gerade fällig wären, und der
Administrator kann den Lauf sofort auslösen.

Ein Anhang bleibt, solange noch **irgendeine** Nachricht daran hängt – eine
weitergeleitete Datei verschwindet also nicht, weil das Original alt wurde.
Termine, Empfehlungen und Konten bleiben unberührt; es geht nur um den
Verlauf.

## Nachrichten weiterleiten

Ein Tipp auf eine Sprechblase zeigt **Weiterleiten**. Danach wählst du die
Zielunterhaltung; die Nachricht erscheint dort mit dem Hinweis
*↪ Weitergeleitet*.

Der Anhang wird nicht kopiert, sondern derselbe bleibt bestehen – er belegt
also keinen zusätzlichen Platz. Sichtbar wird er dadurch für die Mitglieder
der Zielunterhaltung, was ja der Zweck ist.

Abstimmungen und Einladungen lassen sich **nicht** weiterleiten: Sie gehören
zu ihrer Unterhaltung, samt Stimmen und Zusagen.

## Sprachnachrichten

Rechts im Eingabefeld steht 🎤. **Gedrückt halten** nimmt auf, **Loslassen**
schickt ab – so wie bei WhatsApp. Ein kurzer Ton sagt dir, dass die Aufnahme
läuft, ein zweiter, dass sie abgeschickt ist. Während der Aufnahme laufen
darüber die Sekunden mit; **Verwerfen** wirft sie weg. Nach einer
Viertelstunde endet sie von selbst.

Ein Tipp unter einer halben Sekunde gilt als Verrutscher und sendet nichts.
Wer schon loslässt, bevor das Mikrofon bereit ist, bekommt ebenfalls keine
Aufnahme – die wird dann gar nicht erst begonnen.

In der Unterhaltung erscheint ein schmaler Abspieler mit Knopf, Fortschritt
und Länge – nicht das breite Standardfeld des Browsers, das in jedem Browser
anders aussieht. Startet man eine zweite Aufnahme, hält die erste an.

Aufgenommen wird in Opus (WebM); Safari kann das nicht und bekommt MP4. Die
Länge wird beim Senden mitgeschickt, damit sie in der Blase steht, bevor der
Ton geladen ist.

Das Mikrofon gibt der Browser – wie den Standort – **nur in einem sicheren
Kontext** frei: über HTTPS, also deine externe Adresse, oder lokal über
localhost. Nach der Aufnahme wird es sofort wieder freigegeben.

## Die Heftklammer

Im Eingabefeld stehen zwei Knöpfe: 🙂 für Emojis und 📎 für alles, was sich an
eine Unterhaltung hängen lässt:

* **Datei oder Bild**
* **Standort senden** – einmalig, als Nachricht
* **Standort live teilen** – laufend, mit Ablaufzeit
* **Abstimmung**
* **Einladung**

Ein Tipp daneben oder Esc schließt das Menü. Emoji-Auswahl und Menü sind nie
gleichzeitig offen.

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
nicht. Wer zu einer Feier lädt, entscheidet auch, ob sie stattfindet.

Ein abgesagter Termin **verschwindet aus der Unterhaltung**, aus den
Terminlisten und aus der Suche. Damit ist Absagen **endgültig**: Es bleibt
keine Karte mehr stehen, auf die man tippen könnte, um es zurückzunehmen –
wer sich anders entscheidet, lädt neu ein. Die Nachfrage vor dem Absagen sagt
das ausdrücklich.

Die Nachricht selbst bleibt in der Datenbank, denn die Zu- und Absagen hängen
daran; sie wird nur nicht mehr ausgeliefert.

Der Administrator kann fremde Termine also **ändern, aber nicht absagen**.
Wird ein Termin zum Problem, bleibt ihm die Unterhaltung selbst: Wer sie
löscht, nimmt die Termine darin mit.

## Ein Termin ohne Unterhaltung

Unter **Termine** legt der Knopf **Termin ohne Unterhaltung** eine Einladung
an, die an keiner Gruppe hängt. Wer sie sieht, entscheidest du:

- **Ausgewählte Freunde** – eine Reihe mit deinen bestätigten Freunden, jeder
  einzeln an- und abwählbar. Mindestens eine Person muss dabei sein. Nur
  bestätigte Freunde lassen sich auswählen; der Server weist alles andere ab
- **Alle im Umkreis** – 1, 5, 10 oder 25 km um den Ort der Einladung. Mehr als
  25 km gibt es nicht, das wäre keine Nachbarschaft mehr. Dafür braucht der
  Termin einen Ort auf der Karte

Nachträglich lässt sich die Gästeliste ändern – aber nur von dem, der
eingeladen hat. Ein Administrator darf einen Termin berichtigen, nicht
umbesetzen. Absagen bleibt ohnehin beim Gastgeber.

**Beim Umkreis muss der Server wissen, wo du bist**, sonst kann er die
Entfernung nicht rechnen. Zwei Wege führen dahin: du teilst ohnehin gerade
deinen Standort, oder die Oberfläche schickt die Koordinaten mit, sobald du
sie einmal für den Umkreisfilter der Karte geholt hast. Gespeichert wird der
Wert dabei nicht – er gilt nur für diese eine Antwort. Wer weder das eine noch
das andere hat, sieht solche Einladungen nicht.

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

### Nur was in der Nähe ist

Eine zweite Reihe schränkt nach **Entfernung** ein: 5 km, 25 km, 100 km oder
*überall*. Einladungen und Empfehlungen weiter weg fallen aus der Karte und
aus den Listen darunter.

Dafür wird einmal der eigene Standort gebraucht; die Reihe beginnt deshalb mit
**📍 Meinen Standort verwenden**. Danach rechnet der **Browser** die Luftlinie
zu jedem Punkt – der Standort wird dabei nicht gesendet und nicht gespeichert.
Ohne Standort bleibt es bei *überall*.

Termine ohne Zeitpunkt erscheinen nur unter **Alles**; bei ihnen lässt sich
nicht sagen, ob sie in einen Zeitraum fallen.

Im Abschnitt **Termine** der Seitenleiste stehen alle anstehenden Termine aus
allen Unterhaltungen, der nächste zuerst. Darüber lässt sich einschränken:
**Alle**, **Zugesagt** (wo du „Bin dabei“ bist) und **Offen** (was noch auf
deine Antwort wartet). Jeder Knopf trägt seine Anzahl. Das ist nötig, weil eine Einladung
im Verlauf sonst nach oben rutscht und aus dem Blick gerät. Ist der Zeitpunkt vorbei,
fällt ein Termin heraus – die Liste zeigt, was noch kommt, nicht was war.

Wer die Unterhaltung gerade nicht offen hat, bekommt eine Benachrichtigung
über die Einladung.

## Live-Standort und der Abschnitt „Karten“

Über **Teilen** im Abschnitt **Karten** gibst du deinen Standort für eine
gewählte Dauer frei: 15 Minuten, 1 Stunde, 3 Stunden oder 8 Stunden. Länger
als acht Stunden geht nicht, und die Freigabe endet von selbst.

Wer dich sehen darf, wählst du beim Teilen:

* **Eine Unterhaltung** – ihre Mitglieder, wie bisher.
* **Alle Freunde** – dein bestätigter Freundeskreis, auch ohne gemeinsame
  Unterhaltung.
* **In der Nähe** – alle im Umkreis von 1 bis höchstens 25 km. Sehen kann
  dich dabei nur, wer **selbst gerade seinen Standort teilt**; sonst wüsste
  der Server ja nicht, wo die Person ist – und das soll er nur dann wissen.
  Die Entfernung wird bei jedem Abruf neu gerechnet, die Freigabe wandert
  also mit. Wer eine Gruppe verlässt,
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
| **Tipps** | Empfehlungen aus deinem Kreis | Anzahl |

Die Zahl an einem Reiter zeigt, **was seit deinem letzten Blick dazugekommen
ist** – nicht, wie viel es insgesamt gibt. Eine „12", die sich nie ändert,
sagt schließlich nichts. Öffnest du den Reiter, ist sie weg. Eigene Beiträge
zählen nie als neu.

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

## Empfehlungen

Der Reiter **Tipps** sammelt, was gut war: Film, Kino, Restaurant, Bar, Café,
Hotel, Ausflug, Musik, Buch oder Sonstiges – mit Namen, ein bis fünf Sternen,
Ort, Text und Bild. Den Ort kannst du wie bei einer Einladung auf der Karte
antippen.

Jeder schreibt **seine eigene** Empfehlung. Es gibt bewusst keine gemeinsame
Note, die sich mitteln ließe: Ein Tipp von jemandem, den du kennst, ist mehr
wert als ein Durchschnitt aus tausend Sternen.

**Merken** heißt „will ich auch" – der Verfasser sieht, wie viele es sich
vorgemerkt haben. Ändern und löschen darf nur, wer die Empfehlung geschrieben
hat (und der Administrator kann löschen).

Ein Tipp auf die Empfehlung öffnet sie in ganzer Größe – mit Bild, Text, wer
sie sich gemerkt hat und, wenn ein Ort hinterlegt ist, einer **Straßenkarte**.
Über **In Karten öffnen** geht es zur Kartenanwendung. Welche das ist, steht
unter *Einstellungen → Karten*: voreingestellt die **Standard-App des Geräts**
(unter Android fragt das Telefon selbst, welche es sein soll), wahlweise fest
Google Maps, Apple Karten oder OpenStreetMap. Auf dem Rechner gibt es keine
App zum Aufrufen – dort führt die Voreinstellung zu Google Maps im Browser.

**Punkt, nicht Suche.** Der Verweis nennt die Koordinate ausdrücklich als Ort
(`q=loc:` bei Google, eine Beschriftung beim `geo:`-Verweis unter Android).
Das ist kein Schönheitsfehler: Eine bloße Suche nach „49.0094,8.4044" beant­
worten beide mit dem **nächstgelegenen bekannten Ort** – die Nadel stünde dann
auf dem Lokal nebenan statt auf dem Punkt, den jemand gesetzt hat.

Empfehlungen mit Ort stehen außerdem auf der **Live-Karte**, mit einem ⭐ als
Nadel. Ein Tipp darauf öffnet sie. Über der Karte lassen sie sich ausblenden,
falls es zu voll wird.

Sichtbar sind Empfehlungen für deinen Kreis – Freunde und alle, mit denen du
eine Unterhaltung teilst. Oben lässt sich nach Art filtern; angeboten werden
nur Arten, die auch vorkommen.

### In meiner Nähe

Ein Tipp auf **📍 In meiner Nähe** bestimmt einmal deinen Standort. Danach
steht an jeder Empfehlung mit Ort die Luftlinie, und du kannst auf
**5 km**, **25 km**, **100 km** oder **Überall** einschränken – innerhalb
eines Umkreises nach Entfernung sortiert, die nächste zuerst. Mit ↻ bestimmst
du den Standort neu.

Empfehlungen **ohne** Ortsangabe fallen dabei heraus – bei ihnen lässt sich
nicht sagen, ob sie in der Nähe sind. Wie viele das sind, steht unter der
Liste; stillschweigend verschwindet nichts.

**Dein Standort bleibt dabei im Gerät.** Die Empfehlungen bringen ihre
Koordinaten ohnehin mit, die Entfernung wird also im Browser gerechnet – der
Server erfährt nie, wo du gerade bist. Nachgemessen: während des Filterns
geht keine einzige Anfrage hinaus.

Wird ein Konto gelöscht, verschwinden seine Empfehlungen mit.

## Geburtstage

Bei der Registrierung wird nach dem **Geburtstag** gefragt – freiwillig. Wer
schon ein Konto hat, trägt ihn in den Einstellungen nach; dort lässt er sich
auch wieder löschen.

Angegebene Geburtstage erscheinen unter **Termine** zwischen den Einladungen,
nach Datum einsortiert: 🎂 mit Name und dem Alter, das erreicht wird. Am Tag
selbst steht dort „Heute!". Ein Tipp öffnet die Unterhaltung mit der Person –
und legt sie an, falls es noch keine gibt.

Sichtbar sind sie für deinen Kreis, also Freunde und alle, mit denen du eine
Unterhaltung teilst. Unter den engeren Filtern (*Zugesagt*, *Offen*) tauchen
Geburtstage nicht auf: Es gibt bei ihnen nichts zuzusagen.

Der 29. Februar wird in Jahren ohne Schalttag am 1. März gezählt.

**Abschalten:** In den Einstellungen unter *Geburtstag* nimmst du den Haken
bei „Geburtstage anderer unter „Termine" zeigen" weg – dann verschwinden sie
aus deiner Liste. Dein eigener Geburtstag bleibt dabei gespeichert und für
andere sichtbar; die Einstellung betrifft nur, was **du** siehst.

## Einwilligung bei der Registrierung

Ein Antrag lässt sich nur abschicken, wenn das Kästchen zur **Speicherung der
Daten** gesetzt ist. Darüber steht aufklappbar, was gespeichert wird, wer es
sieht und dass man die Löschung verlangen kann. Der Zeitpunkt der Einwilligung
wird zum Konto vermerkt.

Das ist eine sachliche Beschreibung dessen, was diese Software speichert –
keine fertige Datenschutzerklärung. Ob und was du darüber hinaus brauchst,
hängt davon ab, wen du auf deinen Server lässt.

## Freunde

Unten links öffnet **Freunde** die Liste aller Konten auf diesem Server. Eine
Anfrage wird erst durch die **Zusage der Gegenseite** zur Freundschaft – wer
nicht will, lehnt ab, und beide Seiten können sie jederzeit wieder beenden.
Wartet eine Anfrage auf dich, färbt sich der Knopf.

**Wozu das gut ist:** Stimmung und Empfehlungen sind für deinen *Kreis*
sichtbar. Dazu gehören

* alle, mit denen du **mindestens eine Unterhaltung teilst**, und
* alle, mit denen du **befreundet** bist.

Die Freundschaft reicht also über die Unterhaltungen hinaus – so erreicht
eine Empfehlung auch jemanden, mit dem du noch nie geschrieben hast.
Umgekehrt bleibt die Familie im Kreis, ohne dass sich alle erst gegenseitig
bestätigen müssen.

Wird ein Konto gelöscht, verschwinden seine Freundschaften mit.

## Stimmung

Über **Setzen** im Abschnitt **Stimmung** sagst du, worauf du gerade Lust
hättest – ein Emoji, ein Satz, eine Geltungsdauer von zwei Stunden bis morgen
und auf Wunsch dein Standort.

Beim Emoji steht oben eine Reihe mit den **zuletzt genommenen**; der Knopf **＋**
daneben öffnet die ganze Sammlung mit rund 375 Zeichen in elf Gruppen. Was du
wählst, rutscht in der Reihe nach vorn – die Favoriten merkt sich der Browser
dieses Geräts, nicht der Server. Andere tippen auf **Ich mach mit**; ein zweiter
Tipp nimmt es zurück.

Sichtbar ist eine Meldung für deinen Kreis – alle, mit denen du eine
Unterhaltung teilst, und alle, mit denen du befreundet bist. Wer weder das
eine noch das andere ist, sieht deine Stimmung nicht.

Je Person gilt immer nur **eine** Meldung – eine neue ersetzt die alte, sonst
stünde die Pinnwand nach einer Woche voller alter Launen. Abgelaufene
Meldungen verschwinden von selbst.

Ein Tipp auf den **Namen** öffnet die Unterhaltung mit dieser Person; gibt es
noch keine, wird sie angelegt. Genau das ist ja meist der nächste Schritt,
wenn jemand schreibt, worauf er Lust hätte.

## Am Telefon

Alle Schaltflächen sind auf Berührungsgeräten mindestens **44 Pixel** hoch –
darunter trifft ein Finger nicht mehr verlässlich. Das gilt nur dort: mit der
Maus bleibt die Oberfläche kompakt.

**Dialoge füllen den ganzen Bildschirm.** Ein 400 Pixel breites Fenster
mitten auf einem schmalen Display lässt ringsum Luft und innen zu wenig Platz;
auf dem Telefon nimmt ein Dialog deshalb die ganze Fläche, wie eine eigene
Seite. Die Knopfreihe bleibt dabei unten stehen. Eingabefelder sind 16 Pixel
groß – bei kleinerer Schrift zoomt iOS beim Antippen hinein und der Rest der
Seite verrutscht.

**Beim ersten Öffnen** fragt ein Streifen einmal nach allen Erlaubnissen
zusammen: Benachrichtigungen, Mikrofon, Kamera, Standort. Von selbst geht das
nicht – Browser verlangen für jede dieser Fragen eine Berührung, und ein
Fenster, das ungefragt aufspringt, gilt als abgelehnt. Wer wegtippt, wird
nicht wieder gefragt; einschalten geht später in den Einstellungen.

**Im Querformat** rücken die Knöpfe eines Anrufs über das Videobild statt
darunter: bei liegendem Telefon bleibt sonst nicht genug Höhe, und die Kacheln
schoben die Leiste aus dem Bild.

**Wenn die Tastatur aufgeht**, richtet sich die Höhe des Fensters nach dem,
was wirklich zu sehen ist – nicht nach `100dvh`, das dabei unverändert bleibt.
Sonst schöbe der Browser die ganze Seite nach oben, um das Schreibfeld zu
zeigen, und nähme den Kopf mit Name, Anruf und Medien mit aus dem Bild. So
bleibt der Kopf oben stehen, das Schreibfeld sitzt über der Tastatur, und die
letzte Nachricht bleibt sichtbar – auch dann, wenn Bilder erst nachträglich
geladen werden und den Verlauf höher machen.

Zwei Anpassungen fallen auf:

* Auf dem Telefon ist der **Emoji-Knopf ausgeblendet**. Die Tastatur bringt
  ihre eigenen Emojis mit, und der Platz gehört dem Textfeld.
* Unter 350 Pixeln Breite werden **Beschriftungen zu Zeichen** – „Medien"
  wird 🖼, „Senden" wird ➤. Der Name steht weiter als Titel am Knopf.

Die Reiterleiste braucht mit fünf Einträgen zwei Zeilen (rund 100 Pixel). Das
ist der Preis dafür, dass jeder Reiter mit dem Finger zu treffen ist und
keiner außerhalb des Bildes liegt.

## Aussehen

In den Einstellungen unter **Aussehen** wählst du **Wie das Gerät**, **Hell**
oder **Dunkel**. Die Wahl bleibt am Gerät gespeichert – sie sagt nichts über
deine Daten aus, sondern nur, wie hell dein Bildschirm gerade sein soll.
„Wie das Gerät" folgt der Einstellung von Telefon oder Rechner.

Die Helligkeit wird schon gesetzt, bevor die Seite gezeichnet wird; sonst
blitzte beim Laden kurz die falsche auf.

## Hintergrundmuster

In den Angaben zur Unterhaltung (Tipp auf das Bild oben) lässt sich ein
**Muster** wählen: Punkte, Karo, Wellen, Kreuze, Blätter oder Kritzel – oder
keins. Es gilt **nur für dich**; andere sehen ihr eigenes.

Es ist ausdrücklich **kein Foto**, sondern ein gezeichnetes Muster – so wie
bei WhatsApp. Es liegt still im Hintergrund, nimmt seine Farbe aus dem
gewählten Aussehen und **wandert beim Blättern nicht mit**: Es sitzt auf der
Unterhaltung, nicht auf der Liste der Nachrichten, die scrollt.

Auf dem Pi liegt dafür keine einzige Datei – das Muster wird im Browser
gezeichnet.

Die frühere **Farbeinstellung je Unterhaltung ist entfallen** – das Muster
tritt an ihre Stelle.

## Bilder und Dateien

Der Knopf **Medien** oben in der Unterhaltung öffnet alles, was geteilt
wurde – Bilder als Raster, Dateien als Liste, jeweils mit Absender,
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

## Durch Bilder und Videos wischen

Ein Tipp auf ein Bild oder Video im Verlauf öffnet es **bildschirmfüllend**.
Von dort geht es durch alle Bilder und Videos derselben Unterhaltung:

- **Wischen nach links oder rechts** blättert weiter, mit der Tastatur die
  Pfeiltasten, mit der Maus die Pfeile links und rechts
- **Wischen nach unten**, ein Tipp auf ✕ oder `Esc` schließt wieder
- Unten läuft eine **Zeitleiste** mit allen Bildern und Videos, ältestes
  zuerst – so, wie es passiert ist. Ein Tipp darauf springt hin, das aktuelle
  Stück ist hervorgehoben und rückt von selbst in den sichtbaren Bereich

Oben stehen Absender, Datum und die Stelle in der Reihe (*„3 / 12"*). Videos
laufen von selbst und **halten an, sobald du weiterwischst** – sonst hörte man
drei Filme gleichzeitig.

## Löschen von Anhängen

Beim Löschen verschwindet die Datei aus dem Verlauf **und vom Server** – die
Bytes bleiben nicht liegen. Eigene Dateien darf jeder löschen, fremde nur ein
Administrator. Dasselbe gilt, wenn du eine Nachricht mit Anhang löschst: der
Anhang geht mit.

## Suchen und springen

Der Knopf **🔍** oben in der Unterhaltung öffnet die Suche. Gesucht wird ab
zwei Zeichen, im Text **und in Dateinamen**; Groß- und Kleinschreibung ist
egal. Mit dem Haken **Alle Unterhaltungen** geht es über alles, was du sehen
darfst – fremde Unterhaltungen bleiben außen vor, auch für den Administrator.

Die Treffer treten an die Stelle des Verlaufs; Kopf und Suchfeld bleiben
sichtbar, auch wenn nichts gefunden wurde – man will ja gleich etwas anderes
eintippen. Die Fundstelle ist hervorgehoben. Ein
Tipp springt hin: die Nachricht rückt in die Mitte, mit dreißig davor und
dreißig danach, und leuchtet zwei Sekunden lang auf. Gelöschte Nachrichten
tauchen in der Suche nicht auf.

Rechts unten im Verlauf stehen zwei Pfeile:

- **↓** springt ans Ende. Er erscheint nur, wenn du nicht ohnehin unten bist
- **↑** springt zum Anfang des vorigen Tages. Ist nichts Älteres geladen, holt
  er es erst nach

Wer einfach nach oben blättert, bekommt ältere Nachrichten ebenfalls
nachgeladen – fünfzig auf einmal, und das Bild bleibt dabei stehen.

## Galerie: Bilder über die Unterhaltung hinaus

Was du in eine Unterhaltung schickst, sehen deren Mitglieder – mehr nicht. Wer
ein Bild oder einen Film darüber hinaus zeigen will, gibt ihn frei: unter
**Medien** trägt jede eigene Kachel oben links ein Zeichen, das den Stand
verrät.

| Zeichen | Bedeutung |
| --- | --- |
| 🔒 | nicht freigegeben – nur in der Unterhaltung sichtbar |
| 👥 | für deine bestätigten Freunde |
| 🌍 | für alle, die ein Konto haben |

Ein Tipp darauf öffnet die Auswahl, dort lässt sich auch eine
Bildunterschrift setzen. Dasselbe Zeichen steht in der eigenen Galerie an
jeder Kachel – auch von dort aus lässt sich die Freigabe ändern. Zurücknehmen
geht jederzeit; die Datei selbst bleibt, wo sie ist, und verschwindet nicht
aus der Unterhaltung.

**iPhone-Fotos:** HEIC schreibt der Chat schon beim Hochladen in ein JPEG um –
auf dem Gerät, das es aufgenommen hat, denn nur dort kann der Browser das
Format überhaupt lesen. Die Größe bleibt dabei erhalten, nur das Format
wechselt. Kann ein Browser HEIC nicht lesen, bleibt die Datei, wie sie ist.

**Formate:** Freigeben lassen sich Bilder als JPEG, PNG, GIF, WebP, AVIF, HEIC
und HEIF sowie Filme als MP4, WebM, Ogg und QuickTime. Was der Chat nicht
kennt, liegt als gewöhnlicher Anhang da und lässt sich nicht in die Galerie
legen – die Meldung sagt das dann auch.

**Hingelangen:** In einer Unterhaltung mit *einer* Person steht oben rechts
neben dem Namen **🖼 Galerie**. In einer Gruppe nicht – dort wäre nicht klar,
wessen Bilder gemeint sind. Zur **eigenen** Galerie führt der Knopf *Galerie*
unten links neben *Freunde*.

### Ohne Umweg hineinlegen

In der eigenen Galerie legt **＋ Bild hinzufügen** ein Bild oder einen Film
direkt hinein: Datei wählen, Unterschrift, Freigabe – fertig. Es landet in
**keiner** Unterhaltung; niemand bekommt es geschickt.

Eine Freigabe **hält die Datei fest**. Löschst du die Nachricht, mit der ein
Bild einmal kam, bleibt es in der Galerie; auch die Frist für alte Nachrichten
räumt es nicht weg. Erst wenn du die Freigabe zurücknimmst, ist es wieder ein
gewöhnlicher Anhang – und wenn dann nichts mehr daran hängt, verschwindet es
ganz. Wer es sofort loswerden will, löscht es unter **Medien**; das nimmt die
Freigabe mit.

### Herzen und Kommentare

Unter jedem Bild stehen zwei Zahlen. Sie bedeuten Verschiedenes:

- **❤️ Herzen** sieht **jeder**, der das Bild sehen darf. Ein Tipp setzt eines,
  ein zweiter nimmt es zurück
- **💬 Kommentare** sind ein **Zwiegespräch**. Was du schreibst, lesen nur du
  und die Person, der das Bild gehört – kein anderer Besucher, auch nicht mit
  der richtigen Kennung in der Adresse. Auch die *Zahl* zeigt dir nur deinen
  eigenen Faden; sonst wäre schon sie eine Auskunft darüber, wer sonst noch
  geschrieben hat

Wem das Bild gehört, sieht die Fäden getrennt nach Person und kann in jedem
einzeln antworten. Den eigenen Kommentar darf jeder löschen, einen fremden
niemand – auch nicht, wem das Bild gehört.

**Löschen:** Das ✕ an einer eigenen Kachel entfernt Bild oder Film
**endgültig** – vom Server und damit auch aus jeder Unterhaltung, in der es
steht. Herzen und Kommentare gehen mit. Das ist etwas anderes als die Freigabe
zurückzunehmen: dabei bleibt die Datei, sie steht nur nicht mehr in der
Galerie. Fremde Bilder kann niemand löschen.

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

**Was der Browser darf:** Jede Seite bringt eine Inhaltsrichtlinie mit. Skripte
laufen nur aus dem Add-on selbst; das eine Skript in der Seite trägt eine
Kennung, die bei jedem Aufruf wechselt. Bilder kommen von hier – einzige
Ausnahme sind die Kartenkacheln von OpenStreetMap. Sollte je ein fremder Text
als HTML durchrutschen, kann er damit weder ein Skript starten noch etwas
nachladen.

**Der Datenstrom** (Socket.IO) nimmt nur Verbindungen an, deren Herkunft zur
Adresse passt, unter der die Seite läuft. Nötig, weil die Oberfläche unter
zwei Adressen zugleich erreichbar ist – über den Ingress und über die externe
Adresse – und keine davon dem Add-on vorher bekannt ist; die übliche
Einschränkung auf feste Ursprünge scheidet damit aus. `SameSite=Lax` hält
fremde Seiten ohnehin schon vom Cookie fern, dies ist der zweite Riegel.

**Woher eine Anfrage kommt**, lässt sich nur begrenzt feststellen:
`X-Forwarded-For` schickt der Client selbst mit und kann dort schreiben, was er
will. Hinter Cloudflare zählt deshalb `CF-Connecting-IP` – das ersetzt
Cloudflare, egal was der Client behauptet. Wo es fehlt, ist die Adresse nur
ein Anhaltspunkt; keine Bremse hängt allein daran. Die Anmeldung zählt
zusätzlich je Konto, die Registrierung zusätzlich als Gesamtzahl: mehr als
**20 unbeantwortete Anträge** nimmt der Server nicht an, bis ein Administrator
aufgeräumt hat.

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
