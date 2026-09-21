"""Wortvorrat fuer das Impostor-Spiel.

Jedes Wort bringt einen Tipp mit. Den bekommt nur der Impostor zu sehen: er
soll ihm eine Chance geben, mitzureden und das Wort zu erraten, ohne es zu
verraten. Darum nennt der Tipp die Richtung, nie das Wort selbst.

Diese Liste wird beim ersten Start in die Datenbank geschrieben. Danach ist
die Datenbank die Quelle: dort kommen eigene Woerter dazu, und dort steht,
welche Woerter nicht mehr drankommen sollen. Neue Woerter, die hier spaeter
dazukommen, werden beim Start ergaenzt - vorhandene bleiben unangetastet.
"""

# Schluessel -> (deutscher Name, englischer Name)
KATEGORIEN = {
    "sport": ("Sport", "Sports"),
    "musik": ("Musik", "Music"),
    "geschichte": ("Weltgeschichte", "World history"),
    "essen": ("Essen und Trinken", "Food and drink"),
    "tiere": ("Tiere", "Animals"),
    "film": ("Film und Fernsehen", "Film and TV"),
    "technik": ("Technik", "Technology"),
    "alltag": ("Alltag", "Everyday life"),
    "berufe": ("Berufe", "Jobs"),
    "reisen": ("Reisen", "Travel"),
}

