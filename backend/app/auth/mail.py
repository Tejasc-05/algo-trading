"""Configured SMTP delivery. No email body, address, password or token is logged."""
import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlparse
from app.core.config import get_settings
from app.core.exceptions import AppError


def require_mail_configuration():
    settings = get_settings()
    parsed = urlparse(settings.password_reset_frontend_url)
    local = parsed.hostname in {'localhost', '127.0.0.1', '[::1]', '::1'}
    if not settings.smtp_host or not settings.smtp_from_email or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'', '/'} or not parsed.hostname:
        raise AppError('EMAIL_NOT_CONFIGURED', 'Password reset email delivery is not configured. Contact the administrator.', 503)
    if parsed.scheme != 'https' and not (settings.environment == 'development' and local and parsed.scheme == 'http'):
        raise AppError('EMAIL_NOT_CONFIGURED', 'Password reset email delivery is not configured. Contact the administrator.', 503)
    if settings.environment != 'development' and not (settings.smtp_ssl or settings.smtp_starttls):
        raise AppError('EMAIL_NOT_CONFIGURED', 'Password reset email delivery is not configured. Contact the administrator.', 503)
    return settings


def _send(recipient, subject, text):
    settings = require_mail_configuration()
    message = EmailMessage()
    message['From'] = str(settings.smtp_from_email)
    message['To'] = recipient
    message['Subject'] = subject
    message.set_content(text)
    cls = smtplib.SMTP_SSL if settings.smtp_ssl else smtplib.SMTP
    kwargs = {'context':ssl.create_default_context()} if settings.smtp_ssl else {}
    with cls(settings.smtp_host, settings.smtp_port, timeout=10, **kwargs) as smtp:
        if settings.smtp_starttls and not settings.smtp_ssl: smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_username: smtp.login(settings.smtp_username, settings.smtp_password or '')
        smtp.send_message(message)


async def send_reset_email(recipient, link, minutes):
    await asyncio.to_thread(_send, recipient, 'Reset your AlgoFlow password',
        f'Use this link to set a new AlgoFlow password:\n\n{link}\n\n'
        f'This link expires in {minutes} minutes and can be used once.\n'
        'If you did not request this, ignore this email. Your password has not changed.')


async def send_reset_confirmation(recipient):
    await asyncio.to_thread(_send, recipient, 'Your AlgoFlow password was changed',
        'Your AlgoFlow password has been reset. Earlier login sessions and reset links have been invalidated.\n'
        'If you did not make this change, contact your AlgoFlow administrator immediately.')
