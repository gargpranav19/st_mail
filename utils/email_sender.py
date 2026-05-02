"""Email sending module - extracted from main.py for reusability."""

import smtplib
from email.message import EmailMessage
import mimetypes
from pathlib import Path
from typing import List, Optional


def build_message(
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    html_body: Optional[str] = None,
    attachments: Optional[List[str]] = None,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
) -> EmailMessage:
    """Build an email message with optional HTML, attachments, CC, and BCC.
    
    Args:
        sender: From address
        recipient: To address
        subject: Email subject
        body: Plain text body
        html_body: Optional HTML version of the email
        attachments: List of file paths to attach
        cc: List of CC addresses
        bcc: List of BCC addresses
    
    Returns:
        EmailMessage object ready to send
    """
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg["Subject"] = subject
    
    # Set plain text content
    msg.set_content(body)
    
    # Add HTML alternative if provided
    if html_body:
        msg.add_alternative(html_body, subtype='html')
    
    # Add attachments
    if attachments:
        for a in attachments:
            path = Path(a)
            if not path.exists():
                print(f"Warning: attachment not found: {a}")
                continue
            ctype, encoding = mimetypes.guess_type(str(path))
            if ctype is None:
                ctype = 'application/octet-stream'
            maintype, subtype = ctype.split('/', 1)
            with path.open('rb') as fh:
                data = fh.read()
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=path.name)
    
    return msg


def send_message(
    smtp_host: str,
    smtp_port: int,
    message: EmailMessage,
    smtp_user: Optional[str] = None,
    smtp_pass: Optional[str] = None,
) -> bool:
    """Send a single email message via SMTP.
    
    Args:
        smtp_host: SMTP server hostname
        smtp_port: SMTP server port
        message: EmailMessage object to send
        smtp_user: Optional SMTP username for authentication
        smtp_pass: Optional SMTP password for authentication
    
    Returns:
        True if successful, False otherwise
    """
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            if smtp.has_extn('STARTTLS'):
                smtp.starttls()
                smtp.ehlo()
            if smtp_user and smtp_pass:
                smtp.login(smtp_user, smtp_pass)
            smtp.send_message(message)
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


def send_messages(
    smtp_host: str,
    smtp_port: int,
    messages: List[EmailMessage],
    smtp_user: Optional[str] = None,
    smtp_pass: Optional[str] = None,
) -> int:
    """Send multiple email messages via SMTP.
    
    Args:
        smtp_host: SMTP server hostname
        smtp_port: SMTP server port
        messages: List of EmailMessage objects to send
        smtp_user: Optional SMTP username for authentication
        smtp_pass: Optional SMTP password for authentication
    
    Returns:
        Number of successfully sent messages
    """
    sent_count = 0
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            if smtp.has_extn('STARTTLS'):
                smtp.starttls()
                smtp.ehlo()
            if smtp_user and smtp_pass:
                smtp.login(smtp_user, smtp_pass)
            for msg in messages:
                try:
                    smtp.send_message(msg)
                    sent_count += 1
                except Exception as e:
                    print(f"Failed to send individual message: {e}")
                    continue
    except Exception as e:
        print(f"SMTP connection error: {e}")
    
    return sent_count
