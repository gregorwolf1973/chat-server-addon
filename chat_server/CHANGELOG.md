# Änderungsverlauf

## 0.34.0

- **Nachrichten und Anhaenge nach x Tagen loeschen**, ueber die neue Option
  `retention_days`. Voreingestellt 0, also nie. Der Administrator kann den
  Lauf auch sofort ausloesen
- **Standort teilen an alle Freunde** oder **an alle in der Naehe** (1 bis
  25 km), zusaetzlich zur Freigabe an eine Unterhaltung
- Beim Umkreis sieht einen nur, wer selbst gerade teilt - sonst wuesste der
  Server nicht, wo die Person ist

## 0.33.0

- **Die Zahlen an den Reitern zeigen nur noch Neues** - was seit dem letzten
  Blick dazugekommen ist. Beim Oeffnen des Reiters verschwinden sie; eigene
  Beitraege zaehlen nie
- **Farbe der eigenen Sprechblasen** in den Einstellungen, gueltig in allen
  Unterhaltungen
- Eine Standortfreigabe merkt sich, wann sie begonnen hat - ein Ping machte
  sie sonst immer wieder zu etwas Neuem

## 0.32.0

- **Sprachnachricht auf Knopfdruck**: gedrueckt halten nimmt auf, Loslassen
  schickt ab. Ein kurzer Ton meldet den Beginn, ein zweiter den Versand
- **Toene** in den Einstellungen: alle, nur Anrufe oder stumm - am Konto,
  also auf allen Geraeten
- **Stummschaltung je Unterhaltung** fuer 1 Stunde, 8 Stunden oder fuer
  immer, mit 🔕 in der Liste. Auch Push-Nachrichten bleiben dann aus
- Klaenge fuer neue Nachrichten und Ereignisse, alle erzeugt statt geladen

## 0.31.0

- **Abgelaufene Termine verschwinden.** Bisher blieben sie zwoelf Stunden
  nach Beginn stehen; jetzt zeigt die Liste nur noch, was kommt
- **Nachrichten weiterleiten** an eine andere Person oder Gruppe, mit dem
  Hinweis *Weitergeleitet*. Abstimmungen und Einladungen nicht - sie gehoeren
  zu ihrer Unterhaltung
- Von einem Termin oder einer Empfehlung, die man **auf der Live-Karte**
  geoeffnet hat, geht es mit *Zur Karte* wieder zurueck

## 0.30.0

- **Geburtstag** bei der Registrierung (freiwillig) und nachtraeglich in den
  Einstellungen. Angegebene Geburtstage stehen unter **Termine** zwischen den
  Einladungen, mit Alter und "Heute!" am Tag selbst
- Ein Tipp darauf oeffnet die Unterhaltung mit der Person - und legt sie an,
  falls es noch keine gibt
- **Einwilligung zur Speicherung** ist beim Antrag Pflicht, mit aufklappbarer
  Auskunft darueber, was gespeichert wird und wer es sieht. Der Zeitpunkt
  wird zum Konto vermerkt
- Das Kaestchen war auf dem Telefon 13 Pixel breit: als Flex-Element
  schrumpfte es auf seine natuerliche Groesse zurueck, wogegen selbst eine
  Breite mit `!important` nichts ausrichtete
- "1 Zusagen" heisst jetzt "1 Zusage"

## 0.29.0

- **Muster statt Foto** als Hintergrund: Punkte, Karo, Wellen, Kreuze,
  Blaetter oder Kritzel. Ein Foto hinter dem Text war unruhig
- Das Muster **bleibt beim Blaettern stehen** - es sitzt auf der
  Unterhaltung, nicht auf der scrollenden Nachrichtenliste
- Es nimmt seine Farbe aus dem Aussehen und wird im Browser gezeichnet; auf
  dem Pi liegt dafuer keine Datei mehr

## 0.28.1

- **Bedienung am Telefon**: Schaltflaechen waren 13 bis 32 Pixel hoch, ein
  Finger trifft verlaesslich erst ab 44. Auf Beruehrungsgeraeten sind jetzt
  alle Bedienelemente mindestens 44 Pixel; mit der Maus bleibt es kompakt
