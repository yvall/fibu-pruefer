# fibu_pruefer – Prüfung der Steuerberater-Buchhaltung (MVP)

## Ordnerlayout
```
<Wurzel>/
  08 Aug/              <- ein Periodenordner
    BWA/               <- Auswertungs-PDF des Steuerberaters
    Allgemein/ CA/ MA/ YV/   <- Belege & Gutschriften (Kostenstelle wird ignoriert)
    Pruefbericht/      <- wird erzeugt (.md + .html)
```
## Benutzung
    pip install -r requirements.txt
    python -m fibu_pruefer pruefen "<Wurzel>/08 Aug"        # einmalige Prüfung (Exitcode 0/1/2 = ok/prüfen/Fehler)
    python -m fibu_pruefer watch "<Wurzel>" --intervall 60  # automatisch bei neuer BWA / neuen Belegen
    python -m fibu_pruefer watch "<Wurzel>" --mail          # zusätzlich IMAP-Eingang + SMTP-Versand (Env-Variablen siehe mail_fetch.py)
    --llm                                                   # Zusammenfassung via lokalem Ollama (OLLAMA_MODEL, OLLAMA_URL)

## Prüfblöcke (alle deterministisch)
BWA-Rechenwege · Wertenachweis↔BWA↔Summen/Salden · Soll=Haben/Salden · UStVA↔Konten (Kz 81/66/46/67/83, 3806/1406/3820/3860)
· OPOS↔Sachkonten, Dubletten, Überfälligkeit, Periodenabgrenzung · Jahreskonten (Durchlaufposten) · Saldenrichtung
· Entwicklungsübersicht (Summen, Ausreißer) · Belege↔OPOS (Nr./Betrag), Rückfragen-Aufschlüsselung per Summenkombination.

## Zusätzlich (Echtdaten-Stand)
- Liegt neben der August-BWA auch die Vormonats-BWA im BWA-Ordner, wird sie automatisch als Vormonat erkannt: Fortschreibung (kum. Vormonat + Monat = kum. Berichtsmonat) je BWA-Zeile und Konto, Erkennung nachträglicher Buchungen in Vormonaten.
- Unabhängige Ergebnisherleitung aus den GuV-Konten (Klassen 4–8) für Monat und Jahr.
- Umsatzbeweis: Netto der Gutschriften des Leistungsmonats ↔ Erlöskonten 44xx; Ersatz-/Eigenbelege werden als solche markiert.
- Excel „Ungeklärte Posten“ (Dateiname enthält „Klärung/ungeklärt“) wird mit Konto 1370, Umbuchungen und Belegen abgeglichen.
- OCR-Texte der Belege werden je Datei-Hash in `.fibu_cache/` zwischengespeichert (erster Lauf langsam, Folgeläufe ~20 s).

## Grenzen
Seiten ohne Textebene werden per OCR gelesen (im Bericht gekennzeichnet). IMAP/SMTP/Ollama sind implementiert, aber nicht gegen echte Server getestet.
