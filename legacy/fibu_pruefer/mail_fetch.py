"""E-Mail-Eingang (IMAP) + Berichtsversand (SMTP). Konfiguration über Umgebungsvariablen.

FIBU_IMAP_HOST, FIBU_IMAP_USER, FIBU_IMAP_PASS, FIBU_IMAP_FOLDER (INBOX),
FIBU_ALLOWED_SENDERS (kommagetrennt, z. B. "@ehwa.de"), FIBU_SMTP_HOST/PORT/USER/PASS, FIBU_REPORT_TO.
Es werden nur PDFs von erlaubten Absendern mit erkennbarer BWA ("Kurzfristige Erfolgsrechnung") übernommen.
"""
from __future__ import annotations

import email
import imaplib
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from .pdfwords import load_pages

MON = ["", "Jan", "Feb", "Mrz", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


def _period_of(pdf: Path) -> tuple[int, int] | None:
    from .parser import MONTH_NAMES
    import re
    for p in load_pages(pdf, ocr=False)[:4]:
        m = re.search(r"Erfolgsrechnung\s+([A-Za-zäöüÄÖÜ]+)\s+(\d{4})", p.head(6))
        if m and m.group(1) in MONTH_NAMES:
            return int(m.group(2)), MONTH_NAMES[m.group(1)]
    return None


def fetch_new(root: Path, folder_tpl: str = "{mm} {mon}") -> list[Path]:
    host = os.environ.get("FIBU_IMAP_HOST")
    if not host:
        return []
    allowed = [s.strip().lower() for s in os.environ.get("FIBU_ALLOWED_SENDERS", "").split(",") if s.strip()]
    saved: list[Path] = []
    imap = imaplib.IMAP4_SSL(host)
    imap.login(os.environ["FIBU_IMAP_USER"], os.environ["FIBU_IMAP_PASS"])
    imap.select(os.environ.get("FIBU_IMAP_FOLDER", "INBOX"))
    _, data = imap.search(None, "UNSEEN")
    for num in data[0].split():
        _, msg_data = imap.fetch(num, "(BODY.PEEK[])")
        msg = email.message_from_bytes(msg_data[0][1])
        sender = email.utils.parseaddr(msg.get("From", ""))[1].lower()
        if allowed and not any(sender.endswith(a) or a in sender for a in allowed):
            continue
        took = False
        for part in msg.walk():
            fn = part.get_filename()
            if not fn or not fn.lower().endswith(".pdf"):
                continue
            tmp = root / "_eingang"
            tmp.mkdir(exist_ok=True)
            f = tmp / fn
            f.write_bytes(part.get_payload(decode=True))
            per = _period_of(f)
            if not per:
                continue
            y, m = per
            dest = root / folder_tpl.format(mm=f"{m:02d}", mon=MON[m], yyyy=y) / "BWA"
            dest.mkdir(parents=True, exist_ok=True)
            f.replace(dest / fn)
            saved.append(dest / fn)
            took = True
        if took:
            imap.store(num, "+FLAGS", "\\Seen")
    imap.logout()
    return saved


def send_report(res) -> None:
    host, to = os.environ.get("FIBU_SMTP_HOST"), os.environ.get("FIBU_REPORT_TO")
    if not host or not to:
        return
    m = EmailMessage()
    m["From"] = os.environ.get("FIBU_SMTP_USER", "fibu-pruefer@localhost")
    m["To"] = to
    m["Subject"] = f"Prüfbericht Buchhaltung {res.auswertung.month:02d}/{res.auswertung.year}: {res.status.upper()}"
    m.set_content(res.md_path.read_text(encoding="utf-8"))
    m.add_attachment(res.html_path.read_bytes(), maintype="text", subtype="html", filename=res.html_path.name)
    with smtplib.SMTP(host, int(os.environ.get("FIBU_SMTP_PORT", "587"))) as s:
        s.starttls()
        s.login(os.environ["FIBU_SMTP_USER"], os.environ["FIBU_SMTP_PASS"])
        s.send_message(m)