- Das Haekchen in den Einstellungen war **13 x 13 Pixel** gross
- Der **Emoji-Knopf** ist auf dem Telefon ausgeblendet - die Tastatur bringt
  eigene mit, und das Textfeld gewinnt dadurch die Haelfte an Platz
- Unter 350 Pixeln Breite werden Beschriftungen zu Zeichen, damit die
  Kopfzeile nicht ueber den Rand laeuft
- Die Zoomknoepfe der Karte und die "Oeffnen"-Verweise waren 30 bzw. 20 Pixel

## 0.28.0

- **Empfehlungen nach Entfernung filtern**: 5 km, 25 km, 100 km oder Ueberall,
  innerhalb des Umkreises nach Naehe sortiert. An jeder Empfehlung mit Ort
  steht die Luftlinie
- Gerechnet wird im Browser - **der Standort verlaesst das Geraet nicht**
- Empfehlungen ohne Ortsangabe fallen beim Umkreis heraus; wie viele es sind,
  steht unter der Liste

## 0.27.1

- **Beschreibungsfelder in den Dialogen waren weiss und zu klein.** In der
  Regel fuer Eingabefelder stand `input` und `select`, aber kein `textarea` -
  sie bekamen deshalb gar keine Gestaltung. Im dunklen Aussehen hiess das:
  fast weisse Schrift auf weissem Grund
- Jetzt gleicher Grund und gleiche Breite wie die einzeiligen Felder,
  96 statt 66 Pixel hoch und in der Hoehe ziehbar

## 0.27.0

- **Hell und Dunkel**: in den Einstellungen unter *Aussehen* waehlbar, dazu
  *Wie das Geraet*. Die Wahl wird gesetzt, bevor die Seite gezeichnet wird -
  sonst blitzte kurz die falsche Helligkeit auf
- **Hintergrundbild je Unterhaltung**, nur fuer einen selbst. Vor dem
  Hochladen auf 1440 Pixel verkleinert; ein Schleier darueber haelt den Text
  lesbar
- Die **Farbeinstellung je Unterhaltung ist entfallen** - das Hintergrundbild
  tritt an ihre Stelle
- Verstreute Festfarben im Stilblatt haben Namen bekommen; ohne sie liesse
  sich kein helles Aussehen bauen

## 0.26.2

- **Von einer Empfehlung kam man nirgends auf eine Karte.** Die Ortseingabe
  gab es, die Ausgabe fehlte. Ein Tipp auf die Empfehlung oeffnet sie jetzt in
  ganzer Groesse - mit Bild, Text, wer sie sich gemerkt hat und einer
  Strassenkarte
- Empfehlungen mit Ort stehen auch auf der **Live-Karte**, mit ⭐ als Nadel und
  einem Schalter zum Ausblenden
- Der **Medien-Knopf unten links** ist entfallen. Der in der Kopfzeile oeffnet
  denselben Dialog, und dort steht *Alle Unterhaltungen* zur Auswahl

## 0.26.1

- Der Reiter **Zugesagt** ist weg. Stattdessen filtert die **Terminliste**
  selbst: *Alle*, *Zugesagt* und *Offen*, jeweils mit Anzahl. *Offen* zeigt,
  was noch auf eine Antwort wartet

## 0.26.0

- **Empfehlungen** im neuen Reiter *Tipps*: Film, Kino, Restaurant, Bar,
  Café, Hotel, Ausflug, Musik, Buch - mit Namen, ein bis fuenf Sternen, Ort
  (auf der Karte antippbar), Text und Bild
- **Merken** heisst „will ich auch"; der Verfasser sieht, wie viele es sich
  vorgemerkt haben
- Sichtbar im eigenen Kreis - Freunde und alle, mit denen man eine
  Unterhaltung teilt. Filter nach Art, aber nur fuer Arten, die vorkommen
- Aendern darf nur der Verfasser; ein geloeschtes Konto nimmt seine
  Empfehlungen mit

