"""MailSender-Protocol und Implementierungen für den Versand-Knoten.

Empfänger kommen ausschließlich aus MailConfig.an (lokal.yaml) –
niemals aus Berichts- oder Beleginhalten (Schutz vor Prompt-Injection).
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol, runtime_checkable

from fibu.config import MailConfig

log = logging.getLogger(__name__)


@runtime_checkable
class MailSender(Protocol):
    def sende_bericht(
        self,
        betreff: str,
        text: str,
        md_pfad: Path,
        html_pfad: Path,
    ) -> None: ...


class NullMailSender:
    """Trockenlauf: protokolliert den Versand, sendet keine Mail."""

    def sende_bericht(
        self,
        betreff: str,
        text: str,
        md_pfad: Path,
        html_pfad: Path,
    ) -> None:
        log.info("Trockenlauf: Bericht würde gesendet – %s", betreff)


class SmtpMailSender:
    """Produktiv-Sender via SMTP + STARTTLS.

    Passwort: config.smtp_pass, Fallback Umgebungsvariable FIBU_SMTP_PASS.
    """

    def __init__(self, config: MailConfig, smtp_pass: str) -> None:
        self._config = config
        self._smtp_pass = smtp_pass

    @classmethod
    def aus_config(cls, config: MailConfig) -> SmtpMailSender:
        """Validiert Konfiguration und gibt eine einsatzbereite Instanz zurück.

        Wirft ValueError wenn smtp_host oder an leer sind.
        """
        if not config.smtp_host:
            raise ValueError(
                "mail.smtp_host ist nicht konfiguriert. "
                "Bitte config/lokal.yaml ergänzen."
            )
        if not config.an:
            raise ValueError(
                "mail.an (Empfängerliste) ist leer. "
                "Bitte mindestens einen Empfänger in config/lokal.yaml eintragen."
            )
        smtp_pass = os.environ.get("FIBU_SMTP_PASS", config.smtp_pass)
        return cls(config, smtp_pass)

    def sende_bericht(
        self,
        betreff: str,
        text: str,
        md_pfad: Path,
        html_pfad: Path,
    ) -> None:
        cfg = self._config
        m = EmailMessage()
        m["From"] = cfg.von or cfg.smtp_user
        m["To"] = ", ".join(cfg.an)
        m["Subject"] = betreff
        m.set_content(text)
        m.add_attachment(
            html_pfad.read_bytes(),
            maintype="text",
            subtype="html",
            filename=html_pfad.name,
        )
        m.add_attachment(
            md_pfad.read_bytes(),
            maintype="text",
            subtype="markdown",
            filename=md_pfad.name,
        )
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port) as s:
            s.starttls()
            if cfg.smtp_user:
                s.login(cfg.smtp_user, self._smtp_pass)
            s.send_message(m)
        log.info("Prüfbericht versendet: %s → %s", betreff, cfg.an)
