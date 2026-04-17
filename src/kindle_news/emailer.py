from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from .config import SMTPConfig
from .retry import retry_call


def send_epub(smtp_cfg: SMTPConfig, epub_path: Path, subject: str) -> None:
    password = os.getenv(smtp_cfg.password_env_var)
    if not password:
        raise RuntimeError(
            "Missing SMTP password environment variable: "
            f"{smtp_cfg.password_env_var}"
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = smtp_cfg.from_address
    message["To"] = smtp_cfg.to_address
    message.set_content("Your weekly Kindle news digest is attached.")

    payload = epub_path.read_bytes()
    message.add_attachment(
        payload,
        maintype="application",
        subtype="epub+zip",
        filename=epub_path.name,
    )

    def _send() -> None:
        with smtplib.SMTP(smtp_cfg.host, smtp_cfg.port, timeout=smtp_cfg.timeout_seconds) as server:
            if smtp_cfg.use_tls:
                server.starttls()
            if smtp_cfg.username:
                try:
                    server.login(smtp_cfg.username, password)
                except smtplib.SMTPAuthenticationError as exc:
                    raise RuntimeError(
                        "SMTP authentication failed. Check smtp.username, smtp.host/port, and "
                        f"the {smtp_cfg.password_env_var} secret value. "
                        f"Target server: {smtp_cfg.host}:{smtp_cfg.port}, "
                        f"username: {smtp_cfg.username}"
                    ) from exc
            server.send_message(message)

    retry_call(
        _send,
        retries=smtp_cfg.max_retries,
        retry_on=(smtplib.SMTPException, OSError),
    )
