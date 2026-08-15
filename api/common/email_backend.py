from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
import httpx


class BrevoEmailBackend(BaseEmailBackend):
    """Django email backend using Brevo's HTTPS API, without SMTP."""

    def send_messages(self, email_messages):
        api_key = getattr(settings, "BREVO_API_KEY", "")
        if not api_key:
            if self.fail_silently:
                return 0
            raise RuntimeError("BREVO_API_KEY 尚未配置。")
        sent = 0
        for message in email_messages:
            payload = {
                "sender": {
                    "email": message.from_email or settings.DEFAULT_FROM_EMAIL,
                    "name": getattr(settings, "EMAIL_FROM_NAME", "社会理论书库"),
                },
                "to": [{"email": recipient} for recipient in message.to],
                "subject": message.subject,
                "textContent": message.body,
            }
            html_body = next(
                (content for content, mimetype in getattr(message, "alternatives", []) if mimetype == "text/html"),
                None,
            )
            if html_body:
                payload["htmlContent"] = html_body
            response = httpx.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={
                    "api-key": api_key,
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                json=payload,
                timeout=20,
            )
            if response.is_success:
                sent += 1
            elif not self.fail_silently:
                response.raise_for_status()
        return sent
