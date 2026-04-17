from pathlib import Path

import pytest

from kindle_news.config import SMTPConfig
from kindle_news.emailer import send_epub


class FakeSMTP:
    attempts = 0
    sent = 0

    def __init__(self, host: str, port: int, timeout: int) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def __enter__(self) -> "FakeSMTP":
        FakeSMTP.attempts += 1
        if FakeSMTP.attempts == 1:
            raise OSError("temporary failure")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def starttls(self) -> None:
        return None

    def login(self, username: str, password: str) -> None:
        return None

    def send_message(self, message) -> None:
        FakeSMTP.sent += 1


class FakeSMTPAuthFail(FakeSMTP):
    def login(self, username: str, password: str) -> None:
        raise __import__("smtplib").SMTPAuthenticationError(535, b"bad creds")


def test_send_epub_retries(monkeypatch, tmp_path: Path) -> None:
    epub_path = tmp_path / "sample.epub"
    epub_path.write_bytes(b"epub")
    cfg = SMTPConfig(
        host="smtp.example.com",
        port=587,
        username="user",
        password_env_var="SMTP_PASSWORD",
        from_address="from@example.com",
        to_address="to@example.com",
        use_tls=True,
        max_retries=1,
        timeout_seconds=10,
    )
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    send_epub(cfg, epub_path, "Subject")

    assert FakeSMTP.attempts == 2
    assert FakeSMTP.sent == 1


def test_send_epub_reports_auth_failure(monkeypatch, tmp_path: Path) -> None:
    epub_path = tmp_path / "sample.epub"
    epub_path.write_bytes(b"epub")
    cfg = SMTPConfig(
        host="smtp.example.com",
        port=587,
        username="user",
        password_env_var="SMTP_PASSWORD",
        from_address="from@example.com",
        to_address="to@example.com",
        use_tls=True,
        max_retries=0,
        timeout_seconds=10,
    )
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTPAuthFail)

    with pytest.raises(RuntimeError, match="SMTP authentication failed"):
        send_epub(cfg, epub_path, "Subject")