## 0.25.1

- **Es klingelt jetzt.** Bei einem Anruf gibt es einen Ton und auf dem Telefon
  ein Ruetteln - vorher blieb es still, und ein lautloser Anruf ist leicht zu
  uebersehen
- Der Anrufbalken haengt nicht mehr an der geoeffneten Unterhaltung. Er
  erscheint oben im Bild, egal wo man gerade ist, und *Annehmen* springt in
  die richtige Unterhaltung
- Nach 45 Sekunden hoert das Laeuten von selbst auf; der Balken bleibt, damit
  man noch dazukommen kann

## 0.25.0

- **Freunde**, gegenseitig: eine Anfrage wird erst durch die Zusage der
  Gegenseite zur Freundschaft. Ablehnen, zuruecknehmen und beenden gehen
  jederzeit; wartet eine Anfrage, faerbt sich der Knopf unten links
- Der **Kreis** umfasst jetzt Freunde *und* alle, mit denen man eine
  Unterhaltung teilt. Eine Empfehlung erreicht damit auch jemanden, mit dem
  man noch nie geschrieben hat - und die Familie bleibt drin, ohne dass sich
  alle erst bestaetigen muessen
- Ein geloeschtes Konto nimmt seine Freundschaften mit

## 0.24.3

- Basis-Image von Alpine 3.19 auf 3.22 gehoben. 3.19 bekommt keine
  Sicherheitsaktualisierungen mehr

## 0.24.2

- Die **Medienuebersicht und die Live-Karte** waren auf 400 Pixel gequetscht,
  obwohl sie als breite Dialoge gedacht sind. `max-width` kann nur
  verkleinern; gegen die Grundbreite von 400 Pixeln richtete es nichts aus.
  Jetzt 760 Pixel, auf dem Telefon volle Breite

## 0.24.1

- **Das Menue hinter der Heftklammer liess sich nicht schliessen.** Im
  Stilblatt fehlte eine Regel fuer `[hidden]`; jedes eigene `display: flex`
  hat das Attribut ueberstimmt, weil eine Regel der Seite gegen die
  Voreinstellung des Browsers gewinnt
- Dasselbe betraf die Aufnahmeleiste, den Klingelbalken, die Antwortleiste -
  und das Anruffenster, das bildschirmfuellend ueber allem gelegen haette
- Eine Pruefung wacht jetzt darueber, dass die Regel bleibt

## 0.24.0

- **Anrufe und Videoanrufe** ueber 📞 und 🎥 in der Unterhaltung, auch als
  **Gruppenrunde** mit bis zu sechs Personen
- Bild und Ton laufen **direkt von Geraet zu Geraet, nie ueber den Pi**. Der
  Server sagt nur, wer mitmacht, und reicht die Aushandlung weiter
- Klingelbalken mit *Teilnehmen* und *Ablehnen*; wer die App nicht offen hat,
  bekommt eine Push-Nachricht. Mikrofon, Kamera und Auflegen im Anruf
- Neue Optionen `stun_server`, `turn_server`, `turn_username`,
  `turn_password`. Voreingestellt ist Googles STUN-Server; `aus` schaltet ihn
  ab, dann sind Anrufe nur im Heimnetz moeglich
- Wer eine Person zu einer Gruppe hinzufuegte, teilte das nur ihr mit - die
  schon Anwesenden erfuhren nichts und sahen sie erst nach dem Neuladen

## 0.23.0

- **Sprachnachrichten**: 🎤 im Eingabefeld startet die Aufnahme, ein zweiter
  Tipp schickt sie ab. Waehrenddessen laufen die Sekunden mit, *Verwerfen*
  wirft sie weg
- Ein eigener schmaler Abspieler mit Knopf, Fortschritt und Laenge statt des
  breiten Standardfelds. Eine zweite Aufnahme haelt die erste an
- Aufgenommen wird in Opus (WebM), Safari bekommt MP4. Das Mikrofon wird
  danach sofort wieder freigegeben

## 0.22.0

