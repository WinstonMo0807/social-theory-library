"""Check provider configuration through Django's SMTP transport, without sending mail."""
from pathlib import Path
import runpy
from unittest.mock import patch

from django.core.mail import send_mail
import pytest

from accounts.email_links import mail_available


def load_mail_settings(monkeypatch, settings, **values):
    names = (
        "EMAIL_PROVIDER", "EMAIL_BACKEND", "EMAIL_HOST", "EMAIL_PORT",
        "EMAIL_USE_TLS", "EMAIL_USE_SSL", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD",
        "EMAIL_TIMEOUT", "DEFAULT_FROM_EMAIL", "EMAIL_FROM_ADDRESS",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items():
        monkeypatch.setenv(name, str(value))
    # Execute the actual environment loader, rather than injecting SMTP settings directly.
    config = runpy.run_path(str(Path(__file__).parents[1] / "config/settings.py"))
    for name in names:
        if name in config:
            setattr(settings, name, config[name])
    settings.PUBLIC_WEB_URL = "https://library.example.invalid"
    settings.PUBLIC_DEPLOYMENT_MODE = True
    return config


@pytest.mark.parametrize("implicit_ssl,port", [(False, 587), (True, 465)])
def test_environment_reaches_encrypted_smtp_transport(monkeypatch, settings, implicit_ssl, port):
    load_mail_settings(
        monkeypatch, settings, EMAIL_PROVIDER="smtp", EMAIL_HOST="smtp.example.invalid",
        EMAIL_USE_SSL=str(implicit_ssl), EMAIL_HOST_USER="test-sender",
        EMAIL_HOST_PASSWORD="test-only-credential", EMAIL_TIMEOUT="12",
        EMAIL_FROM_ADDRESS="library@example.invalid.test",
    )
    assert mail_available()
    with patch("django.core.mail.backends.smtp.smtplib.SMTP") as starttls, \
            patch("django.core.mail.backends.smtp.smtplib.SMTP_SSL") as ssl:
        transport = ssl if implicit_ssl else starttls
        assert send_mail("Account message", "Test body", None, ["reader@example.invalid"]) == 1
        assert transport.call_args.args == ("smtp.example.invalid", port)
        assert transport.call_args.kwargs["timeout"] == 12
        transport.return_value.login.assert_called_once_with("test-sender", "test-only-credential")
        transport.return_value.sendmail.assert_called_once()
        if implicit_ssl:
            starttls.assert_not_called()
            transport.return_value.starttls.assert_not_called()
        else:
            ssl.assert_not_called()
            transport.return_value.starttls.assert_called_once()


def test_unconfigured_smtp_is_not_available(monkeypatch, settings):
    load_mail_settings(monkeypatch, settings, EMAIL_PROVIDER="smtp", EMAIL_FROM_ADDRESS="library@example.org")
    assert not mail_available()


def test_existing_provider_and_explicit_backend_are_preserved(monkeypatch, settings):
    config = load_mail_settings(monkeypatch, settings, EMAIL_PROVIDER="brevo")
    assert config["EMAIL_BACKEND"] == "common.email_backend.BrevoEmailBackend"
    config = load_mail_settings(
        monkeypatch, settings, EMAIL_PROVIDER="smtp",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    )
    assert config["EMAIL_BACKEND"] == "django.core.mail.backends.locmem.EmailBackend"
