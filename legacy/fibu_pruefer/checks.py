"""Deterministische Prüfregeln. Kein LLM – jede Aussage ist nachrechenbar."""
from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from .parser import ZERO, Auswertung, Konto

TOL = Decimal("0.02")
ORDER = {"fehler": 0, "pruefen": 1, "info": 2}


def eur(v: Decimal | None) -> str:
    if v is None:
        return "–"
    s = f"{v:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def pdate(s: str) -> date | None:
    for fmt in ("%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def close(a: Decimal, b: Decimal, tol: Decimal = TOL) -> bool:
    return abs(a - b) <= tol


@dataclass
class Finding:
    severity: str        # fehler | pruefen | info
    title: str
    detail: str
    ref: str = ""        # z. B. Konto / Seite


@dataclass
class CheckResult:
    key: str
    name: str
    tests: int = 0
    findings: list[Finding] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def test(self, ok: bool, severity: str, title: str, detail: str, ref: str = "") -> bool:
        self.tests += 1
        if not ok:
            self.findings.append(Finding(severity, title, detail, ref))
        return ok

    @property
    def status(self) -> str:
        if not self.findings:
            return "ok"
        return min((f.severity for f in self.findings), key=lambda s: ORDER[s])


# ----------------------------------------------------------------------------------------

def _g(a: Auswertung, label: str, idx: int) -> Decimal | None:
    v = a.bwa.get(label)
    return v[idx] if v else None


def check_bwa_arithmetik(a: Auswertung) -> CheckResult:
    r = CheckResult("bwa", "BWA – Rechenwege (Monat und kumuliert)")
    cost_lines = ["Personalkosten", "Raumkosten", "Betriebl. Steuern", "Versich./Beiträge", "Besondere Kosten",
                  "Fahrzeugko. (o. St)", "Werbe-/Reisekosten", "Kosten Warenabgabe", "Abschreibungen",
                  "Reparatur/Instandh.", "Sonstige Kosten"]
    if not a.bwa:
        r.test(False, "fehler", "BWA nicht lesbar", "Die BWA-Seite konnte nicht ausgewertet werden.")
        return r
    for idx, per in ((0, f"{a.month:02d}/{a.year}"), (1, f"Jan–{a.month:02d}/{a.year}")):
        def v(l: str) -> Decimal:
            x = _g(a, l, idx)
            return x if x is not None else ZERO
        rules = [
            ("Gesamtleistung", v("Umsatzerlöse") + v("Best.Verdg. FE/UE") + v("Akt.Eigenleistungen"), "Umsatz + Bestandsveränd. + Eigenleistungen"),
            ("Rohertrag", v("Gesamtleistung") - v("Mat./Wareneinkauf"), "Gesamtleistung − Wareneinkauf"),
            ("Betriebl. Rohertrag", v("Rohertrag") + v("So. betr. Erlöse"), "Rohertrag + sonst. betr. Erlöse"),
            ("Gesamtkosten", sum((v(c) for c in cost_lines), ZERO), "Summe der Kostenarten"),
            ("Betriebsergebnis", v("Betriebl. Rohertrag") - v("Gesamtkosten"), "Betriebl. Rohertrag − Gesamtkosten"),
            ("Neutraler Aufwand", v("Zinsaufwand") + v("Sonst. neutr. Aufw"), "Zinsaufwand + sonst. neutr. Aufwand"),
            ("Neutraler Ertrag", v("Zinserträge") + v("Sonst. neutr. Ertr") + v("Verr. kalk. Kosten"), "Zinserträge + sonst. neutr. Erträge + verr. kalk. Kosten"),
            ("Ergebnis vor Steuern", v("Betriebsergebnis") - v("Neutraler Aufwand") + v("Neutraler Ertrag") + v("Kontenkl. unbesetzt"), "Betriebsergebnis − neutr. Aufwand + neutr. Ertrag"),
            ("Vorläufiges Ergebnis", v("Ergebnis vor Steuern") - v("Steuern Eink.u.Ertr"), "Ergebnis vor Steuern − Ertragsteuern"),
        ]
        for label, calc, how in rules:
            if label not in a.bwa:
                continue
            shown = v(label)
            r.test(close(shown, calc), "fehler", f"BWA {per}: „{label}“ stimmt nicht",
                   f"Ausgewiesen {eur(shown)}, nachgerechnet {eur(calc)} ({how}); Differenz {eur(shown - calc)}.", "BWA")
    return r


def _fuzzy(label: str, known: list[str]) -> str | None:
    import difflib
    if label in known:
        return label
    m = difflib.get_close_matches(label, known, n=1, cutoff=0.7)
    return m[0] if m else None


def check_wertenachweis(a: Auswertung) -> CheckResult:
    r = CheckResult("wertenachweis", "Wertenachweis – Konten ↔ BWA-Zeilen")
    for g in a.wgroups:
        sev = "pruefen" if g.ocr else "fehler"
        note = " (Seite per OCR gelesen – ggf. Lesefehler)" if g.ocr else ""
        sp = sum((k["per"] for k in g.kontos), ZERO)
        sy = sum((k["ytd"] for k in g.kontos), ZERO)
        if g.bwa_per is not None:
            r.test(close(sp, g.bwa_per), sev, f"Zeile {g.zeile} {g.name}: Konten ≠ BWA-Wert (Monat)",
                   f"Summe der Konten {eur(sp)}, BWA-Zeile {eur(g.bwa_per)}{note}.", f"Zeile {g.zeile}")
        if g.bwa_ytd is not None:
            r.test(close(sy, g.bwa_ytd), sev, f"Zeile {g.zeile} {g.name}: Konten ≠ BWA-Wert (kumuliert)",
                   f"Summe der Konten {eur(sy)}, BWA-Zeile {eur(g.bwa_ytd)}{note}.", f"Zeile {g.zeile}")
        lab = _fuzzy(g.name, list(a.bwa))
        if lab and g.bwa_per is not None:
            r.test(close(a.bwa[lab][0], g.bwa_per), sev, f"Zeile {g.zeile} {g.name}: Wertenachweis ≠ BWA-Seite",
                   f"BWA-Seite {eur(a.bwa[lab][0])}, Wertenachweis {eur(g.bwa_per)}{note}.", f"Zeile {g.zeile}")
        if lab and g.bwa_ytd is not None:
            r.test(close(a.bwa[lab][1], g.bwa_ytd), sev, f"Zeile {g.zeile} {g.name}: Wertenachweis ≠ BWA-Seite (kum.)",
                   f"BWA-Seite {eur(a.bwa[lab][1])}, Wertenachweis {eur(g.bwa_ytd)}{note}.", f"Zeile {g.zeile}")
        # Konto gegen Summen & Salden
        for k in g.kontos:
            sk = a.sus.get(k["nr"])
            if not sk:
                continue
            sign = 1 if k["sh"] == "S" else -1
            exp_p, exp_y = sign * sk.per_move, sign * sk.ytd_move
            r.test(close(k["per"], exp_p), sev, f"Konto {k['nr']} {k['name']}: Wertenachweis ≠ Summen/Salden (Monat)",
                   f"Wertenachweis {eur(k['per'])}, Summen/Salden {eur(exp_p)}{note}.", f"Konto {k['nr']}")
            r.test(close(k["ytd"], exp_y), sev, f"Konto {k['nr']} {k['name']}: Wertenachweis ≠ Summen/Salden (kum.)",
                   f"Wertenachweis {eur(k['ytd'])}, Summen/Salden {eur(exp_y)}{note}.", f"Konto {k['nr']}")
    return r


def check_summen_salden(a: Auswertung) -> CheckResult:
    r = CheckResult("sus", "Summen & Salden – interne Konsistenz")
    sach = {n: k for n, k in a.sus.items() if len(n) <= 4}
    for n, k in a.sus.items():
        calc = k.eb + k.ytd_soll - k.ytd_haben
        r.test(close(calc, k.saldo), "fehler", f"Konto {n} {k.name}: Saldo passt nicht zu EB + Bewegungen",
               f"EB {eur(k.eb)} + Soll {eur(k.ytd_soll)} − Haben {eur(k.ytd_haben)} = {eur(calc)}, ausgewiesen {eur(k.saldo)}.", f"Konto {n}")
    ps = sum((k.per_soll for k in sach.values()), ZERO)
    ph = sum((k.per_haben for k in sach.values()), ZERO)
    ys = sum((k.ytd_soll for k in sach.values()), ZERO)
    yh = sum((k.ytd_haben for k in sach.values()), ZERO)
    r.test(close(ps, ph), "fehler", "Soll ≠ Haben im Monat", f"Soll {eur(ps)}, Haben {eur(ph)}.")
    r.test(close(ys, yh), "fehler", "Soll ≠ Haben kumuliert", f"Soll {eur(ys)}, Haben {eur(yh)}.")
    r.test(close(sum((k.eb for k in sach.values()), ZERO), ZERO), "fehler", "Eröffnungsbilanz nicht ausgeglichen",
           "Summe der EB-Werte ist ungleich 0.")
    r.test(close(sum((k.saldo for k in sach.values()), ZERO), ZERO), "fehler", "Saldensumme ≠ 0",
           "Summe aller Salden (Soll − Haben) ist ungleich 0.")
    if a.sus_total.get("per_soll") is not None:
        r.test(close(ps, a.sus_total["per_soll"]), "pruefen", "Summenzeile (Monat Soll) ≠ Summe der Konten",
               f"Konten {eur(ps)}, Summenzeile {eur(a.sus_total['per_soll'])}.")
        r.test(close(ys, a.sus_total.get("ytd_soll", ys)), "pruefen", "Summenzeile (kum. Soll) ≠ Summe der Konten",
               f"Konten {eur(ys)}, Summenzeile {eur(a.sus_total.get('ytd_soll'))}.")
    # Personenkonten ↔ Sammelkonten
    for first, sammel, label in (("1", "1200", "Debitoren"), ("7", "3300", "Kreditoren")):
        person = [k for n, k in a.sus.items() if len(n) == 5 and n.startswith(first)]
        if person and sammel in a.sus:
            s = sum((k.saldo for k in person), ZERO)
            r.test(close(s, a.sus[sammel].saldo), "fehler", f"{label}: Personenkonten ≠ Sammelkonto {sammel}",
                   f"Summe Personenkonten {eur(s)}, Konto {sammel} {eur(a.sus[sammel].saldo)}.", f"Konto {sammel}")
    return r


ANOMALY_EXPECT = {"0": 1, "1": 1, "3": -1, "4": -1, "6": 1, "7": 1}
ANOMALY_SKIP = {"2910", "3820", "3830", "4946", "1370", "6850_"}


def check_kontenrichtung(a: Auswertung) -> CheckResult:
    r = CheckResult("richtung", "Saldenrichtung / auffällige Buchungssummen")
    for n, k in a.sus.items():
        if len(n) > 4 or n in ANOMALY_SKIP:
            continue
        exp = ANOMALY_EXPECT.get(n[0])
        if exp and abs(k.saldo) >= Decimal("1.00") and (k.saldo > 0) != (exp > 0):
            side = "Haben" if k.saldo < 0 else "Soll"
            r.test(False, "pruefen", f"Konto {n} {k.name}: ungewöhnlicher {side}-Saldo",
                   f"Saldo {eur(abs(k.saldo))} {side[0]}, erwartet wäre die Gegenseite. Bitte Kontierung/Gegenbuchung prüfen.", f"Konto {n}")
        else:
            r.tests += 1
    for n, k in a.sus.items():
        if k.per_soll < 0 or k.per_haben < 0:
            r.test(False, "info", f"Konto {n} {k.name}: negative Monatssumme",
                   f"Soll {eur(k.per_soll)} / Haben {eur(k.per_haben)} – deutet auf Storno/Gegenbuchung hin.", f"Konto {n}")
    for n, k in a.sus.items():
        if len(n) == 5 and n.startswith(("1", "7")) and abs(k.saldo) >= Decimal("1.00") and (n.startswith("1") != (k.saldo > 0)):
            r.test(False, "pruefen", f"Personenkonto {n} {k.name}: Saldo auf der „falschen“ Seite",
                   f"Saldo {eur(k.saldo)} (Soll +, Haben −).", f"Konto {n}")
    return r


def _sum_rev19(a: Auswertung) -> Decimal:
    return sum((k.per_haben - k.per_soll for n, k in a.sus.items() if n.startswith("4") and len(n) == 4 and "19" in k.name and "%" in k.name), ZERO)


def check_ustva(a: Auswertung) -> CheckResult:
    r = CheckResult("ustva", "Umsatzsteuer-Voranmeldung ↔ Buchhaltung")
    if not a.ustva:
        r.test(False, "pruefen", "UStVA-Seiten nicht gefunden", "Keine UStVA-Werte im PDF erkannt.")
        return r
    sus = a.sus
    def per(nr: str, side: str) -> Decimal:
        k = sus.get(nr)
        return (k.per_soll if side == "S" else k.per_haben) if k else ZERO
    z81 = a.ustva.get("81", {})
    if z81.get("base") is not None:
        rev = _sum_rev19(a)
        r.test(close(Decimal(z81["base"]), rev, Decimal("1.00")), "fehler", "Kz. 81 ≠ Erlöse 19 % laut Buchhaltung",
               f"UStVA-Bemessung {eur(Decimal(z81['base']))}, Erlöskonten 19 % {eur(rev)}.", "UStVA Kz. 81")
        calc = (Decimal(z81["base"]) * Decimal("0.19")).quantize(Decimal("0.01"), ROUND_HALF_UP)
        r.test(close(calc, z81["tax"], Decimal("0.05")), "fehler", "Kz. 81: Steuer ≠ 19 % der Bemessung",
               f"19 % von {eur(Decimal(z81['base']))} = {eur(calc)}, gemeldet {eur(z81['tax'])}.", "UStVA Kz. 81")
        r.test(close(per("3806", "H"), z81["tax"]), "fehler", "Kz. 81 ≠ Konto 3806 (Umsatzsteuer 19 %)",
               f"Konto 3806 Haben {eur(per('3806', 'H'))}, UStVA {eur(z81['tax'])}.", "Konto 3806")
        forderung = per("1200", "S")
        exp = (rev * Decimal("1.19")).quantize(Decimal("0.01"), ROUND_HALF_UP)
        r.test(close(forderung, exp, Decimal("0.05")), "pruefen", "Forderungs-Zugang ≠ Erlöse × 1,19",
               f"Konto 1200 Soll {eur(forderung)}, Erlöse brutto {eur(exp)} – es könnten Erlöse ohne Rechnung oder Rechnungen ohne Erlös gebucht sein.", "Konto 1200")
    z66 = a.ustva.get("66", {})
    if z66.get("tax") is not None:
        vs = per("1406", "S") + per("1401", "S")
        r.test(close(vs, z66["tax"]), "fehler", "Kz. 66 ≠ abziehbare Vorsteuer (Konten 1401/1406)",
               f"Konten {eur(vs)}, UStVA {eur(z66['tax'])}.", "UStVA Kz. 66")
    z46, z67 = a.ustva.get("46", {}), a.ustva.get("67", {})
    if z46.get("tax") is not None:
        r.test(close(per("3837", "H"), z46["tax"]), "fehler", "Kz. 46 ≠ Konto 3837 (USt § 13b)", f"Konto 3837 {eur(per('3837', 'H'))}, UStVA {eur(z46['tax'])}.", "UStVA Kz. 46")
        base = z46.get("base")
        if base is not None:
            c = (Decimal(base) * Decimal("0.19")).quantize(Decimal("0.01"), ROUND_HALF_UP)
            r.test(close(c, z46["tax"], Decimal("0.05")), "fehler", "Kz. 46: Steuer ≠ 19 % der Bemessung", f"19 % von {base} = {eur(c)}, gemeldet {eur(z46['tax'])}.", "UStVA Kz. 46")
    if z67.get("tax") is not None:
        r.test(close(per("1407", "S"), z67["tax"]), "fehler", "Kz. 67 ≠ Konto 1407 (Vorsteuer § 13b)", f"Konto 1407 {eur(per('1407', 'S'))}, UStVA {eur(z67['tax'])}.", "UStVA Kz. 67")
    tax = lambda kz: (a.ustva.get(kz) or {}).get("tax") or ZERO
    zahl = tax("81") + tax("46") - tax("66") - tax("67")
    z83 = tax("83")
    r.test(close(zahl, z83), "fehler", "Zahllast falsch berechnet", f"Berechnet {eur(zahl)}, Kz. 83 {eur(z83)}.", "UStVA Kz. 83")
    if a.ustva_zahllast is not None:
        r.test(close(a.ustva_zahllast, z83), "fehler", "Verbleibender Betrag ≠ Kz. 83", f"{eur(a.ustva_zahllast)} vs. {eur(z83)}.")
    proto = (a.ustva.get("83_protokoll") or {}).get("tax")
    if proto is not None:
        r.test(close(proto, z83), "fehler", "Übermittlungsprotokoll ≠ UStVA-Werte", f"Protokoll {eur(proto)}, Werte {eur(z83)}.")
    if a.letter_amount is not None:
        r.test(close(a.letter_amount, z83), "fehler", "Betrag im Anschreiben ≠ Kz. 83", f"Anschreiben {eur(a.letter_amount)}, UStVA {eur(z83)}.")
    r.test(close(per("3820", "S"), z83), "pruefen", "Konto 3820 (USt-Vorauszahlung) ≠ Kz. 83", f"Konto 3820 Soll {eur(per('3820', 'S'))}, UStVA {eur(z83)}.", "Konto 3820")
    # Verbindlichkeit USt
    k3860 = sus.get("3860")
    if k3860:
        offen = -k3860.saldo
        if offen - z83 > Decimal("0.02"):
            r.test(False, "pruefen", "Konto 3860: USt-Verbindlichkeit höher als die aktuelle Zahllast",
                   f"Saldo {eur(offen)} H, Zahllast {eur(z83)} → {eur(offen - z83)} ohne erkennbaren Zahlungsbezug "
                   f"(Vormonats-Zahllast nicht gezahlt/gebucht, Dauerfristverlängerung, Zahlung falsch kontiert?). "
                   f"Zahlungen im Monat: {eur(k3860.per_soll)}.", "Konto 3860")
        else:
            r.tests += 1
    # Datumslogik
    if a.ustva_datum:
        d = pdate(a.ustva_datum)
        import re as _re
        m = _re.search(r"eingezogen", " ".join(l.text for l in a.pages[0].lines)) if a.pages else None
        txt = a.pages[0].text if a.pages else ""
        mm = _re.search(r"am\s+(\d{2}\.\d{2}\.\d{4})\s+vom\s+Finanzamt", txt)
        if mm and d and pdate(mm.group(1)) and pdate(mm.group(1)) < d:
            r.test(False, "info", "Lastschrift vor Übermittlungsdatum",
                   f"Anschreiben: Einzug am {mm.group(1)}, Übermittlung laut Protokoll am {a.ustva_datum}. "
                   f"Bitte prüfen, ob Fristende/Dauerfristverlängerung korrekt berücksichtigt ist.")
    return r


def check_opos(a: Auswertung) -> CheckResult:
    r = CheckResult("opos", "Offene Posten (Debitoren/Kreditoren)")
    ref = pdate(a.created) or date.today()
    end = date(a.year, a.month, 28)
    # Monatsende
    import calendar
    end = date(a.year, a.month, calendar.monthrange(a.year, a.month)[1]) if a.year else ref
    by: dict[str, list] = defaultdict(list)
    for it in a.opos:
        by[it.konto].append(it)
    for nr, items in by.items():
        s = sum((i.soll - i.haben for i in items), ZERO)
        k = a.sus.get(nr)
        if k:
            r.test(close(s, k.saldo), "fehler", f"OPOS Konto {nr} ({items[0].konto_name}) ≠ Summen/Salden",
                   f"Offene Posten {eur(s)}, Saldo {eur(k.saldo)}.", f"Konto {nr}")
    for first, sammel, label in (("1", "1200", "Debitoren"), ("7", "3300", "Kreditoren")):
        s = sum((i.soll - i.haben for i in a.opos if i.konto.startswith(first)), ZERO)
        if sammel in a.sus and any(i.konto.startswith(first) for i in a.opos):
            r.test(close(s, a.sus[sammel].saldo), "fehler", f"OPOS {label} gesamt ≠ Sachkonto {sammel}",
                   f"OPOS {eur(s)}, Sachkonto {eur(a.sus[sammel].saldo)}.", f"Konto {sammel}")
    overdue: list = []
    seen: dict[tuple[str, str], int] = defaultdict(int)
    for it in a.opos:
        if it.belegnr:
            seen[(it.konto, it.belegnr)] += 1
    for (kto, nr), n in seen.items():
        r.test(n == 1, "fehler", f"Rechnungsnummer {nr} doppelt auf Konto {kto}", f"{n} offene Posten mit identischer Nummer.", f"Konto {kto}")
    for it in a.opos:
        if it.konto.startswith("1") and it.soll > 0:
            d = pdate(it.datum)
            if d and d > end:
                r.test(False, "info", f"Rechnung {it.belegnr} ({it.konto_name}) datiert nach Periodenende, aber im {a.month:02d}/{a.year} gebucht",
                       f"Rechnungsdatum {it.datum}, Betrag {eur(it.soll)}. Zulässig bei Leistung im Berichtsmonat (Soll-Versteuerung) – "
                       f"Leistungsmonat anhand der Gutschrift/Rechnung prüfen.", f"Konto {it.konto}")
            f = pdate(it.faellig)
            if f and f < ref:
                overdue.append((it, (ref - f).days))
    if overdue:
        total = sum((i.soll for i, _ in overdue), ZERO)
        lines = "; ".join(f"{i.konto_name} {i.belegnr} {eur(i.soll)} ({d} Tage)" for i, d in sorted(overdue, key=lambda x: -x[1]))
        r.test(False, "pruefen", f"{len(overdue)} überfällige Forderungen, zusammen {eur(total)}",
               f"Stand {ref:%d.%m.%Y}: {lines}. Zahlungseingänge auf dem Bankkonto prüfen – evtl. bereits bezahlt, aber nicht ausgeziffert; sonst Mahnwesen.",
               "OPOS")
    return r


def check_durchlaufend(a: Auswertung) -> CheckResult:
    r = CheckResult("jahreskonto", "Jahreskonten (z. B. Durchlaufende Posten)")
    ref = pdate(a.created) or date.today()
    for jk in a.jahreskonten:
        r.test(close(jk.saldo, jk.eb + jk.jvz_soll - jk.jvz_haben), "fehler", f"Konto {jk.nr} {jk.name}: Saldo rechnerisch falsch",
               f"EB + Soll − Haben = {eur(jk.eb + jk.jvz_soll - jk.jvz_haben)}, ausgewiesen {eur(jk.saldo)}.", f"Konto {jk.nr}")
        es = sum((e["soll"] for e in jk.entries), ZERO)
        eh = sum((e["haben"] for e in jk.entries), ZERO)
        r.test(close(es, jk.jvz_soll) and close(eh, jk.jvz_haben), "fehler", f"Konto {jk.nr}: Einzelposten ≠ Summenzeile",
               f"Einzelposten Soll {eur(es)} / Haben {eur(eh)}, Summenzeile {eur(jk.jvz_soll)} / {eur(jk.jvz_haben)}.", f"Konto {jk.nr}")
        if abs(jk.saldo) > TOL:
            offene = "; ".join(f"{e['datum']} {e['text'][:40]} {eur(e['soll'] - e['haben'])}" for e in jk.entries)
            r.test(False, "pruefen", f"Konto {jk.nr} {jk.name}: offener Saldo {eur(abs(jk.saldo))} {'H' if jk.saldo < 0 else 'S'}",
                   f"Durchlaufposten sollten sich ausgleichen. Offene Einzelposten: {offene}.", f"Konto {jk.nr}")
        groups: dict[tuple, int] = defaultdict(int)
        for e in jk.entries:
            groups[(e["datum"], e["soll"], e["haben"], e["text"])] += 1
        for (d, s, h, t), n in groups.items():
            if n > 1:
                r.test(False, "pruefen", f"Konto {jk.nr}: {n}× identische Buchung {d} {eur(s or h)}",
                       f"„{t}“ – mögliche Doppelbuchung bzw. Sammelzahlung, die auf Einzelrechnungen aufgeteilt werden müsste.", f"Konto {jk.nr}")
        old = [e for e in jk.entries if (pdate(e["datum"]) and (ref - pdate(e["datum"])).days > 60)]
        if old and abs(jk.saldo) > TOL:
            r.test(False, "info", f"Konto {jk.nr}: {len(old)} Posten seit mehr als 60 Tagen offen",
                   "; ".join(f"{e['datum']} {e['text'][:35]} {eur(e['soll'] - e['haben'])}" for e in old), f"Konto {jk.nr}")
        for e in jk.entries:
            if "erl" in e["text"].lower() and "bitte" in e["text"].lower():
                r.test(False, "info", f"Konto {jk.nr}: Klärungsvermerk des Steuerberaters", f"{e['datum']} „{e['text']}“", f"Konto {jk.nr}")
    return r


def check_entwicklung(a: Auswertung) -> CheckResult:
    r = CheckResult("entwicklung", "Entwicklungsübersicht – Summen und Ausreißer")
    if not a.entwicklung:
        r.test(False, "pruefen", "Entwicklungsübersicht nicht lesbar", "Keine 13-Monats-Zeilen erkannt.")
        return r
    ocr = 6 in a.ocr_pages or any(p in a.ocr_pages for p in range(1, 99) if a.page_types.get(p) == "entwicklung")
    sev = "pruefen" if ocr else "fehler"
    note = " (OCR-Seite)" if ocr else ""
    outlier: list[tuple[str, Decimal, Decimal, Decimal, Decimal]] = []
    skip_outlier = {"Gesamtleistung", "Rohertrag", "Betriebl. Rohertrag", "Gesamtkosten", "Ergebnis vor Steuern"}
    for lab, vals in a.entwicklung.items():
        bw = a.bwa.get(lab)
        if bw:
            r.test(close(vals[-1], bw[0], Decimal("0.05")), sev, f"{lab}: Monatswert Entwicklungsübersicht ≠ BWA",
                   f"Entwicklung {eur(vals[-1])}, BWA {eur(bw[0])}{note}.", "Entwicklungsübersicht")
            ytd = sum(vals[-a.month:], ZERO)
            r.test(close(ytd, bw[1], Decimal("0.05")), sev, f"{lab}: Summe Jan–{a.month:02d} ≠ kumulierter BWA-Wert",
                   f"Σ Monate {eur(ytd)}, BWA kumuliert {eur(bw[1])}{note}.", "Entwicklungsübersicht")
        if lab in skip_outlier:
            continue
        prev = vals[:-1]
        if not any(prev):
            continue
        med = Decimal(str(statistics.median([float(x) for x in prev])))
        lo, hi = min(prev), max(prev)
        cur = vals[-1]
        if (cur < lo or cur > hi) and abs(cur - med) >= Decimal("250") and abs(cur - med) >= abs(med) * Decimal("0.15"):
            outlier.append((lab, cur, med, lo, hi))
    for lab, cur, med, lo, hi in outlier:
        r.test(False, "info", f"{lab}: Monatswert außerhalb der 12-Monats-Spanne",
               f"{eur(cur)} (Median Vormonate {eur(med)}, Spanne {eur(lo)} … {eur(hi)}).", "Entwicklungsübersicht")
    # auffällige Einzelmonate (z. B. Rückstellungsauflösung) – Hinweis
    pk = a.entwicklung.get("Personalkosten")
    if pk:
        med = Decimal(str(statistics.median([float(x) for x in pk])))
        for m, v in zip(a.entw_months, pk):
            if abs(v - med) > Decimal("10000"):
                r.test(False, "info", f"Personalkosten {m}: stark abweichend ({eur(v)})",
                       f"Median {eur(med)}. Bei Abweichung > 10.000 € Rückstellungsbuchung/Tantieme/Einmalzahlung belegen lassen "
                       f"(Konten 3074/6026 in Summen & Salden).", "Entwicklungsübersicht")
    return r


def check_ergebnis_aus_konten(a: Auswertung) -> CheckResult:
    """Unabhängiger Beweis: Ergebnis aus den GuV-Konten (4–8) ≙ Ergebnis der BWA."""
    r = CheckResult("ergebnis", "Monats- und Jahresergebnis – unabhängige Herleitung aus den Konten")
    guv = {n: k for n, k in a.sus.items() if len(n) == 4 and n[0] in "45678"}
    lab = "Vorläufiges Ergebnis"
    if not guv or lab not in a.bwa:
        r.test(False, "pruefen", "Ergebnisherleitung nicht möglich", "GuV-Konten oder BWA-Ergebniszeile fehlen.")
        return r
    mon = sum((k.per_haben - k.per_soll for k in guv.values()), ZERO)
    ytd = sum((k.ytd_haben - k.ytd_soll for k in guv.values()), ZERO)
    r.test(close(mon, a.bwa[lab][0]), "fehler", f"Monatsergebnis {a.month:02d}/{a.year} stimmt nicht",
           f"Aus den GuV-Konten (Klassen 4–8) ergibt sich {eur(mon)}, die BWA weist {eur(a.bwa[lab][0])} aus (Differenz {eur(a.bwa[lab][0] - mon)}).", "Summen & Salden ↔ BWA")
    r.test(close(ytd, a.bwa[lab][1]), "fehler", f"Jahresergebnis Jan–{a.month:02d}/{a.year} stimmt nicht",
           f"Aus den GuV-Konten ergibt sich {eur(ytd)}, die BWA weist {eur(a.bwa[lab][1])} aus (Differenz {eur(a.bwa[lab][1] - ytd)}).", "Summen & Salden ↔ BWA")
    return r


def check_vormonat(a: Auswertung, p: Auswertung | None) -> CheckResult:
    r = CheckResult("vormonat", "Vormonats-Fortschreibung (Juli → August) und nachträgliche Änderungen")
    if p is None:
        r.test(False, "info", "Keine Vormonats-BWA im BWA-Ordner", "Fortschreibung Vormonat → Berichtsmonat und Rückwirkungsprüfung wurden übersprungen.")
        return r
    if (p.year, p.month) != ((a.year, a.month - 1) if a.month > 1 else (a.year - 1, 12)):
        r.test(False, "info", "Vormonats-BWA nicht unmittelbar vorhergehend", f"Vorhanden: {p.month:02d}/{p.year}, Berichtsmonat {a.month:02d}/{a.year}.")
        return r
    same_year = p.year == a.year
    # 1) BWA-Zeilen: kum. Vormonat + Monat = kum. aktuell
    if same_year:
        for lab, (per, ytd) in a.bwa.items():
            if lab in p.bwa:
                exp = p.bwa[lab][1] + per
                tag = "Jahresergebnis" if lab == "Vorläufiges Ergebnis" else lab
                r.test(close(exp, ytd), "fehler", f"{tag}: kum. Vormonat + Monat ≠ kum. Berichtsmonat",
                       f"kum. {p.month:02d}: {eur(p.bwa[lab][1])} + Monat {eur(per)} = {eur(exp)}, ausgewiesen {eur(ytd)} (Differenz {eur(ytd - exp)}) – "
                       f"es wurde nachträglich in Vormonaten gebucht.", "BWA")
    # 2) Konten: Fortschreibung
    changed = []
    for n, k in a.sus.items():
        q = p.sus.get(n)
        if q is None:
            if same_year and (k.ytd_soll - k.per_soll > TOL or k.ytd_haben - k.per_haben > TOL):
                changed.append((n, k.name, k.ytd_soll - k.per_soll, k.ytd_haben - k.per_haben))
            continue
        if not same_year:
            continue
        dS, dH = (k.ytd_soll - k.per_soll) - q.ytd_soll, (k.ytd_haben - k.per_haben) - q.ytd_haben
        r.tests += 1
        if abs(dS) > TOL or abs(dH) > TOL:
            changed.append((n, k.name, dS, dH))
    for n, q in p.sus.items():
        if n not in a.sus and same_year and (abs(q.ytd_soll) > TOL or abs(q.ytd_haben) > TOL):
            changed.append((n, q.name + " (im Berichtsmonat nicht mehr bebucht)", -q.ytd_soll, -q.ytd_haben))
    r.meta["changed"] = changed
    if changed:
        txt = "; ".join(f"{n} {nm}: Soll {eur(dS)} / Haben {eur(dH)}" for n, nm, dS, dH in changed[:25])
        ust = [c for c in changed if c[0] in ("1401", "1406", "1407", "3806", "3837")]
        if ust:
            txt += (" – ACHTUNG Umsatzsteuer: " + ", ".join(f"{c[0]} {eur(c[2] - c[3])}" for c in ust) +
                    " wurde rückwirkend verändert; diese Beträge sind in den bereits gemeldeten UStVA der Vormonate nicht enthalten und sind in der "
                    "Aug-UStVA (Kz. 66 = nur Aug-Bewegung) nicht nachgeholt → ggf. berichtigte UStVA bzw. Nachmeldung beim Steuerberater erfragen.")
        r.test(False, "pruefen", f"{len(changed)} Konten mit nachträglich geänderten Vormonats-Buchungen",
               "Differenz zwischen kum. Werten des Berichtsmonats (abzüglich Monat) und den kum. Werten der Vormonats-BWA – "
               "also Buchungen mit Datum ≤ Vormonat, die nach Erstellung der Vormonats-BWA hinzukamen/geändert wurden: " + txt, "Summen & Salden")
    # 3) Entwicklungsübersicht: Vormonatswerte unverändert?
    diffs = []
    for lab, vals in a.entwicklung.items():
        pv = p.entwicklung.get(lab)
        if not pv:
            continue
        for i, m in enumerate(a.entw_months[:-1]):          # gemeinsame Monate
            if m in p.entw_months:
                j = p.entw_months.index(m)
                if abs(vals[i] - pv[j]) > Decimal("0.05"):
                    diffs.append((lab, m, pv[j], vals[i]))
    r.tests += 1
    if diffs:
        ocr = any(p.page_types.get(n) == "entwicklung" for n in (p.ocr_pages + a.ocr_pages))
        txt = "; ".join(f"{l} {m}: {eur(o)} → {eur(nw)}" for l, m, o, nw in diffs[:20])
        r.findings.append(Finding("pruefen" if not ocr else "info", f"{len(diffs)} Monatswerte früherer Monate haben sich seit der Vormonats-BWA geändert",
                                  txt + (" (Entwicklungsübersicht per OCR gelesen – ggf. Lesefehler)" if ocr else ""), "Entwicklungsübersicht"))
    r.test(True, "info", "", "")
    return r


def run_bwa_checks(a: Auswertung) -> list[CheckResult]:
    return [check_bwa_arithmetik(a), check_wertenachweis(a), check_summen_salden(a), check_ustva(a),
            check_ergebnis_aus_konten(a), check_opos(a), check_durchlaufend(a), check_kontenrichtung(a), check_entwicklung(a)]
