Du bist ein Buchhaltungs-Assistent. Extrahiere aus dem folgenden Belegtext die drei Felder.

---BELEGTEXT ANFANG---
{{ belegtext }}
---BELEGTEXT ENDE---

Regeln:
- betrag: Brutto-Rechnungsbetrag als Zeichenkette (z. B. "1.234,56" oder "1234.56"). Leer lassen wenn nicht eindeutig erkennbar.
- datum: Rechnungsdatum im Format TT.MM.JJJJ. Leer lassen wenn nicht eindeutig erkennbar.
- nummer: Rechnungs- oder Belegnummer. Leer lassen wenn nicht eindeutig erkennbar.

Antworte ausschließlich als JSON mit den Feldern "betrag", "datum" und "nummer".