- **Standort, Abstimmung und Einladung stecken jetzt hinter der Heftklammer**
  statt als eigene Knoepfe im Eingabefeld. Dazu kommt *Standort live teilen* -
  bisher nur in der Seitenleiste zu finden
- Das Eingabefeld hat dadurch spuerbar mehr Platz, auf dem Telefon rund
  100 Pixel
- Das Menue sitzt immer ueber dem Eingabefeld, auch wenn es beim Tippen
  waechst. Ein Tipp daneben oder Esc schliesst es
- Die Pruefung auf einen sicheren Kontext liess nur `localhost` durch und wies
  `127.0.0.1` mit einem HTTPS-Hinweis ab, obwohl der Browser den Standort dort
  sehr wohl herausgibt. Jetzt entscheidet `isSecureContext`

## 0.21.0

- **Reiter in der Seitenleiste**, wie die Filterknoepfe bei WhatsApp:
  Unterhaltungen, Karten, Stimmung, Termine und **Zugesagt** - Letzteres
  zeigt nur die Termine, bei denen man selbst zugesagt hat
- Jeder Reiter traegt eine Zahl: ungelesene Nachrichten, laufende Freigaben,
  gueltige Stimmungsmeldungen, anstehende Termine, eigene Zusagen
- Der zuletzt gewaehlte Reiter bleibt am Geraet gespeichert
- Die Begrenzung auf drei Zeilen aus 0.20.0 faellt weg: es steht nur noch
  eine Liste auf einmal da, und die bekommt die volle Hoehe

## 0.20.1

- **Absagen darf allein, wer eingeladen hat** - der Administrator jetzt
  ausdruecklich nicht mehr. Wer zu einer Feier laedt, entscheidet auch, ob
  sie stattfindet
- Das gilt auch fuer den Umweg ueber das Aendern: `abgesagt` nimmt nur der
  Gastgeber. Sonst waere die Regel mit einem Feld zu umgehen
- Fremde Termine kann der Administrator weiterhin aendern

## 0.20.0

- **Stimmung** und **Termine** zeigen in der Seitenleiste hoechstens drei
  Zeilen, darueber hinaus wird gescrollt. Neben der Ueberschrift steht die
  Gesamtzahl
- Ein abgesagter Termin verschwand nicht aus der Seitenleiste, wenn jemand
  anders ihn absagte: die Anzeige wurde aus dem alten Stand neu gezeichnet,
  statt ihn nachzuladen

## 0.19.0

- **Filter auf der Live-Karte**: nach Zeitraum (Heute, Morgen, 7 Tage, Alles)
  und nach Merkmalen. Mehrere Merkmale wirken als *oder*. Angeboten werden nur
  Merkmale, die auch vorkommen; eine Zeile sagt, wie viel uebrig bleibt
- **Einladungen nachtraeglich aendern**: Titel, Zeit, Ort, Beschreibung,
  Merkmale, Bild. Die Zusagen bleiben erhalten
- **Ort per Klick auf der Karte** setzen und verschieben, dazu *Aktueller Ort*
  und *Ort entfernen*. Ist die Strassenkarte aus, steht dort ein Knopf, der
  sie einschaltet - die Umrisskarte ist dafuer zu grob
- **Absage zuruecknehmen**, mitsamt den alten Zusagen
- Ein ersetztes Bild wird von der Platte geraeumt

## 0.18.0

- Die **Live-Karte zeigt jetzt auch die Einladungen** - jeden anstehenden
  Termin mit hinterlegtem Ort. Personen tragen ihr Profilbild, Einladungen
  eine 📅-Fahne
- Ein Tipp auf eine Fahne oeffnet den Termin mit Beschreibung, Merkmalen und
  Zusagen
- Unter der Karte stehen beide Listen getrennt: *Wer teilt gerade* und
  *Einladungen*. Die Seitenleiste zaehlt beides
- Termine ohne Ort und abgesagte erscheinen nicht auf der Karte

## 0.17.0

