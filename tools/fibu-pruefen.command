#!/bin/bash
# Fibu-Prüfer – manueller Start per Doppelklick.
#
# Ablauf: Monatsordner im Finder-Dialog wählen -> Prüflauf -> Bericht im Browser öffnen.
# Voraussetzung: Projektumgebung .venv ist eingerichtet (siehe docs/FORTSCHRITT.md, Punkt k).
# Diese Datei liegt im Projekt unter tools/ und findet das Projekt selbst.
# Es werden keine Mails verschickt und keine Zugangsdaten gelesen.

set -u

SKRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJEKT="$(cd "$SKRIPT_DIR/.." && pwd)"
FIBU="$PROJEKT/.venv/bin/fibu"

pause_und_ende() {
  echo
  read -r -n 1 -s -p "Eine Taste drücken zum Schließen …"
  echo
  exit "${1:-0}"
}

if [ ! -x "$FIBU" ]; then
  echo "Programm nicht gefunden: $FIBU"
  echo "Bitte zuerst die Projektumgebung einrichten:"
  echo "  cd \"$PROJEKT\" && python -m venv .venv && source .venv/bin/activate"
  echo "  pip install -c constraints.txt -e \".[dev]\""
  pause_und_ende 1
fi

# Startordner im Dialog: Datenwurzel, falls vorhanden
START="$HOME/fibu-echtdaten"
[ -d "$START" ] || START="$HOME/Downloads/fibu-echtdaten"
[ -d "$START" ] || START="$HOME"

ORDNER="$(osascript - "$START" <<'APPLESCRIPT' 2>/dev/null
on run argv
  set startPfad to item 1 of argv
  set gewaehlt to choose folder with prompt "Monatsordner für die Fibu-Prüfung auswählen (z. B. 08 Aug)" default location (POSIX file startPfad)
  return POSIX path of gewaehlt
end run
APPLESCRIPT
)"

if [ -z "$ORDNER" ]; then
  echo "Keine Auswahl getroffen – abgebrochen."
  pause_und_ende 0
fi
ORDNER="${ORDNER%/}"

echo "Gewählter Ordner: $ORDNER"

if [ ! -d "$ORDNER/BWA" ]; then
  echo
  echo "Hinweis: In diesem Ordner gibt es keinen Unterordner „BWA“."
  echo "Gewählt werden muss der Monatsordner selbst (z. B. „08 Aug“), nicht der Ordner darüber."
  read -r -p "Trotzdem fortfahren? (j/N) " ANTWORT
  case "$ANTWORT" in
    j|J|ja|Ja) ;;
    *) echo "Abgebrochen."; pause_und_ende 0 ;;
  esac
fi

echo
echo "Prüflauf startet …"
echo

# Das Programm sucht die Skills relativ zum Arbeitsverzeichnis.
cd "$PROJEKT" || pause_und_ende 1

LOG="$(mktemp)"
"$FIBU" pruefen --ordner "$ORDNER" 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}

# Pfad des HTML-Berichts aus der Ausgabe lesen (Zeilen enden auf .html)
HTML="$(grep -E '\.html[[:space:]]*$' "$LOG" | tail -1 | sed -E 's/^.*->[[:space:]]*//; s/^[[:space:]]+//; s/[[:space:]]+$//')"
rm -f "$LOG"

echo
if [ -n "$HTML" ] && [ -f "$HTML" ]; then
  echo "Bericht: $HTML"
  open "$HTML"
else
  echo "Kein Bericht gefunden. Bitte die Ausgabe oben prüfen."
fi

# Exit-Code: 0 = ohne Fehlerbefund, sonst Befunde (das ist normal) – hier nur zur Information.
echo "Beendet mit Code $RC (ungleich 0 bedeutet: Befunde der Stufe Fehler, kein Programmabsturz)."
pause_und_ende 0
