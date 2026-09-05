"""Englische Fassung der Texte, die der Server selbst in Seiten schreibt.

Das betrifft das Grundgeruest von index.html und die drei Seiten vor der
Anmeldung. Alles Uebrige baut die Oberflaeche selbst zusammen und uebersetzt
es ueber static/i18n.js.

Deutsch ist auch hier die Quelle: fehlt eine Uebersetzung, bleibt der deutsche
Satz stehen.
"""

EN = {
    # ---------- Geruest der Oberflaeche ----------
    "Unterhaltungen": "Conversations",
    "Karten": "Maps",
    "Stimmung": "Mood",
    "Termine": "Events",
    "Tipps": "Tips",
    "+ Neu": "+ New",
    "Neue Unterhaltung": "New conversation",
    "Freunde": "Friends",
    "Galerie": "Gallery",
    "Einstellungen": "Settings",
    "Standort teilen": "Share location",
    "Stimmung setzen": "Set a mood",
    "Termin ohne Unterhaltung": "Event without a conversation",
    "Empfehlung schreiben": "Write a recommendation",
    "Anrufen": "Call",
    "Videoanruf": "Video call",
    "Im Verlauf suchen": "Search the history",
    "Im Verlauf suchen …": "Search the history …",
    "Alle Unterhaltungen": "All conversations",
    "Suche schließen": "Close search",
    "Zum vorigen Tag": "To the previous day",
    "Ans Ende": "To the end",
    "Person hinzufügen": "Add person",
    "+ Person": "+ Person",
    "Medien": "Media",
    "Bilder und Dateien dieser Unterhaltung":
        "Pictures and files in this conversation",
    "Antwort an": "Reply to",
    "Antwort verwerfen": "Discard reply",
    "Wähle links eine Unterhaltung oder starte mit „+ Neu“ eine neue.":
        "Pick a conversation on the left, or start one with „+ Neu“ (new).",
    "Nachricht schreiben …": "Write a message …",
    "Emoji": "Emoji",
    "Anhang": "Attachment",
    "Senden": "Send",
    "Sprachnachricht aufnehmen": "Record a voice message",
    "Abstimmung": "Poll",
    "Einladung": "Invitation",
    "Auflegen": "Hang up",
    "Mikrofon": "Microphone",
    "Kamera": "Camera",
    "Anruf": "Call",
    "Bild": "Picture",
    "Schließen": "Close",
    "＋ Bild hinzufügen": "＋ Add picture",
    "Benachrichtigungen einschalten": "Turn on notifications",
    "Zurück": "Back",
    "Deine Bilder und Filme": "Your pictures and films",
    "Halten zum Aufnehmen – Loslassen schickt ab":
        "Hold to record — release to send",
    "Anhängen": "Attach",
    "Zum Aufnehmen gedrückt halten": "Hold down to record",

    # ---------- Anmeldung ----------
    "Anmelden": "Sign in",
    "Melde dich mit deinem Konto an.": "Sign in with your account.",
    "Benutzername": "User name",
    "Passwort": "Password",
    "Passwort vergessen?": "Forgotten your password?",
    "Noch kein Konto?": "No account yet?",
    "Zugang beantragen": "Request access",
    "Zur Anmeldung": "To the sign-in page",
    "Zurück zur Anmeldung": "Back to the sign-in page",
    "Ich habe schon ein Konto": "I already have an account",
    "Zeigen": "Show",
    "Verbergen": "Hide",
    "Passwort anzeigen": "Show password",
    "Passwort verbergen": "Hide password",

    # ---------- Passwort vergessen ----------
    "Passwort vergessen": "Forgotten password",
    "Dieser Chat verschickt keine Mail. Stattdessen erfährt der Administrator "
    "davon und setzt dir ein neues Passwort.":
        "This chat sends no e-mail. Instead the administrator is told and sets "
        "a new password for you.",
    "Dein Benutzername": "Your user name",
    "Administrator benachrichtigen": "Notify the administrator",
    "Danke – die Nachricht ist raus.": "Thank you — the message has gone out.",
    "Wenn es das Konto gibt, weiß der Administrator jetzt Bescheid und setzt "
    "dir ein neues Passwort. Er sagt dir, wie es lautet.":
        "If the account exists, the administrator now knows and will set a new "
        "password for you, and tell you what it is.",
    "Zu viele Anfragen. Bitte warte eine Stunde.":
        "Too many requests. Please wait an hour.",

    # ---------- Zugang beantragen ----------
    "Antrag ist unterwegs": "Your request is on its way",
    "Die Registrierung ist zurzeit geschlossen. Wende dich an jemanden, der "
    "bereits ein Konto hat.":
        "Registration is closed at the moment. Ask someone who already has an "
        "account.",
    "Ein Administrator schaut ihn sich an und schaltet dein Konto frei. "
    "Danach kannst du dich mit deinem Benutzernamen und Passwort anmelden.":
        "An administrator will look at it and enable your account. After that "
        "you can sign in with your user name and password.",
    "Sag uns kurz, wer du bist – ein Administrator gibt den Zugang danach "
    "frei.":
        "Tell us briefly who you are — an administrator will then grant "
        "access.",
    "Anzeigename": "Display name",
    "Passwort (mindestens 6 Zeichen)": "Password (at least 6 characters)",
    "Mindestens eines von beiden, damit wir dich erreichen können:":
        "At least one of these, so we can reach you:",
    "E-Mail": "E-mail",
    "Telefon": "Phone",
    "Geburtstag (freiwillig)": "Birthday (optional)",
    "Wenn du ihn angibst, erscheint er bei deinen Freunden unter „Termine“. "
    "Ohne Angabe bleibt er einfach leer.":
        "If you give it, it shows up for your friends under „Termine“ "
        "(events). Leave it blank and nothing happens.",
    "Weshalb möchtest du Zugang?": "Why would you like access?",
    "Was wird gespeichert?": "What is stored?",
    "Dies ist ein privater Server. Gespeichert werden Benutzername, "
    "Anzeigename, dein Passwort (nur als Prüfsumme, nicht im Klartext), deine "
    "Kontaktangabe, deine Begründung und – falls angegeben – dein Geburtstag. "
    "Dazu kommt alles, was du später selbst schreibst oder hochlädst: "
    "Nachrichten, Bilder, Dateien, Standorte und Sprachaufnahmen.":
        "This is a private server. What is stored: your user name, your "
        "display name, your password (only as a hash, never in the clear), "
        "your contact details, your reason and — if given — your birthday. "
        "On top of that, everything you write or upload later: messages, "
        "pictures, files, locations and voice recordings.",
    "Sichtbar ist das jeweils nur für die Personen, mit denen du schreibst, "
    "sowie für den Administrator dieses Servers. Die Daten liegen auf dessen "
    "Gerät und werden nicht an Dritte weitergegeben.":
        "All of it is visible only to the people you write with and to the "
        "administrator of this server. The data lives on their machine and is "
        "not passed on to anyone else.",
    "Du kannst jederzeit verlangen, dass dein Konto und deine Beiträge "
    "gelöscht werden – wende dich dazu an den Administrator.":
        "You may ask at any time for your account and your contributions to "
        "be deleted — talk to the administrator.",
    "Ich bin einverstanden, dass meine Angaben zu diesem Zweck gespeichert "
    "werden.":
        "I agree that my details may be stored for this purpose.",
    "Antrag abschicken": "Send the request",
}


def uebersetzt(text, sprache):
    """Der englische Satz - oder der deutsche, wenn keiner hinterlegt ist."""
    if sprache != "en":
        return text
    return EN.get(text, text)
