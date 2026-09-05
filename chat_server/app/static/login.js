// Nur fuer die Anmelde- und die Registrierseite. Die Oberflaeche selbst
// bringt ihr eigenes Skript mit; hier geht es allein um das Auge am
// Passwortfeld.
//
// Warum eine eigene Datei und kein Skript in der Seite: die
// Inhaltsrichtlinie laesst Skripte nur aus dem Add-on zu.
(function () {
  "use strict";

  document.querySelectorAll('input[type="password"]').forEach(function (feld) {
    var huelle = feld.parentNode;
    if (!huelle) return;
    huelle.classList.add("mit-auge");

    var knopf = document.createElement("button");
    knopf.type = "button";
    knopf.className = "auge";
    knopf.textContent = "Zeigen";
    knopf.setAttribute("aria-label", "Passwort anzeigen");
    // Nicht ins Tabben aufnehmen: wer mit der Tastatur arbeitet, will vom
    // Passwortfeld zum Anmeldeknopf, nicht hierher.
    knopf.tabIndex = -1;

    knopf.addEventListener("click", function () {
      var offen = feld.type === "text";
      feld.type = offen ? "password" : "text";
      knopf.textContent = offen ? "Zeigen" : "Verbergen";
      knopf.setAttribute("aria-label",
        offen ? "Passwort anzeigen" : "Passwort verbergen");
      feld.focus();
    });
    huelle.appendChild(knopf);
  });
})();