- **Straßenkarte** mit Leaflet (1.9.4, BSD-2-Clause, liegt im Add-on) in der
  Live-Karte und der Terminansicht. Kacheln von OpenStreetMap
- Geladen wird erst beim Oeffnen einer ganzen Karte - beim Start der App und
  in Sprechblasen geht **keine einzige** Anfrage nach draussen. Dort bleibt
  es bei der Umrisskarte aus dem Add-on
- **Abschalter** in den Einstellungen. Dann bleibt es ueberall bei den
  Umrissen. Die Einstellung haengt am Konto, nicht am Geraet - eine
  Entscheidung ueber die eigenen Daten soll nicht davon abhaengen, mit
  welchem Telefon man sich anmeldet
- Kommt Leaflet nicht durch, bleibt die Umrisskarte stehen und sagt, warum

## 0.16.0

- **Einladungen** (Knopf 📅): Titel, Zeit, Ort, Bild, Beschreibung und
  Merkmale wie Musik, Tanz, Alkohol, Essen, Sport. Zusagen mit „Bin dabei“,
  „Vielleicht“, „Kann nicht“ - noch einmal tippen nimmt die Antwort zurueck
- **Termine** in der Seitenleiste: was ansteht, aus allen Unterhaltungen,
  der naechste zuerst. Eine Einladung rutscht im Verlauf sonst aus dem Blick
- **Karten** in der Seitenleiste: Live-Standort fuer 15 Minuten bis 8 Stunden
  freigeben, je Unterhaltung. Damit ist ohne Zutun klar, wer mitsehen darf.
  Die Freigabe laeuft von selbst ab, und wer die Gruppe verlaesst, teilt dort
  nicht weiter. Alle Punkte zusammen auf einer Uebersichtskarte
- **Stimmung**: worauf ich gerade Lust haette, mit Emoji, Dauer und auf
  Wunsch Ort - sichtbar fuer alle, mit denen ich eine Unterhaltung teile.
  Andere tippen auf „Ich mach mit“
- Die Terminkarte erbte `white-space: pre-wrap` von der Sprechblase; jede
  Einrueckung im Vorlagentext wurde dadurch zu einer Leerzeile und die Karte
  doppelt so hoch wie noetig

## 0.15.1

- Die Kartenvorschau beim Standort war leer. Die Umrisse lagen in einem
  `<symbol>`, und ein Symbol skaliert sich in das einbindende Element hinein –
  statt eines Ausschnitts wurde die ganze Welt in ein winziges Feld gequetscht

## 0.15.0

- **Gruppenabstimmung**: Der Knopf 📊 legt eine Frage mit bis zu zwölf
  Antworten an, wahlweise mit mehreren erlaubten Antworten. Sie erscheint als
  Nachricht mit Balken und Stimmenzahl
- Ein Tipp stimmt ab, ein weiterer nimmt die Stimme zurück. Bei Einfachwahl
  ersetzt eine neue Stimme die alte
- Wer für was gestimmt hat, steht im Tooltip der Antwort
- Stimmen anderer erscheinen sofort, ohne die Seite neu zu laden. Wer die
  Unterhaltung geschlossen hat, wird über die Abstimmung benachrichtigt

## 0.14.0

- **Standort senden**: Der Knopf 📍 schickt den eigenen Standort in die
  Unterhaltung, mit **Kartenvorschau**, Koordinaten und einem Link, der die
  Karten-App öffnet
- Die Karte liegt als Umrissdatei **im Add-on** (102 KB, gemeinfreie Daten von
  Natural Earth). Es wird nichts von fremden Servern nachgeladen – erst wer
  auf „In Karten öffnen“ tippt, verlässt das Haus
- Der Browser gibt den Standort nur über HTTPS heraus, also über die externe
  Adresse. Über den Ingress sagt die App das jetzt statt stumm zu bleiben

## 0.13.0

- **Mehrere Medien auf einmal löschen**: In der Übersicht schaltet
  **Auswählen** einen Auswahlmodus ein. Angetippte Kacheln bekommen einen
  Haken, **Alle** markiert auf einen Schlag, **Löschen** entfernt die ganze
  Auswahl – einzeln war das zu umständlich
