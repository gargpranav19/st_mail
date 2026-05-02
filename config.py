"""Project-level configuration you can edit instead of passing CLI/env vars.

Leave any value as None to keep using the CLI or environment variables.
Attachments should be a list of file paths (relative to project root or absolute).
"""

# SMTP settings (used if CLI/env not provided)
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = None
SMTP_PASS = None  # do not store secrets here for Streamlit mode; enter password in the app UI

# Default sender/subject/body if you prefer to set them in code
SENDER = None
SUBJECT = None
BODY = """Hi,
Please find the attached report.

Thank you.
"""

# CC and BCC (comma-separated email addresses or leave as empty string)
CC = ""  # e.g., "manager@example.com, admin@example.com"
BCC = ""  # e.g., "archive@example.com"

# Attachments applied to every message (optional)
ATTACHMENTS = []

# Excel/input defaults (set here to avoid passing on CLI)
EXCEL_PATH = 'recipients.xlsx'
SHEET = None  # sheet name or index
EMAIL_COLUMN = None  # column name that contains the email addresses
CC_COLUMN = None  # column name that contains CC addresses (comma-separated per row, optional)
BCC_COLUMN = None  # column name that contains BCC addresses (comma-separated per row, optional)
