jmail_sender
===========

A small, configurable CLI utility to send plain-text emails (with optional attachments) to a list of recipients stored in an Excel file.

This README explains how to configure the project using `config.py`, environment variables, or command-line flags; how to prepare your Excel file; how to run dry-runs and real sends; and common troubleshooting and safety tips.

## Contents
- `main.py` — the CLI script. Reads recipients, builds messages, optionally sends via SMTP.
- `config.py` — optional in-code defaults (SMTP, sender, subject, body, attachments, Excel path).
- `recipients.xlsx` — expected Excel file (you can use your own).
- `requirements.txt` — Python dependencies.

## Quick start (recommended)
1. Create and activate a virtual environment (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Required packages (if not present) are `pandas` and `openpyxl` for Excel support. `python-dotenv` is optional if you want the script to auto-load a `.env` file.

3. Edit `config.py` to configure defaults (optional)

Open `config.py` and set any of the following values. Leave values as `None` to keep using CLI args or environment variables.

- SMTP_HOST (e.g. `smtp.gmail.com`)
- SMTP_PORT (e.g. `587`)
- SMTP_USER (SMTP login username)
- SMTP_PASS (SMTP password or app password — do NOT commit this file with secrets)
- SENDER (From address to show in emails)
- SUBJECT (default subject)
- BODY (default plain-text body)
- ATTACHMENTS (list of file paths to attach to every message)
- EXCEL_PATH (path to your recipients Excel file)
- SHEET (sheet name or index)
- EMAIL_COLUMN (column name that contains email addresses)

Example snippet from `config.py`:

```python
SMTP_HOST = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_USER = 'you@example.com'
SMTP_PASS = None  # prefer environment var or remove this before committing
SENDER = 'you@example.com'
SUBJECT = 'Hello'
BODY = 'This is a plain-text message body.'
ATTACHMENTS = ['report.pdf']
EXCEL_PATH = 'recipients.xlsx'
EMAIL_COLUMN = 'Email'
```

4. Prepare the Excel file

- Save your recipient list as an `.xlsx` file.
- The script tries to auto-detect the email column by searching headers that include the word `email` (case-insensitive).
- If automatic detection fails, set `EMAIL_COLUMN` in `config.py` or pass `--email-column "YourEmailColumn"` on the CLI.

Minimal example (first rows):

| Email              | Name   |
|--------------------|--------|
| alice@example.com  | Alice  |
| bob@example.com    | Bob    |

5. Dry-run to preview messages (safe)

If you set values in `config.py` you can simply run:

```powershell
python .\main.py
```

Or explicitly provide the Excel file and message on the command line:

```powershell
python .\main.py --excel recipients.xlsx --subject "Hello" --body "This is a test" --sender "you@yourdomain.com"
```

The script will print a sample message and the number of messages that would be sent.

6. Send real emails (use `--send`)

Set SMTP credentials via environment variables (safer), or in `config.py` (not recommended for secrets), or pass them on the CLI.

PowerShell (session-only env vars):

```powershell
$env:SMTP_HOST = 'smtp.gmail.com'
$env:SMTP_PORT = '587'
$env:SMTP_USER = 'you@example.com'
$env:SMTP_PASS = 'your-smtp-password-or-app-password'
python .\main.py --send
# cleanup
Remove-Item Env:SMTP_PASS
```

Or pass on the CLI (less secure because history may retain the password):

```powershell
python .\main.py --smtp-host smtp.gmail.com --smtp-port 587 --smtp-user you@example.com --smtp-pass yourpass --send
```

### Gmail notes
- If your Google account uses 2-Step Verification, you must generate an App Password and use it as the `SMTP_PASS` value.
- Use port `587` with STARTTLS (the script uses smtplib + starttls).

## Attachments
- Add files to `config.ATTACHMENTS` (list of file paths). Example:

```python
ATTACHMENTS = ['report.pdf', 'report.docx']
```

- The script will try to attach every file in the list to each outgoing message. It guesses the MIME type automatically; unknown types are sent as `application/octet-stream`.
- Missing attachments are warned about and skipped.

## CLI reference

```
usage: main.py [-h] [--excel EXCEL] [--sheet SHEET] [--email-column EMAIL_COLUMN]
               [--subject SUBJECT] [--body BODY] [--sender SENDER]
               [--smtp-host SMTP_HOST] [--smtp-port SMTP_PORT]
               [--smtp-user SMTP_USER] [--smtp-pass SMTP_PASS] [--send]
```

Key options:
- `--excel` path to Excel file (or set `EXCEL_PATH` in `config.py`)
- `--sheet` sheet name or index
- `--email-column` the column containing emails (auto-detected if omitted)
- `--subject` subject text (or set `SUBJECT` in `config.py`)
- `--body` body text (or set `BODY` in `config.py`)
- `--sender` from address (or set `SENDER` in `config.py`)
- `--smtp-*` override SMTP settings
- `--send` actually send (dry-run by default)

## Troubleshooting
- Missing dependency error: run `python -m pip install pandas openpyxl`.
- `Could not find an email column`: set `EMAIL_COLUMN` in `config.py` or pass `--email-column` with the exact header.
- `5.7.8 BadCredentials` (Gmail): ensure `SMTP_USER` is the correct email and `SMTP_PASS` is a valid app password.
- Connection/TLS errors: verify `SMTP_HOST` and `SMTP_PORT`. Some providers use SSL on port 465; the script currently uses STARTTLS on 587. If you need port 465/SSL I can update the script.

## Security & best practices
- Do not commit `config.py` or `.env` with real credentials. Add `.env` and `config.py` to `.gitignore` if they contain secrets.
- When using the Streamlit app, enter SMTP username/password and sender email directly in the UI rather than storing them in backend config or environment variables.
- Prefer environment variables over in-code secrets for CLI use, but the Streamlit app is designed to receive credentials from the user at runtime.
- Test on a small list before sending to a large audience.
- For large or high-deliverability mailings use a dedicated provider (SendGrid, SES, Mailgun).

## Next steps I can help with
- Implement per-recipient personalization (replace placeholders like `{{Name}}` using Excel columns).
- Add SMTP credential validation (attempt login and report errors before sending messages).
- Add batching/rate-limiting for large lists.
- Support provider-specific SMTP SSL on port 465.

If you'd like any of those, tell me which and I'll implement and validate it.
