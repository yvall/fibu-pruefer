from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fibu.config import MailConfig
from fibu.ingest.mail import MailSender, NullMailSender, SmtpMailSender


def _config(**kwargs: object) -> MailConfig:
    defaults = {
        "smtp_host": "mail.example.com",
        "smtp_port": 587,
        "smtp_user": "fibu@example.com",
        "smtp_pass": "geheim",
        "von": "Fibu <fibu@example.com>",
        "an": ["empfaenger@example.com"],
    }
    defaults.update(kwargs)
    return MailConfig.model_validate(defaults)


# ---------------------------------------------------------------------------
# NullMailSender
# ---------------------------------------------------------------------------

def test_null_sender_logt_und_sendet_nicht(caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    md = tmp_path / "bericht.md"
    html = tmp_path / "bericht.html"
    md.write_text("# Test")
    html.write_bytes(b"<html/>")

    sender = NullMailSender()
    with caplog.at_level(logging.INFO, logger="fibu.ingest.mail"):
        sender.sende_bericht("Betreff", "Text", md, html)

    assert "Trockenlauf" in caplog.text
    assert "Betreff" in caplog.text


def test_null_sender_implementiert_protocol() -> None:
    assert isinstance(NullMailSender(), MailSender)


# ---------------------------------------------------------------------------
# SmtpMailSender.aus_config – Validierung
# ---------------------------------------------------------------------------

def test_aus_config_wirft_bei_leerem_smtp_host() -> None:
    with pytest.raises(ValueError, match="smtp_host"):
        SmtpMailSender.aus_config(_config(smtp_host=""))


def test_aus_config_wirft_bei_leerer_empfaengerliste() -> None:
    with pytest.raises(ValueError, match="mail.an"):
        SmtpMailSender.aus_config(_config(an=[]))


def test_aus_config_liest_passwort_aus_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIBU_SMTP_PASS", "env-pass")
    cfg = _config(smtp_pass="")
    sender = SmtpMailSender.aus_config(cfg)
    assert sender._smtp_pass == "env-pass"


def test_aus_config_bevorzugt_env_vor_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIBU_SMTP_PASS", "env-pass")
    sender = SmtpMailSender.aus_config(_config(smtp_pass="config-pass"))
    assert sender._smtp_pass == "env-pass"


# ---------------------------------------------------------------------------
# SmtpMailSender.sende_bericht – SMTP-Aufruf
# ---------------------------------------------------------------------------

def test_smtp_sender_ruft_smtp_korrekt_auf(tmp_path: Path) -> None:
    md = tmp_path / "bericht.md"
    html = tmp_path / "bericht.html"
    md.write_text("# Test")
    html.write_bytes(b"<html/>")

    cfg = _config()
    sender = SmtpMailSender(cfg, "geheim")

    mock_smtp = MagicMock()
    mock_smtp.__enter__ = lambda s: s
    mock_smtp.__exit__ = MagicMock(return_value=False)

    with patch("smtplib.SMTP", return_value=mock_smtp) as smtp_cls:
        sender.sende_bericht("Betreff Test", "Markdown-Inhalt", md, html)

    smtp_cls.assert_called_once_with("mail.example.com", 587)
    mock_smtp.starttls.assert_called_once()
    mock_smtp.login.assert_called_once_with("fibu@example.com", "geheim")
    mock_smtp.send_message.assert_called_once()


def test_smtp_sender_implementiert_protocol() -> None:
    cfg = _config()
    assert isinstance(SmtpMailSender(cfg, "pw"), MailSender)