- Fremde Dateien lassen sich dabei nicht auswählen (außer als Administrator)
  und werden beim Löschen übersprungen statt den ganzen Vorgang abzubrechen

## 0.12.0

- **Schutz gegen Durchprobieren an der Anmeldung**: Nach acht Fehlversuchen
  ist ein Konto für eine Viertelstunde gesperrt. Die Grenze je Absender liegt
  bewusst höher (40) – hinter Tunnel und Reverse Proxy haben alle dieselbe
  Adresse, eine strenge Grenze würde sonst die ganze Familie aussperren,
  sobald jemand ein einzelnes Konto angreift
- Gebremste Versuche stehen mit Kontonamen im Add-on-Protokoll
- **Hochgeladene Dateien bleiben aus dem Backup**: `/data/uploads` kann viele
  Gigabyte umfassen. Datenbank, Schlüssel und Profilbilder sind weiterhin
  enthalten

## 0.11.0

- **Mehrere Bilder auf einmal erscheinen als Album** in einer Sprechblase mit
  einer Uhrzeit, statt als lauter Einzelnachrichten. Das Raster richtet sich
  nach der Anzahl: zwei nebeneinander, bei dreien eines breit oben und zwei
  darunter, ab vier gleichmäßig
- Jedes Bild bleibt eine eigene Nachricht und damit einzeln löschbar

## 0.10.0

- **Emoji-Auswahl** neben dem Eingabefeld: rund 375 Zeichen in elf Gruppen,
  eingefügt wird an der Schreibmarke. Ohne Fremdbibliothek, funktioniert
  also auch ohne Internet
- **Videos erscheinen in der Medienübersicht als Vorschaukachel** statt als
  Zeile mit Dateinamen
- In der Dateiliste überlappten sich langer Name, Größe und Löschknopf. Der
  Name wird jetzt gekürzt, die beiden anderen behalten ihren Platz

## 0.9.2

- Das Token wird jetzt auch ohne `Bearer ` davor angenommen. Wer es in
  `secrets.yaml` nackt hinterlegt, bekam bisher nur ein wortkarges 401 – der
  häufigste Stolperstein beim Einrichten

## 0.9.1

- Abgelehnte Nachrichten aus Home Assistant stehen jetzt mit Grund im
  Add-on-Protokoll. Ein `rest_command` gilt dort auch dann als erfolgreich,
  wenn der Chat-Server ablehnt – bisher sah man deshalb gar nicht, weshalb
  nichts ankam
- Ist der Empfänger unbekannt, nennt die Antwort zusätzlich die vorhandenen
  Gruppen, und das Protokoll listet sie ebenfalls auf

## 0.9.0

- **Unterhaltungen löschen**: In den Angaben zur Unterhaltung (Tipp auf den
  Namen oben) gibt es **Chat löschen** – das entfernt sie nur bei dir, alle
  anderen behalten sie. Bleibt danach niemand mehr übrig, verschwindet sie
  samt Nachrichten und Anhängen
- Administratoren können mit **Für alle löschen** eine Unterhaltung
  endgültig entfernen, einschließlich der Dateien auf der Platte
- **Profilbilder in groß**: Ein Tipp auf das runde Bild neben einer Nachricht
  oder in den Angaben zur Unterhaltung zeigt es formatfüllend

## 0.8.0

- **Benachrichtigung erzwingen:** `POST /api/notify` nimmt jetzt
  `"always": true` an. Damit erreicht eine Meldung auch die, die den Chat
  gerade offen haben – für Alarme, die niemand verpassen soll. Ohne das Feld
  bleibt es beim bisherigen Verhalten
- Die Antwort nennt unter `pushed`, an wie viele Geräte sie ging
- **Das Token steht in der Oberfläche**: Administratoren finden es unter
  **… → Einstellungen → Home Assistant** samt Kopierknopf, statt es aus
  `/data/api_token.txt` holen zu müssen

## 0.7.0

