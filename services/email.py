"""Email sending service using SMTP."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from core.config import get_settings

log = logging.getLogger(__name__)


def _send(to: str, subject: str, html_body: str) -> bool:
    """Send an HTML email. Returns True on success."""
    s = get_settings()
    if not s.smtp_host:
        log.warning("SMTP not configured — skipping email to %s", to)
        return False
    msg = MIMEMultipart("alternative")
    msg["From"] = s.smtp_from or s.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as server:
            server.starttls()
            server.login(s.smtp_user, s.smtp_password)
            server.sendmail(msg["From"], [to], msg.as_string())
        return True
    except Exception:
        log.exception("Failed to send email to %s", to)
        return False


# ── Email templates ──────────────────────────────────────────────────────────

_BASE = """
<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:'Segoe UI',Arial,sans-serif;background:#f4f6f8;">
<div style="max-width:520px;margin:40px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08);">
  <div style="background:linear-gradient(135deg,#1a73e8,#0d47a1);padding:28px 32px;text-align:center;">
    <h1 style="margin:0;color:#fff;font-size:1.6rem;">Geo<span style="color:#4caf50">Freak</span></h1>
  </div>
  <div style="padding:32px;">
    {content}
  </div>
  <div style="padding:16px 32px;background:#f8f9fa;text-align:center;font-size:.8rem;color:#999;">
    © 2026 GeoFreak
  </div>
