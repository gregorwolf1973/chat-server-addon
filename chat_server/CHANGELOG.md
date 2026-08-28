# Änderungsverlauf

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
