"""Skill ustva-abgleich: UStVA-Kennzahlen gegen Buchhaltungskonten prüfen."""
from __future__ import annotations

import re as _re
from decimal import ROUND_HALF_UP, Decimal

from fibu.contracts import Context, Finding
from fibu.contracts.finding import Ref

ZERO = Decimal(0)


def _eur(val: Decimal) -> str:
    s = f"{val:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def run(ctx: Context) -> list[Finding]:
    a = ctx.auswertung
    tol = Decimal(str(ctx.config.get("toleranz", "0.02")))

    kto_ust_19 = str(ctx.config.get("ustva_konto_ust_19", "3806"))
    raw_vs = ctx.config.get("ustva_konto_vorsteuer", ["1406", "1401"])
    kto_vorsteuer = [str(k) for k in raw_vs] if isinstance(raw_vs, list) else ["1406", "1401"]
    kto_ust_13b = str(ctx.config.get("ustva_konto_ust_13b", "3837"))
    kto_vs_13b = str(ctx.config.get("ustva_konto_vorsteuer_13b", "1407"))
    kto_zahlung = str(ctx.config.get("ustva_konto_zahlung", "3820"))
    kto_verbindlichkeit = str(ctx.config.get("ustva_konto_verbindlichkeit", "3860"))

    if not a.ustva:
        return [Finding(
            rule="ustva-abgleich",
            severity="pruefen",
            title="UStVA-Seiten nicht gefunden",
            detail="Keine UStVA-Werte im PDF erkannt.",
        )]

    findings: list[Finding] = []

    def per(nr: str, side: str) -> Decimal:
        k = a.sus.get(nr)
        return (k.per_soll if side == "S" else k.per_haben) if k else ZERO

    def tax(kz: str) -> Decimal:
        kz_obj = a.ustva.get(kz)
        return (kz_obj.tax or ZERO) if kz_obj else ZERO

    def _rev19() -> Decimal:
        return sum(
            (k.per_haben - k.per_soll for n, k in a.sus.items()
             if n.startswith("4") and len(n) == 4 and "19" in k.name and "%" in k.name),
            ZERO,
        )

    _ref_bwa = Ref(art="seite", id="UStVA")

    z81 = a.ustva.get("81")
    if z81 is not None and z81.base is not None:
        rev = _rev19()
        if abs(z81.base - rev) > Decimal("1.00"):
            findings.append(Finding(
                rule="ustva-abgleich", severity="fehler",
                title="Kz. 81 ≠ Erlöse 19 % laut Buchhaltung",
                detail=f"UStVA-Bemessung {_eur(z81.base)}, Erlöskonten 19 % {_eur(rev)}.",
                refs=[Ref(art="seite", id="UStVA Kz. 81")],
            ))
        if z81.tax is not None:
            calc = (z81.base * Decimal("0.19")).quantize(Decimal("0.01"), ROUND_HALF_UP)
            if abs(calc - z81.tax) > Decimal("0.05"):
                findings.append(Finding(
                    rule="ustva-abgleich", severity="fehler",
                    title="Kz. 81: Steuer ≠ 19 % der Bemessung",
                    detail=f"19 % von {_eur(z81.base)} = {_eur(calc)}, gemeldet {_eur(z81.tax)}.",
                    refs=[Ref(art="seite", id="UStVA Kz. 81")],
                ))
            if abs(per(kto_ust_19, "H") - z81.tax) > tol:
                findings.append(Finding(
                    rule="ustva-abgleich", severity="fehler",
                    title=f"Kz. 81 ≠ Konto {kto_ust_19} (Umsatzsteuer 19 %)",
                    detail=f"Konto {kto_ust_19} Haben {_eur(per(kto_ust_19, 'H'))}, UStVA {_eur(z81.tax)}.",
                    refs=[Ref(art="konto", id=kto_ust_19)],
                ))
            forderung = per("1200", "S")
            exp = (rev * Decimal("1.19")).quantize(Decimal("0.01"), ROUND_HALF_UP)
            if abs(forderung - exp) > Decimal("0.05"):
                findings.append(Finding(
                    rule="ustva-abgleich", severity="pruefen",
                    title="Forderungs-Zugang ≠ Erlöse × 1,19",
                    detail=(
                        f"Konto 1200 Soll {_eur(forderung)}, Erlöse brutto {_eur(exp)}"
                        f" – es könnten Erlöse ohne Rechnung oder Rechnungen ohne Erlös"
                        f" gebucht sein."
                    ),
                    refs=[Ref(art="konto", id="1200")],
                ))

    z66 = a.ustva.get("66")
    if z66 is not None and z66.tax is not None:
        vs = sum(per(k, "S") for k in kto_vorsteuer)
        if abs(vs - z66.tax) > tol:
            findings.append(Finding(
                rule="ustva-abgleich", severity="fehler",
                title=f"Kz. 66 ≠ abziehbare Vorsteuer (Konten {'/'.join(kto_vorsteuer)})",
                detail=f"Konten {_eur(vs)}, UStVA {_eur(z66.tax)}.",
                refs=[Ref(art="seite", id="UStVA Kz. 66")],
            ))

    z46 = a.ustva.get("46")
    z67 = a.ustva.get("67")
    if z46 is not None and z46.tax is not None:
        if abs(per(kto_ust_13b, "H") - z46.tax) > tol:
            findings.append(Finding(
                rule="ustva-abgleich", severity="fehler",
                title=f"Kz. 46 ≠ Konto {kto_ust_13b} (USt § 13b)",
                detail=f"Konto {kto_ust_13b} {_eur(per(kto_ust_13b, 'H'))}, UStVA {_eur(z46.tax)}.",
                refs=[Ref(art="seite", id="UStVA Kz. 46")],
            ))
        if z46.base is not None:
            c = (z46.base * Decimal("0.19")).quantize(Decimal("0.01"), ROUND_HALF_UP)
            if abs(c - z46.tax) > Decimal("0.05"):
                findings.append(Finding(
                    rule="ustva-abgleich", severity="fehler",
                    title="Kz. 46: Steuer ≠ 19 % der Bemessung",
                    detail=f"19 % von {_eur(z46.base)} = {_eur(c)}, gemeldet {_eur(z46.tax)}.",
                    refs=[Ref(art="seite", id="UStVA Kz. 46")],
                ))
    if z67 is not None and z67.tax is not None and abs(per(kto_vs_13b, "S") - z67.tax) > tol:
        findings.append(Finding(
            rule="ustva-abgleich", severity="fehler",
            title=f"Kz. 67 ≠ Konto {kto_vs_13b} (Vorsteuer § 13b)",
            detail=f"Konto {kto_vs_13b} {_eur(per(kto_vs_13b, 'S'))}, UStVA {_eur(z67.tax)}.",
            refs=[Ref(art="seite", id="UStVA Kz. 67")],
        ))

    # Zahllast
    zahl = tax("81") + tax("46") - tax("66") - tax("67")
    z83 = tax("83")
    if abs(zahl - z83) > tol:
        findings.append(Finding(
            rule="ustva-abgleich", severity="fehler",
            title="Zahllast falsch berechnet",
            detail=f"Berechnet {_eur(zahl)}, Kz. 83 {_eur(z83)}.",
            refs=[Ref(art="seite", id="UStVA Kz. 83")],
        ))
    if a.ustva_zahllast is not None and abs(a.ustva_zahllast - z83) > tol:
        findings.append(Finding(
            rule="ustva-abgleich", severity="fehler",
            title="Verbleibender Betrag ≠ Kz. 83",
            detail=f"{_eur(a.ustva_zahllast)} vs. {_eur(z83)}.",
        ))
    kz_proto = a.ustva.get("83_protokoll")
    proto = kz_proto.tax if kz_proto is not None else None
    if proto is not None and abs(proto - z83) > tol:
        findings.append(Finding(
            rule="ustva-abgleich", severity="fehler",
            title="Übermittlungsprotokoll ≠ UStVA-Werte",
            detail=f"Protokoll {_eur(proto)}, Werte {_eur(z83)}.",
        ))
    if a.letter_amount is not None and abs(a.letter_amount - z83) > tol:
        findings.append(Finding(
            rule="ustva-abgleich", severity="fehler",
            title="Betrag im Anschreiben ≠ Kz. 83",
            detail=f"Anschreiben {_eur(a.letter_amount)}, UStVA {_eur(z83)}.",
        ))
    if abs(per(kto_zahlung, "S") - z83) > tol:
        findings.append(Finding(
            rule="ustva-abgleich", severity="pruefen",
            title=f"Konto {kto_zahlung} (USt-Vorauszahlung) ≠ Kz. 83",
            detail=f"Konto {kto_zahlung} Soll {_eur(per(kto_zahlung, 'S'))}, UStVA {_eur(z83)}.",
            refs=[Ref(art="konto", id=kto_zahlung)],
        ))

    # Verbindlichkeit USt
    k3860 = a.sus.get(kto_verbindlichkeit)
    if k3860:
        offen = -k3860.saldo
        if offen - z83 > Decimal("0.02"):
            findings.append(Finding(
                rule="ustva-abgleich", severity="pruefen",
                title=f"Konto {kto_verbindlichkeit}: USt-Verbindlichkeit höher als die aktuelle Zahllast",
                detail=(
                    f"Saldo {_eur(offen)} H, Zahllast {_eur(z83)} → {_eur(offen - z83)}"
                    f" ohne erkennbaren Zahlungsbezug "
                    f"(Vormonats-Zahllast nicht gezahlt/gebucht, Dauerfristverlängerung,"
                    f" Zahlung falsch kontiert?). "
                    f"Zahlungen im Monat: {_eur(k3860.per_soll)}."
                ),
                refs=[Ref(art="konto", id=kto_verbindlichkeit)],
            ))

    # Datumslogik Lastschrift vs. Übermittlung
    if a.ustva_datum:
        from datetime import datetime as _dt
        def _pd(s: str):  # type: ignore[no-untyped-def]
            for fmt in ("%d.%m.%Y", "%d/%m/%Y"):
                try:
                    return _dt.strptime(s, fmt).date()
                except ValueError:
                    pass
            return None

        txt = a.page_texts[0] if a.page_texts else ""
        mm = _re.search(r"am\s+(\d{2}\.\d{2}\.\d{4})\s+vom\s+Finanzamt", txt)
        d_datum = _pd(a.ustva_datum)
        if mm and d_datum and _pd(mm.group(1)) and _pd(mm.group(1)) < d_datum:
            findings.append(Finding(
                rule="ustva-abgleich", severity="info",
                title="Lastschrift vor Übermittlungsdatum",
                detail=(
                    f"Anschreiben: Einzug am {mm.group(1)},"
                    f" Übermittlung laut Protokoll am {a.ustva_datum}. "
                    f"Bitte prüfen, ob Fristende/Dauerfristverlängerung korrekt"
                    f" berücksichtigt ist."
                ),
            ))

    return findings
