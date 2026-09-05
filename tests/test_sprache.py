"""Prueft, dass die Oberflaeche vollstaendig uebersetzbar ist.

Der Anlass: 0.45.0 war zwar zweisprachig, aber rund 200 Texte liefen gar
nicht erst durch T() beziehungsweise t() - sie blieben deutsch stehen, auch
wenn alles andere englisch war. Diese Reihe faengt genau das ab:

  1. Jeder Schluessel aus T(...) steht in i18n.js.
  2. Jeder Schluessel aus t(...) steht in texte.py.
  3. Kein Oberflaechentext steht ohne T() im Code.
  4. Kein title=T(...) - das schreibt T("...") woertlich in die Seite.
  5. Kein fest verdrahtetes "de-DE" - das Datum folgt der Sprache.
  6. Der laufende Server liefert die Anmeldeseite wirklich englisch aus.

Die ersten fuenf Punkte lesen nur Dateien; Punkt 6 braucht den Server.
"""
import re
import sys
from pathlib import Path

import requests

from helpers import BASE, Ergebnis

APP_DIR = Path(__file__).resolve().parent.parent / "chat_server" / "app"
APP = APP_DIR / "static" / "app.js"
I18N = APP_DIR / "static" / "i18n.js"
TEXTE = APP_DIR / "texte.py"
VORLAGEN = APP_DIR / "templates"

e = Ergebnis()
quelle = APP.read_text(encoding="utf-8")
n = len(quelle)


# ---------------------------------------------------------------- Werkzeug
def kommentarfeld(text):
    """Welche Stellen liegen in einem Kommentar?"""
    feld = bytearray(len(text))
    i = 0
    while i < len(text):
        z = text[i]
        if z in "'\"`":
            ende, i = z, i + 1
            while i < len(text):
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == ende or (ende != "`" and text[i] == "\n"):
                    break
                i += 1
            i += 1
        elif z == "/" and text[i:i + 2] == "//":
            while i < len(text) and text[i] != "\n":
                feld[i] = 1
                i += 1
        elif z == "/" and text[i:i + 2] == "/*":
            schluss = text.find("*/", i + 2)
            schluss = len(text) if schluss < 0 else schluss + 2
            for j in range(i, schluss):
                feld[j] = 1
            i = schluss
        else:
            i += 1
    return feld


def aufrufe(text, name, kommentar):
    """(Anfang, Ende) jedes name(...) samt passender Klammer."""
    treffer = []
    for m in re.finditer(r"\b%s\(" % name, text):
        if kommentar[m.start()]:
            continue
        i, tiefe = m.end() - 1, 0
        while i < len(text):
            z = text[i]
            if z in "'\"`":
                ende, i = z, i + 1
                while i < len(text):
                    if text[i] == "\\":
                        i += 2
                        continue
                    if text[i] == ende:
                        break
                    i += 1
            elif z == "(":
                tiefe += 1
            elif z == ")":
                tiefe -= 1
                if tiefe == 0:
                    treffer.append((m.start(), i))
                    break
            i += 1
    return sorted(treffer)


def woerterbuch(pfad, anfang):
    """Schluessel eines Objektliterals - ohne node auszufuehren."""
    text = pfad.read_text(encoding="utf-8")
    text = text[text.index(anfang):]
    schluessel, i = set(), 0
    zeilen = text.split("\n")
    for nr, zeile in enumerate(zeilen):
        # Ein Schluessel steht am Zeilenanfang und endet auf ": oder "
        m = re.match(r'\s*"((?:[^"\\]|\\.)*)"\s*(:?)\s*$', zeile) \
            or re.match(r'\s*"((?:[^"\\]|\\.)*)"\s*:', zeile)
        if not m:
            continue
        roh = m.group(1)
        # Ueber mehrere Zeilen umgebrochene Schluessel zusammensetzen
        j = nr
        while not re.search(r'"\s*:', zeilen[j]) and j + 1 < len(zeilen):
            j += 1
            weiter = re.match(r'\s*"((?:[^"\\]|\\.)*)"', zeilen[j])
            if not weiter:
                break
            roh += weiter.group(1)
        schluessel.add(roh.replace('\\"', '"').replace("\\\\", "\\"))
    return schluessel


LITERAL = re.compile(r"""(['"])((?:(?!\1)[^\\\n]|\\.)*)\1""")
ENTKOMMEN = {"\\n": "\n", "\\t": "\t", '\\"': '"', "\\'": "'", "\\\\": "\\"}


def fester_text(roh):
    """Der Text, wenn das Argument nur aus Zeichenketten besteht."""
    if LITERAL.sub("", roh).strip().strip("+").strip():
        return None
    text = ""
    for m in LITERAL.finditer(roh):
        stueck = m.group(2)
        for a, b in ENTKOMMEN.items():
            stueck = stueck.replace(a, b)
        text += stueck
    return text or None


# ------------------------------------------------- 1. Schluessel in i18n.js
e.abschnitt("Schluessel der Oberflaeche")

kommentar = kommentarfeld(quelle)
spannen = aufrufe(quelle, "T", kommentar)
bekannt = woerterbuch(I18N, "window.WORTE_EN")

e.pruefe(len(bekannt) > 300, f"i18n.js gelesen ({len(bekannt)} Schluessel)")
e.pruefe(len(spannen) > 500, f"T()-Aufrufe gefunden ({len(spannen)})")

fehlend = []
for a, b in spannen:
    text = fester_text(quelle[a + 2:b])
    if text and text not in bekannt:
        fehlend.append(text)
e.pruefe(not fehlend,
         "jeder T()-Schluessel steht in i18n.js"
         + (f" - es fehlen {len(fehlend)}: {fehlend[:3]}" if fehlend else ""))