- **Nachrichten sehen aus wie gewohnt:** In Gruppen trägt jede fremde
  Nachricht das Bild des Absenders und seinen Namen in einer eigenen Farbe –
  auch bei mehreren Nachrichten hintereinander. Eigene stehen rechts ohne
  Bild und Namen, im Direktchat entfällt beides
- **Videos und Musik** erscheinen mit Abspieler, Vorschaubild und
  Abspielknopf statt als Anhang. Geladen wird nur der Anfang
- **Mehrere Dateien auf einmal** auswählen und senden, mit Fortschrittsanzeige
- **Farbe je Unterhaltung**: neun Töne für die eigenen Sprechblasen, über
  einen Tipp auf den Namen in der Kopfzeile. Die Wahl gilt nur für einen
  selbst, andere behalten ihre

## 0.6.2

- Die Uhrzeit bleibt beim Antippen einer Nachricht an ihrem Platz. Sie hing an
  der Sprechblase und rutschte beim Aufklappen von „Antworten“ und
  „Löschen“ nach unten zu den Knöpfen – jetzt hängt sie am Text

## 0.6.1

- **Der Sende-Knopf funktioniert wieder.** Er reichte sein Klick-Ereignis als
  Datei-Kennung an das Senden weiter; der Server wies die Nachricht ab und
  niemand erfuhr davon. Mit der Tastatur am Rechner fiel es nicht auf, am
  Handy tippt man den Knopf
- **Jede Nachricht wird jetzt vom Server bestätigt.** Bleibt die Bestätigung
  aus oder wird die Nachricht abgelehnt, sagt die Oberfläche das und der Text
  kehrt ins Eingabefeld zurück, statt verloren zu gehen
- Fehlt die Verbindung, erscheint ein Hinweis über dem Eingabefeld
- Das App-Symbol wird nach einem Update erneuert: das Manifest wird erzeugt
  und trägt für die Symbole eine Kennung – vorher blieb beim Hinzufügen zum
  Home-Bildschirm das alte Bild hängen
- Im Einstellungsdialog passen „Bild wählen" und „Entfernen" wieder
  nebeneinander in den Rahmen

## 0.6.0

- **Profilbilder für Personen und Gruppen** – sichtbar in der Unterhaltungs-
  liste und in der Kopfzeile. Das eigene Bild setzt man in den Einstellungen,
  das Gruppenbild durch Tippen auf das Bild oben in der Gruppe
- Ohne Bild erscheinen die Initialen auf farbigem Grund, die Farbe bleibt für
  dieselbe Person gleich
- Bilder werden im Browser auf 256 Pixel verkleinert und quadratisch
  zugeschnitten, bevor sie hochgeladen werden; ersetzte Bilder werden vom
  Server gelöscht
- **Nach einem Update lädt der Browser die Oberfläche wieder frisch.** Bisher
  behielt er `app.js` und `style.css` im Zwischenspeicher – auf dem Handy
  sah die Ansicht danach kaputt aus oder Knöpfe fehlten, obwohl das Add-on
  aktuell war. Die Dateien tragen jetzt einen Änderungsstempel in der Adresse
- **Senden mit der Bildschirmtastatur** funktioniert wieder: Android meldet
  beim Tippen auf Enter oft kein „Enter“, sondern einen Umbruch aus der
  Worterkennung. Darauf hört die Eingabe jetzt zusätzlich, und die Tastatur
  zeigt eine Senden-Taste statt einer Zeilenschaltung
- Der Abstand zwischen Text und Uhrzeit ist größer und bleibt es auch bei
  langen Nachrichten: die Uhrzeit sitzt jetzt fest unten rechts, und der Text
  lässt dafür Platz – vorher klebte sie bei voller Zeile am letzten Wort

## 0.5.0

- **Eigenes Logo** – als Add-on-Symbol, auf der Anmeldeseite, als App-Symbol
  auf dem Home-Bildschirm und als Favicon im Browser-Tab