</div>
</body></html>
"""


def send_welcome(to: str, username: str, confirm_url: str, lang: str = "es"):
    if lang == "es":
        subject = "¡Bienvenido a GeoFreak!"
        content = f"""
        <h2 style="color:#1a73e8;margin-top:0;">¡Hola, {username}!</h2>
        <p style="color:#333;line-height:1.6;">Gracias por registrarte en <strong>GeoFreak</strong>. Confirma tu email para activar todas las funciones:</p>
        <div style="text-align:center;margin:28px 0;">
          <a href="{confirm_url}" style="display:inline-block;padding:14px 36px;background:linear-gradient(135deg,#1a73e8,#0d47a1);color:#fff;text-decoration:none;border-radius:8px;font-weight:600;font-size:1rem;">Confirmar email</a>
        </div>
        <p style="color:#888;font-size:.85rem;">Si no creaste esta cuenta, ignora este mensaje.</p>
        """
    else:
        subject = "Welcome to GeoFreak!"
        content = f"""
        <h2 style="color:#1a73e8;margin-top:0;">Hi, {username}!</h2>
        <p style="color:#333;line-height:1.6;">Thanks for signing up for <strong>GeoFreak</strong>. Confirm your email to unlock all features:</p>
        <div style="text-align:center;margin:28px 0;">
          <a href="{confirm_url}" style="display:inline-block;padding:14px 36px;background:linear-gradient(135deg,#1a73e8,#0d47a1);color:#fff;text-decoration:none;border-radius:8px;font-weight:600;font-size:1rem;">Confirm email</a>
        </div>
        <p style="color:#888;font-size:.85rem;">If you didn't create this account, just ignore this message.</p>
        """
    _send(to, subject, _BASE.format(content=content))


def send_password_reset(to: str, username: str, reset_url: str, lang: str = "es"):
    if lang == "es":
        subject = "Recupera tu contraseña — GeoFreak"
        content = f"""
        <h2 style="color:#1a73e8;margin-top:0;">Hola, {username}</h2>
        <p style="color:#333;line-height:1.6;">Has solicitado restablecer tu contraseña. Haz clic en el enlace:</p>
        <div style="text-align:center;margin:28px 0;">
          <a href="{reset_url}" style="display:inline-block;padding:14px 36px;background:linear-gradient(135deg,#1a73e8,#0d47a1);color:#fff;text-decoration:none;border-radius:8px;font-weight:600;font-size:1rem;">Cambiar contraseña</a>
        </div>
        <p style="color:#888;font-size:.85rem;">El enlace caduca en 1 hora. Si no lo solicitaste, ignora este mensaje.</p>
        """
    else:
        subject = "Reset your password — GeoFreak"
        content = f"""
        <h2 style="color:#1a73e8;margin-top:0;">Hi, {username}</h2>
        <p style="color:#333;line-height:1.6;">You requested a password reset. Click the link below:</p>
        <div style="text-align:center;margin:28px 0;">
          <a href="{reset_url}" style="display:inline-block;padding:14px 36px;background:linear-gradient(135deg,#1a73e8,#0d47a1);color:#fff;text-decoration:none;border-radius:8px;font-weight:600;font-size:1rem;">Reset password</a>
        </div>
        <p style="color:#888;font-size:.85rem;">This link expires in 1 hour. If you didn't request this, just ignore it.</p>
        """
    _send(to, subject, _BASE.format(content=content))


def send_email_change_confirm(to: str, username: str, confirm_url: str, lang: str = "es"):
    if lang == "es":
        subject = "Confirma tu nuevo email — GeoFreak"
        content = f"""
        <h2 style="color:#1a73e8;margin-top:0;">Hola, {username}</h2>
        <p style="color:#333;line-height:1.6;">Has solicitado cambiar tu email. Confirma el nuevo email:</p>
        <div style="text-align:center;margin:28px 0;">
          <a href="{confirm_url}" style="display:inline-block;padding:14px 36px;background:linear-gradient(135deg,#1a73e8,#0d47a1);color:#fff;text-decoration:none;border-radius:8px;font-weight:600;font-size:1rem;">Confirmar nuevo email</a>
        </div>
        <p style="color:#888;font-size:.85rem;">Si no lo solicitaste, ignora este mensaje.</p>
        """
    else:
        subject = "Confirm your new email — GeoFreak"
        content = f"""
        <h2 style="color:#1a73e8;margin-top:0;">Hi, {username}</h2>
        <p style="color:#333;line-height:1.6;">You requested an email change. Confirm your new email:</p>
        <div style="text-align:center;margin:28px 0;">
          <a href="{confirm_url}" style="display:inline-block;padding:14px 36px;background:linear-gradient(135deg,#1a73e8,#0d47a1);color:#fff;text-decoration:none;border-radius:8px;font-weight:600;font-size:1rem;">Confirm new email</a>
        </div>
        <p style="color:#888;font-size:.85rem;">If you didn't request this, just ignore it.</p>
        """
    _send(to, subject, _BASE.format(content=content))


def send_verify_email(to: str, username: str, confirm_url: str, lang: str = "es"):
    """Resend the email-address verification link to an existing user."""
    if lang == "es":
        subject = "Verifica tu email — GeoFreak"
        content = f"""
        <h2 style="color:#1a73e8;margin-top:0;">Hola, {username}</h2>
        <p style="color:#333;line-height:1.6;">Has solicitado verificar tu email. Haz clic en el botón para confirmar tu dirección:</p>
        <div style="text-align:center;margin:28px 0;">
          <a href="{confirm_url}" style="display:inline-block;padding:14px 36px;background:linear-gradient(135deg,#1a73e8,#0d47a1);color:#fff;text-decoration:none;border-radius:8px;font-weight:600;font-size:1rem;">Verificar email</a>
        </div>
        <p style="color:#888;font-size:.85rem;">El enlace caduca en 24 horas. Si no lo solicitaste, ignora este mensaje.</p>
        """
    else:
        subject = "Verify your email — GeoFreak"
        content = f"""
        <h2 style="color:#1a73e8;margin-top:0;">Hi, {username}</h2>
        <p style="color:#333;line-height:1.6;">You requested to verify your email address. Click the button below to confirm:</p>
        <div style="text-align:center;margin:28px 0;">
          <a href="{confirm_url}" style="display:inline-block;padding:14px 36px;background:linear-gradient(135deg,#1a73e8,#0d47a1);color:#fff;text-decoration:none;border-radius:8px;font-weight:600;font-size:1rem;">Verify email</a>
        </div>
        <p style="color:#888;font-size:.85rem;">This link expires in 24 hours. If you didn't request this, just ignore it.</p>
        """
    _send(to, subject, _BASE.format(content=content))


def send_contact(name: str, email: str, message: str) -> bool:
    """Send a contact form message to the site admin."""
    import html as _html
    s = get_settings()
    to = s.mail_to or s.smtp_from or s.smtp_user
    if not to:
        log.warning("No MAIL_TO configured — skipping contact email")
        return False
    safe_name = _html.escape(name)
    safe_email = _html.escape(email)
    safe_msg = _html.escape(message).replace("\n", "<br>")
    subject = f"[GeoFreak] Contacto de {safe_name}"
    content = f"""
    <h2 style="color:#1a73e8;margin-top:0;">Nuevo mensaje de contacto</h2>
    <p style="color:#333;line-height:1.6;"><strong>Nombre:</strong> {safe_name}</p>
    <p style="color:#333;line-height:1.6;"><strong>Email:</strong> {safe_email}</p>
    <p style="color:#333;line-height:1.6;"><strong>Mensaje:</strong></p>
    <div style="background:#f4f6f8;padding:16px;border-radius:8px;color:#333;line-height:1.6;">{safe_msg}</div>
    """
    return _send(to, subject, _BASE.format(content=content))
