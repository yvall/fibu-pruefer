"""Ingest-Schicht: liest einen Periodenordner und baut einen Context für run_skills().

Nutzt die Legacy-Parser unter der Haube (PDF-Parsing, Beleg-Scan, Klärungsliste).
Die Konvertierung legacy.Auswertung → contracts.Auswertung erfolgt vollständig hier;
die contracts-Modelle haben keine Abhängigkeit auf die Legacy.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fibu.contracts import (
    Auswertung,
    BelegRecord,
    Context,
    JahresEintrag,
    JahresKonto,
    KlaerRow,
    Konto,
    OposItem,
    Rueckfrage,
    UstvaKz,
    WGroup,
    WKonto,
)


def _from_legacy(a: Any) -> Auswertung:
    """Konvertiert legacy.Auswertung vollständig in contracts.Auswertung."""
    return Auswertung(
        source=str(a.source),
        year=a.year,
        month=a.month,
        created=a.created,
        page_texts=[p.text for p in a.pages],
        page_types=a.page_types,
        bwa=a.bwa,
        wgroups=[
            WGroup(
                zeile=g.zeile,
                name=g.name,
                bwa_per=g.bwa_per,
                bwa_ytd=g.bwa_ytd,
                ocr=g.ocr,
                kontos=[
                    WKonto(nr=k["nr"], sh=k["sh"], name=k["name"], per=k["per"], ytd=k["ytd"])
                    for k in g.kontos
                ],
            )
            for g in a.wgroups
        ],
        sus={
            nr: Konto(
                nr=nr,
                name=k.name,
                eb=k.eb,
                per_soll=k.per_soll,
                per_haben=k.per_haben,
                ytd_soll=k.ytd_soll,
                ytd_haben=k.ytd_haben,
                saldo=k.saldo,
            )
            for nr, k in a.sus.items()
        },
        sus_total=a.sus_total,
        opos=[
            OposItem(
                konto=it.konto,
                konto_name=it.konto_name,
                belegnr=it.belegnr,
                datum=it.datum,
                faellig=it.faellig,
                gegenkonto=it.gegenkonto,
                soll=it.soll,
                haben=it.haben,
                text=it.text,
            )
            for it in a.opos
        ],
        opos_totals=a.opos_totals,
        entwicklung=a.entwicklung,
        entw_months=a.entw_months,
        ustva={
            kz: UstvaKz(base=v.get("base"), tax=v.get("tax"))
            for kz, v in a.ustva.items()
        },
        ustva_zahllast=a.ustva_zahllast,
        ustva_datum=a.ustva_datum,
        jahreskonten=[
            JahresKonto(
                nr=jk.nr,
                name=jk.name,
                eb=jk.eb,
                saldo=jk.saldo,
                jvz_soll=jk.jvz_soll,
                jvz_haben=jk.jvz_haben,
                entries=[
                    JahresEintrag(
                        datum=e["datum"],
                        text=e["text"],
                        soll=e["soll"],
                        haben=e["haben"],
                    )
                    for e in jk.entries
                ],
            )
            for jk in a.jahreskonten
        ],
        rueckfragen=[
            Rueckfrage(datum=r.datum, betrag=r.betrag, text=r.text)
            for r in a.rueckfragen
        ],
        letter_amount=a.letter_amount,
        ocr_pages=a.ocr_pages,
        warnings=a.warnings,
    )


def load_context(
    period_dir: Path,
    bwa_dirname: str = "BWA",
    config: dict[str, object] | None = None,
) -> Context:
    """Lädt einen Periodenordner vollständig in einen Context.

    Nutzt die Legacy-Parser für PDF, Belege und Klärungsliste.
    Wirft FileNotFoundError, wenn kein BWA-PDF vorhanden.
    """
    from legacy.fibu_pruefer.belege import load_klaerung, scan
    from legacy.fibu_pruefer.parser import load_auswertung
    from legacy.fibu_pruefer.pipeline import list_bwa_pdfs

    pdfs = list_bwa_pdfs(period_dir, bwa_dirname)
    if not pdfs:
        raise FileNotFoundError(f"Kein BWA-PDF in {period_dir / bwa_dirname}")

    legacy_a = load_auswertung(pdfs[-1][1])
    legacy_p = load_auswertung(pdfs[-2][1]) if len(pdfs) >= 2 else None

    legacy_belege = scan(period_dir, bwa_dirname)
    belege = [
        BelegRecord(
            path=str(b.path),
            rel=b.rel,
            sha=b.sha,
            text=b.text,
            kind=b.kind,
            brutto=b.brutto,
            netto=b.netto,
            alle=b.alle,
            daten=b.daten,
            nummern=b.nummern,
            leistung=b.leistung,
            ocr=b.ocr,
        )
        for b in legacy_belege
    ]

    legacy_rows = load_klaerung(period_dir)
    klaerung = [
        KlaerRow(text=r.text, monat=r.monat, betrag=r.betrag, kommentar=r.kommentar)
        for r in legacy_rows
    ]

    return Context(
        auswertung=_from_legacy(legacy_a),
        prev=_from_legacy(legacy_p) if legacy_p else None,
        belege=belege,
        klaerung=klaerung,
        config=config or {},
    )