- **Selbstregistrierung mit Freigabe**: Auf der Anmeldeseite können Leute
  über **Zugang beantragen** ein Konto anfragen – mit E-Mail oder
  Telefonnummer und einer Begründung. Bis ein Administrator freigibt, kommt
  niemand hinein und der Name erscheint in keiner Auswahlliste
- Anträge stehen oben in der Benutzerverwaltung, mit Kontaktdaten und
  Begründung, und lassen sich freigeben oder ablehnen
- Administratoren mit Push bekommen bei neuen Anträgen eine Benachrichtigung
- Die offene Registrierungsseite nimmt höchstens drei Anträge je Stunde und
  Absender an; mit `allow_registration: false` lässt sie sich abschalten
- Gesperrte Konten erscheinen nicht mehr in der Auswahl für neue
  Unterhaltungen

## 0.4.1

- Sprechblasen sind deutlich kompakter: unter jeder Nachricht standen 40 Pixel
  Leerraum, weil die Zeilenumbrüche der Vorlage zu Textknoten wurden. Eine
  Textnachricht misst jetzt 38 statt 114 Pixel
- Die Uhrzeit steht wie bei WhatsApp rechts neben dem Text statt in einer
  eigenen Zeile darunter
- Die Medienübersicht ist jetzt auch aus einer geöffneten Unterhaltung
  erreichbar – auf dem Handy war sie es gar nicht, weil die Seitenleiste dort
  verdeckt wird, sobald ein Chat offen ist. Der Knopf in der Kopfzeile zeigt
  gleich die Medien dieser Unterhaltung

## 0.4.0

- **Medienübersicht** über den Knopf **Medien**: alle Bilder und Dateien aus
  den eigenen Unterhaltungen, als Raster und Liste, mit Absender, Unterhaltung
  und Zeitpunkt – wahlweise über alle Chats oder auf einen eingeschränkt
- Gelöschte Dateien verschwinden jetzt auch **von der Platte**. Bisher blieben
  die Bytes in `/data/uploads` liegen, obwohl die Nachricht als gelöscht galt
- Wer eine Nachricht mit Anhang löscht, löscht damit auch den Anhang
- Eigene Dateien darf jeder entfernen, fremde nur ein Administrator

## 0.3.1

- Die Verbindung wird jetzt wie vorgesehen erst über Polling aufgebaut und
  dann auf WebSocket hochgestuft. Der bisherige Direktversuch scheiterte am
  eingebauten Server, schrieb bei jedem Verbindungsaufbau einen
  `AssertionError: write() before start_response` ins Protokoll und kostete
  einen Fehlversuch — die Verbindung läuft unverändert über WebSocket

## 0.3.0

- **Benutzerverwaltung für Administratoren** unter **… → Benutzer verwalten**:
  Passwort zurücksetzen, Administratorrechte vergeben und entziehen, Konten
  sperren und entsperren, Konten endgültig löschen
- Ein zurückgesetztes Passwort meldet das Konto auf allen Geräten ab; wer
  gesperrt oder gelöscht wird, verliert laufende Sitzungen sofort
- Beim Löschen bleiben die Nachrichten im Verlauf stehen und erscheinen unter
  „Gelöschtes Konto“, damit fremde Unterhaltungen keine Lücken bekommen
- Schutz gegen Aussperren: das eigene Konto lässt sich weder sperren, löschen
  noch entmachten, und der letzte verbliebene Administrator bleibt bestehen
- Die Anmeldung beachtet Groß- und Kleinschreibung des Benutzernamens nicht
  mehr — bisher kam nicht hinein, wer den Namen groß schrieb, obwohl neue
  Konten immer klein gespeichert werden
- Gesperrte Konten erhalten keine Nachrichten mehr über `POST /api/notify`
  und erscheinen nicht in der Auswahl für neue Unterhaltungen

## 0.2.2

- Der Socket.IO-Client liegt jetzt im Repository statt beim Bauen vom CDN
  geladen zu werden: die Installation auf dem Pi braucht dafür kein Internet
  mehr und liefert bei jedem Bau dieselbe Fassung aus

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
