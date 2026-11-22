"""Centralized email notification service."""
import re

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string


class EmailNotificationService:
    """Centralized service for sending email notifications."""

    def send(self, subject: str, template_name: str, context: dict,
             recipient_list: list[str]) -> int:
        """
        Render template, send email via send_mail.

        Returns number of successfully sent emails (0 or 1).
        """
        html_message = render_to_string(template_name, context)
        plain_message = self._to_plain(html_message)

        return send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.EMAIL_FROM,
            recipient_list=recipient_list,
            html_message=html_message,
        )

    @staticmethod
    def _to_plain(html: str) -> str:
        """Minimal plain-text fallback from HTML."""
        text = re.sub('<[^<]+>', '', html).strip()
        return re.sub(r'\s+', ' ', text)
