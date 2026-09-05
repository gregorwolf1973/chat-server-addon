// Nur fuer die Anmelde- und die Registrierseite. Die Oberflaeche selbst
// bringt ihr eigenes Skript mit; hier geht es allein um das Auge am
// Passwortfeld.
//
// Warum eine eigene Datei und kein Skript in der Seite: die
// Inhaltsrichtlinie laesst Skripte nur aus dem Add-on zu.
(function () {
  "use strict";

  // Die Seite sagt, welche Sprache gilt - dieselbe Quelle wie in den Vorlagen
  var EN = document.documentElement.lang === "en";
  var ZEIGEN = EN ? "Show" : "Zeigen";
  var VERBERGEN = EN ? "Hide" : "Verbergen";
  var A_ZEIGEN = EN ? "Show password" : "Passwort anzeigen";
  var A_VERBERGEN = EN ? "Hide password" : "Passwort verbergen";

  document.querySelectorAll('input[type="password"]').forEach(function (feld) {
    var huelle = feld.parentNode;
    if (!huelle) return;
    huelle.classList.add("mit-auge");

    var knopf = document.createElement("button");
    knopf.type = "button";
    knopf.className = "auge";
    knopf.textContent = ZEIGEN;
    knopf.setAttribute("aria-label", A_ZEIGEN);
    // Nicht ins Tabben aufnehmen: wer mit der Tastatur arbeitet, will vom
    // Passwortfeld zum Anmeldeknopf, nicht hierher.
    knopf.tabIndex = -1;

    knopf.addEventListener("click", function () {
      var offen = feld.type === "text";
      feld.type = offen ? "password" : "text";
      knopf.textContent = offen ? ZEIGEN : VERBERGEN;
      knopf.setAttribute("aria-label", offen ? A_ZEIGEN : A_VERBERGEN);
      feld.focus();
    });
    huelle.appendChild(knopf);
  });
})();
