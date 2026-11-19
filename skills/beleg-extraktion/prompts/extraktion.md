Extrahiere Rechnungsfelder. Wähle je Feld den Index des passenden Kandidaten oder null.

---BELEGKOPF---
{{ kopf }}

---SUMMENZEILEN---
{{ summenblock }}

---KANDIDATEN---
Beträge (brutto = Zahlbetrag inkl. USt):  {{ betraege }}
Datumsangaben (DD.MM.JJJJ):               {{ datumsangaben }}
Nummern:                                  {{ nummern }}

Antworte ausschließlich als JSON mit fünf Feldern (Integer oder null):
brutto_idx – Index des Brutto-Gesamtbetrags (der gezahlte Endbetrag inkl. USt)
netto_idx  – Index des Netto-Betrags ohne USt; null wenn nicht ausgewiesen
ust_idx    – Index des Umsatzsteuerbetrags; null wenn keine USt (z. B. Auslandsbeleg)
datum_idx  – Index des Rechnungs-/Belegdatums
nummer_idx – Index der Rechnungs-/Belegnummer
