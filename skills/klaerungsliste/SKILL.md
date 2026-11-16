---
name: klaerungsliste
description: >
  Gleicht die Klärungsliste „Ungeklärte Posten" gegen Konto 1370, Belege
  und rückwirkend geänderte Konten ab.
kind: code
runs_after:
  - vormonat-fortschreibung
severity_default: pruefen
inputs:
  - auswertung.jahreskonten
  - auswertung.sus
  - context.belege
  - context.klaerung
  - context.changed_accounts
---