# ------------------------------------------------- 2. Schluessel in texte.py
e.abschnitt("Schluessel der Vorlagen")

raum = {}
exec(compile(TEXTE.read_text(encoding="utf-8"), "texte.py", "exec"), raum)
SERVER_WORTE = raum["EN"]
e.pruefe(len(SERVER_WORTE) > 50,
         f"texte.py gelesen ({len(SERVER_WORTE)} Eintraege)")

vorlagen_fehlend = []
for datei in sorted(VORLAGEN.glob("*.html")):
    inhalt = datei.read_text(encoding="utf-8")
    for m in re.finditer(r"""\bt\(\s*(["'])((?:(?!\1)[^\\]|\\.)*)\1""",
                         inhalt, re.S):
        if m.group(2) not in SERVER_WORTE:
            vorlagen_fehlend.append(f"{datei.name}: {m.group(2)}")
e.pruefe(not vorlagen_fehlend,
         "jeder t()-Schluessel steht in texte.py"
         + (f" - es fehlen {vorlagen_fehlend[:3]}" if vorlagen_fehlend else ""))


# ------------------------------------------- 3. Kein Text ohne Uebersetzung
e.abschnitt("Kein deutscher Text am Woerterbuch vorbei")


def gedeckt(p):
    for a, b in spannen:
        if a <= p <= b:
            return True
    return False


# Text zwischen > und < sowie zwischen } und < - letzteres faengt auch
# `>${zahl} auf der Karte<` ab, wo eine Einsetzung davorsteht.
UMLAUT = re.compile(r"[ÄÖÜäöüß]")
FUELLWORT = {
    "der", "die", "das", "den", "dem", "und", "oder", "nicht", "kein",
    "keine", "noch", "hier", "von", "zu", "mit", "für", "ist", "sind",
    "du", "dein", "deine", "im", "als", "wie", "wer", "wo", "bei", "aus",
    "nach", "über", "unter", "vor", "bis", "alle", "auf", "eine", "einen",
}
uebrig = {}
for m in re.finditer(r"[>}]([^<>{}$]+)(?=<|\$\{)", quelle):
    p = m.start(1)
    if kommentar[p] or gedeckt(p):
        continue
    s = m.group(1).strip()
    woerter = re.findall(r"[A-Za-zÄÖÜäöüß]+", s)
    if len(s) < 3 or not woerter or re.search(r"[/#=<>{}\\$()\[\];]", s):
        continue
    if UMLAUT.search(s) or any(w.lower() in FUELLWORT for w in woerter):
        uebrig.setdefault(s, quelle[:p].count("\n") + 1)

e.pruefe(not uebrig,
         "kein deutscher Oberflaechentext ohne T()"
         + (f" - {len(uebrig)}: {list(uebrig.items())[:3]}" if uebrig else ""))

roh_vorlage = []
for datei in sorted(VORLAGEN.glob("*.html")):
    inhalt = datei.read_text(encoding="utf-8")
    maske = list(inhalt)
    for m in re.finditer(r"\{\{.*?\}\}|\{%.*?%\}|<!--.*?-->"
                         r"|<script\b.*?</script>|<style\b.*?</style>",
                         inhalt, re.S):
        for k in range(m.start(), m.end()):
            maske[k] = "\x01"
    for m in re.finditer(r">([^<>]*)<", "".join(maske)):
        for stueck in re.finditer(r"[^\x01\n]+", m.group(1)):
            s = stueck.group(0).strip()
            # "Deutsch" und "English" stehen bewusst in ihrer eigenen Sprache
            if s in ("Deutsch", "English") or len(s) < 3:
                continue
            if UMLAUT.search(s):
                roh_vorlage.append(f"{datei.name}: {s}")
e.pruefe(not roh_vorlage,
         "kein deutscher Text ohne t() in den Vorlagen"
         + (f" - {roh_vorlage[:3]}" if roh_vorlage else ""))


# --------------------------------------------------- 4./5. Alte Fehlerbilder
e.abschnitt("Fehlerbilder, die es schon einmal gab")

# title=T("...") landet woertlich im HTML: der Browser liest title='T("...'
e.pruefe("title=T(" not in quelle,
         "kein title=T(...) ausserhalb einer Einsetzung")

# Ein festes "de-DE" zeigt deutsche Datumsformate auch im englischen Text
ohne_locale = re.sub(r"const LOCALE = .*", "", quelle)
e.pruefe('"de-DE"' not in ohne_locale,
         "kein fest verdrahtetes Datumsformat ausser in LOCALE")
e.pruefe("const LOCALE" in quelle, "LOCALE richtet sich nach der Sprache")

# Englische Werte duerfen keine deutschen Menuenamen mehr nennen
i18n_text = I18N.read_text(encoding="utf-8")
e.pruefe("„Termine“ (events)" not in i18n_text,
         "englische Texte nennen die englischen Menuenamen")


# --------------------------------------------------------- 6. Am Server
e.abschnitt("Der Server liefert englisch aus")

seite = requests.get(f"{BASE}/login?lang=en", timeout=5)
e.pruefe(seite.status_code == 200, "Anmeldeseite erreichbar")
e.pruefe('lang="en"' in seite.text, "Seite ist als englisch ausgezeichnet")
e.pruefe("Sign in with your account." in seite.text,
         "Anmeldetext ist uebersetzt")
e.pruefe("Melde dich mit deinem Konto an." not in seite.text,
         "kein deutscher Anmeldetext mehr auf der Seite")

deutsch = requests.get(f"{BASE}/login?lang=de", timeout=5)
e.pruefe("Melde dich mit deinem Konto an." in deutsch.text,
         "Deutsch bleibt erreichbar")

sys.exit(e.bilanz())
