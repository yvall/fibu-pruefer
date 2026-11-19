Extrahiere Rechnungsfelder. Wähle je Feld den Index des passenden Kandidaten oder null.

---BELEGKOPF---
{{ kopf }}

---SUMMENZEILEN---
{{ summenblock }}

---KANDIDATEN---
Datumsangaben (DD.MM.JJJJ):  {{ datumsangaben }}
Nummern:                      {{ nummern }}

Antworte ausschließlich als JSON mit zwei Feldern (Integer oder null):
datum_idx  – Index des Rechnungs-/Belegdatums
nummer_idx – Index der Rechnungs-/Belegnummer