# (Kategorie, Wort, Tipp fuer den Impostor)
WORTE = [
    # ---------- Sport ----------
    ("sport", "Fußball", "Zwei Mannschaften, ein Ball, ein Rasen."),
    ("sport", "Tennis", "Es gibt ein Netz und eine eigenartige Zählweise."),
    ("sport", "Marathon", "Es geht um Ausdauer, nicht um Tempo."),
    ("sport", "Skispringen", "Winter, und es geht weit nach unten."),
    ("sport", "Boxen", "Zwei Personen, Handschuhe, Runden."),
    ("sport", "Schwimmbad", "Man braucht Badesachen."),
    ("sport", "Radrennen", "Es geht um Berge und Sekunden."),
    ("sport", "Schiedsrichter", "Diese Person wird selten geliebt."),
    ("sport", "Olympia", "Alle vier Jahre, viele Länder."),
    ("sport", "Torwart", "Eine Sonderrolle im Team."),
    ("sport", "Golf", "Viel Rasen, wenig Ball."),
    ("sport", "Klettern", "Es geht nach oben, am besten gesichert."),
    ("sport", "Yoga", "Ruhe, Matte, eigenartige Haltungen."),
    ("sport", "Handball", "Halle, Tor, aber nicht mit dem Fuß."),
    ("sport", "Dart", "Kneipe, Ziel, Spitzen."),
    ("sport", "Formel 1", "Sehr laut, sehr schnell, sehr rund."),

    # ---------- Musik ----------
    ("musik", "Gitarre", "Etwas mit Saiten."),
    ("musik", "Schlagzeug", "Der Grund, warum Nachbarn klingeln."),
    ("musik", "Oper", "Gesungen, und meist auf Italienisch."),
    ("musik", "Beatles", "Eine Band aus England, sehr lange her."),
    ("musik", "Kopfhörer", "Damit hört es nur einer."),
    ("musik", "Festival", "Sommer, Zelt, viele Leute."),
    ("musik", "Klavier", "Schwarz und weiß, und schwer zu tragen."),
    ("musik", "Dirigent", "Steht vorn und spielt selbst nichts."),
    ("musik", "Blasmusik", "Man braucht Luft dafür."),
    ("musik", "Schallplatte", "Rund, schwarz, und wieder in Mode."),
    ("musik", "Ohrwurm", "Man wird es nicht mehr los."),
    ("musik", "Karaoke", "Mut ist wichtiger als Talent."),
    ("musik", "Geige", "Klein, teuer, unter dem Kinn."),
    ("musik", "Hip-Hop", "Mehr gesprochen als gesungen."),
    ("musik", "Chor", "Viele Stimmen, ein Stück."),

    # ---------- Weltgeschichte ----------
    ("geschichte", "Berliner Mauer", "Sie stand mitten in einer Stadt."),
    ("geschichte", "Mondlandung", "1969, und manche zweifeln bis heute."),
    ("geschichte", "Titanic", "Es ging um Eis."),
    ("geschichte", "Pyramiden", "Sehr alt, sehr groß, sehr eckig."),
    ("geschichte", "Römisches Reich", "Straßen, Legionen, Latein."),
    ("geschichte", "Französische Revolution", "Es ging ums Köpfen."),
    ("geschichte", "Buchdruck", "Davor schrieb man alles ab."),
    ("geschichte", "Wikinger", "Norden, Schiffe, schlechter Ruf."),
    ("geschichte", "Kolumbus", "Er suchte etwas anderes."),
    ("geschichte", "Mittelalter", "Burgen, Pest und wenig Seife."),
    ("geschichte", "Kalter Krieg", "Zwei Seiten, kein Schuss."),
    ("geschichte", "Steinzeit", "Feuer war das Neueste."),
    ("geschichte", "Napoleon", "Klein gewachsen, groß gedacht."),
    ("geschichte", "Seidenstraße", "Ein Weg für Waren, sehr weit."),
    ("geschichte", "Wiedervereinigung", "Aus zwei wurde eins."),

    # ---------- Essen und Trinken ----------
    ("essen", "Pizza", "Rund, und es gibt Streit über den Belag."),
    ("essen", "Kaffee", "Der Grund, warum der Morgen funktioniert."),
    ("essen", "Currywurst", "Eine Beilage macht sie berühmt."),
    ("essen", "Sushi", "Roh, und man isst es mit Stäbchen."),
    ("essen", "Schokolade", "Es schmilzt in der Hand."),
    ("essen", "Grillen", "Draußen, mit Rauch und Meinungen."),
    ("essen", "Weißbier", "Ein hohes Glas gehört dazu."),
    ("essen", "Spaghetti", "Lang und schwer zu essen."),
    ("essen", "Käse", "Je älter, desto teurer."),
    ("essen", "Brezel", "Man verknotet sie."),
    ("essen", "Suppe", "Man braucht einen Löffel."),
    ("essen", "Eisdiele", "Vor allem im Sommer voll."),
    ("essen", "Knoblauch", "Man riecht es am nächsten Tag noch."),
    ("essen", "Frühstück", "Die erste Gelegenheit am Tag."),
    ("essen", "Weihnachtsmarkt", "Es ist kalt, und man trinkt trotzdem."),

    # ---------- Tiere ----------
    ("tiere", "Elefant", "Sehr groß, sehr grau, gutes Gedächtnis."),
    ("tiere", "Pinguin", "Es kann nicht fliegen, dafür schwimmen."),
    ("tiere", "Katze", "Sie entscheidet, wann gekuschelt wird."),
    ("tiere", "Biene", "Ohne sie wird es eng."),
    ("tiere", "Hai", "Eine Filmmusik hat ihm geschadet."),
    ("tiere", "Eichhörnchen", "Es vergisst, wo es etwas versteckt hat."),
    ("tiere", "Papagei", "Es plappert nach."),
    ("tiere", "Schildkröte", "Sie hat Zeit."),
    ("tiere", "Wolf", "Der Vorfahr eines Haustiers."),
    ("tiere", "Kuh", "Sie steht auf der Weide und liefert täglich."),
    ("tiere", "Spinne", "Acht Beine, viele Ängste."),
    ("tiere", "Delfin", "Klug, und es lebt im Wasser."),
    ("tiere", "Pferd", "Man kann darauf sitzen."),
    ("tiere", "Mücke", "Nachts im Schlafzimmer der Feind."),
    ("tiere", "Adler", "Er steht auf Wappen."),

    # ---------- Film und Fernsehen ----------
    ("film", "Tatort", "Sonntagabend, immer dieselbe Zeit."),
    ("film", "Star Wars", "Weltraum, und es gibt Teil 1 bis 9."),
    ("film", "Zeichentrick", "Gemalt, nicht gefilmt."),
    ("film", "Kinosaal", "Dunkel, und es riecht nach Mais."),
    ("film", "Netflix", "Man sucht länger, als man schaut."),
    ("film", "Horrorfilm", "Man schaut durch die Finger."),
    ("film", "Nachrichten", "Jeden Abend um dieselbe Zeit."),
    ("film", "James Bond", "Ein Getränk wird geschüttelt."),
    ("film", "Werbepause", "Der Moment für den Kühlschrank."),
    ("film", "Serienfinale", "Danach ist es vorbei."),
    ("film", "Untertitel", "Man liest, statt zu hören."),
    ("film", "Fernbedienung", "Sie liegt nie da, wo man sucht."),
    ("film", "Komödie", "Man soll dabei lachen."),
    ("film", "Dokumentation", "Es soll echt sein."),
    ("film", "Popcorn", "Es gehört ins Kino."),

    # ---------- Technik ----------
    ("technik", "Smartphone", "Es liegt neben dir."),
    ("technik", "WLAN", "Man merkt es erst, wenn es fehlt."),
    ("technik", "Akku", "Immer zur falschen Zeit leer."),
    ("technik", "Drucker", "Er streikt, wenn es eilig ist."),
    ("technik", "Passwort", "Man vergisst es zuverlässig."),
    ("technik", "Kühlschrank", "Er summt in der Küche."),
    ("technik", "Staubsauger", "Er macht Lärm und Ordnung."),
    ("technik", "Roboter", "Er soll die Arbeit machen."),
    ("technik", "Satellit", "Er kreist da oben."),
    ("technik", "Elektroauto", "Es braucht kein Benzin."),
    ("technik", "Kamera", "Sie hält etwas fest."),
    ("technik", "Suchmaschine", "Der erste Schritt bei jeder Frage."),
    ("technik", "Updates", "Immer im falschen Moment."),
    ("technik", "Taschenlampe", "Sie hilft im Dunkeln."),
    ("technik", "Waschmaschine", "Sie dreht sich und schluckt Socken."),

    # ---------- Alltag ----------
    ("alltag", "Wecker", "Der unbeliebteste Ton des Tages."),
    ("alltag", "Regenschirm", "Man hat ihn nie dabei, wenn man ihn braucht."),
    ("alltag", "Supermarkt", "Man geht für eine Sache und kommt mit zehn."),
    ("alltag", "Stau", "Man steht, statt zu fahren."),
    ("alltag", "Montag", "Der unbeliebteste von sieben."),
    ("alltag", "Wäscheberg", "Er wächst von allein."),
    ("alltag", "Zahnarzt", "Zweimal im Jahr, ungern."),
    ("alltag", "Schlüssel", "Ohne ihn stehst du draußen."),
    ("alltag", "Geburtstag", "Einmal im Jahr, mit Kerzen."),
    ("alltag", "Sonntag", "Die Läden bleiben zu."),
    ("alltag", "Umzug", "Kisten und falsche Freunde."),
    ("alltag", "Nachbar", "Man hört ihn, bevor man ihn sieht."),
    ("alltag", "Warteschlange", "Die andere geht immer schneller."),
    ("alltag", "Kaugummi", "Man soll es nicht verschlucken."),
    ("alltag", "Winterreifen", "Zweimal im Jahr ein Termin."),

    # ---------- Berufe ----------
    ("berufe", "Feuerwehr", "Man ruft sie bei Rauch."),
    ("berufe", "Bäcker", "Er steht auf, wenn andere schlafen."),
    ("berufe", "Lehrer", "Er hat viele Ferien, sagt man."),
    ("berufe", "Pilot", "Sein Arbeitsplatz ist weit oben."),
    ("berufe", "Arzt", "Man geht ungern hin."),
    ("berufe", "Polizist", "Eine Uniform gehört dazu."),
    ("berufe", "Bauer", "Er arbeitet nach dem Wetter."),
    ("berufe", "Friseur", "Danach sieht man anders aus."),
    ("berufe", "Programmierer", "Viel sitzen, wenig reden."),
    ("berufe", "Kellner", "Er merkt sich, wer was wollte."),
    ("berufe", "Briefträger", "Er kennt jeden Hund im Viertel."),
    ("berufe", "Bürgermeister", "Man wählt ihn."),
    ("berufe", "Müllabfuhr", "Sehr früh und sehr laut."),
    ("berufe", "Hebamme", "Sie ist am Anfang dabei."),
    ("berufe", "Schornsteinfeger", "Er soll Glück bringen."),

    # ---------- Reisen ----------
    ("reisen", "Flughafen", "Warten gehört dazu."),
    ("reisen", "Zelt", "Man schläft auf dem Boden."),
    ("reisen", "Venedig", "Statt Straßen gibt es Wasser."),
    ("reisen", "Strandurlaub", "Sand, Sonne, wenig Programm."),
    ("reisen", "Wanderung", "Feste Schuhe sind wichtig."),
    ("reisen", "Reisepass", "Ohne ihn kommt man nicht weit."),
    ("reisen", "Kreuzfahrt", "Ein Hotel, das schwimmt."),
    ("reisen", "Berghütte", "Oben, mit Aussicht und Bier."),
    ("reisen", "Souvenir", "Es verstaubt zu Hause."),
    ("reisen", "Nachtzug", "Man schläft und kommt trotzdem an."),
    ("reisen", "Sonnenbrand", "Am ersten Tag zu leichtsinnig."),
    ("reisen", "Landkarte", "Früher aus Papier."),
    ("reisen", "Sprachkurs", "Damit man sich verständlich macht."),
    ("reisen", "Wohnmobil", "Man nimmt alles mit."),
    ("reisen", "Ansichtskarte", "Sie kommt nach der Rückkehr an."),
]


def kategorie_name(schluessel, englisch=False):
    """Anzeigename einer Kategorie; unbekannte Schluessel bleiben, wie sie sind."""
    eintrag = KATEGORIEN.get(schluessel)
    if not eintrag:
        return schluessel
    return eintrag[1] if englisch else eintrag[0]
