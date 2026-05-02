#!/usr/bin/env python3
"""Send mass emails using addresses read from an Excel file.

Usage examples:
  Dry-run (no send):
	python main.py --excel recipients.xlsx --subject "Hello" --body "Hi all" --sender "me@example.com"

  Send using SMTP:
	python main.py --excel recipients.xlsx --subject "Hello" --body "Hi all" --sender "me@example.com" --smtp-host smtp.example.com --smtp-port 587 --smtp-user me@example.com --smtp-pass secret --send

The script looks for an email column automatically (case-insensitive) if --email-column is not provided.
"""

import argparse
import os
import re
import sys
import smtplib
from email.message import EmailMessage
import mimetypes
from pathlib import Path
from typing import List, Optional, Union
from dotenv import load_dotenv
import config

load_dotenv()
try:
	import pandas as pd
except Exception as e:
	print("Missing dependency: pandas (and openpyxl for .xlsx). Install with: python -m pip install pandas openpyxl")
	raise


EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def find_email_column(df: pd.DataFrame) -> str:
	candidates = [c for c in df.columns if "email" in c.lower()]
	if candidates:
		return candidates[0]
	# fallback: any column whose values look like emails
	for c in df.columns:
		sample = df[c].dropna().astype(str).head(20).tolist()
		if sample and all(EMAIL_REGEX.match(s) for s in sample):
			return c
	raise ValueError("Could not find an email column automatically. Use --email-column to specify the column name.")



def load_emails_from_excel(path: str, sheet: Optional[Union[str, int]] = None, email_column: Optional[str] = None, cc_column: Optional[str] = None, bcc_column: Optional[str] = None) -> List[dict]:

	# If sheet is None, read the first sheet (passing sheet_name=None to pandas
	# returns a dict of DataFrames). If a numeric sheet index was provided as a
	# string, coerce it to int.
	if sheet is None:
		df = pd.read_excel(path)
	else:
		# coerce numeric string to int
		sheet_arg = sheet
		if isinstance(sheet, str) and sheet.isdigit():
			sheet_arg = int(sheet)
		df = pd.read_excel(path, sheet_name=sheet_arg)
	if email_column:
		if email_column not in df.columns:
			raise KeyError(f"Email column '{email_column}' not found in sheet. Available columns: {list(df.columns)}")
		col = email_column
	else:
		col = find_email_column(df)

	# Validate CC/BCC columns exist
	if cc_column and cc_column not in df.columns:
		raise KeyError(f"CC column '{cc_column}' not found in sheet. Available columns: {list(df.columns)}")
	if bcc_column and bcc_column not in df.columns:
		raise KeyError(f"BCC column '{bcc_column}' not found in sheet. Available columns: {list(df.columns)}")

	emails = df[col].dropna().astype(str).str.strip()
	valid_indices = [i for i, e in enumerate(emails) if EMAIL_REGEX.match(e)]
	invalid = [e for i, e in enumerate(emails) if i not in valid_indices]
	if invalid:
		print(f"Warning: {len(invalid)} invalid/ignored email values found (showing up to 10): {invalid[:10]}")

	# Build result list with email, cc, bcc
	result = []
	seen = set()
	for i in valid_indices:
		email = emails.iloc[i]
		if email in seen:
			continue  # deduplicate
		seen.add(email)

		row_data = {'email': email, 'cc': None, 'bcc': None}

		if cc_column:
			cc_val = df.iloc[i][cc_column]
			if pd.notna(cc_val):
				cc_str = str(cc_val).strip()
				if cc_str:
					row_data['cc'] = [e.strip() for e in cc_str.split(',') if e.strip()]

		if bcc_column:
			bcc_val = df.iloc[i][bcc_column]
			if pd.notna(bcc_val):
				bcc_str = str(bcc_val).strip()
				if bcc_str:
					row_data['bcc'] = [e.strip() for e in bcc_str.split(',') if e.strip()]

		result.append(row_data)

	return result


def build_message(sender: str, recipient: str, subject: str, body: str, attachments: Optional[List[str]] = None, cc: Optional[List[str]] = None, bcc: Optional[List[str]] = None) -> EmailMessage:
	msg = EmailMessage()
	msg["From"] = sender
	msg["To"] = recipient
	if cc:
		msg["Cc"] = ", ".join(cc)
	if bcc:
		msg["Bcc"] = ", ".join(bcc)
	msg["Subject"] = subject
	msg.set_content(body)

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


def send_messages(smtp_host: str, smtp_port: int, smtp_user: Optional[str], smtp_pass: Optional[str], messages: List[EmailMessage]):
	with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
		smtp.ehlo()
		if smtp.has_extn('STARTTLS'):
			smtp.starttls()
			smtp.ehlo()
		if smtp_user and smtp_pass:
			smtp.login(smtp_user, smtp_pass)
		for msg in messages:
			smtp.send_message(msg)


def parse_args():
	p = argparse.ArgumentParser(description="Send mass email using recipients from an Excel file.")
	p.add_argument("--excel", required=False, help="Path to Excel file (.xlsx/.xls) containing recipient emails (or set in config.py)")
	p.add_argument("--sheet", default=None, help="Sheet name or index (optional)")
	p.add_argument("--email-column", default=None, help="Column name that holds email addresses (auto-detected if omitted)")
	p.add_argument("--cc-column", default=None, help="Column name that holds CC addresses (comma-separated per row, optional)")
	p.add_argument("--bcc-column", default=None, help="Column name that holds BCC addresses (comma-separated per row, optional)")
	p.add_argument("--subject", required=False, help="Email subject (or set SUBJECT in config.py)")
	p.add_argument("--body", required=False, help="Email body (plain text) (or set BODY in config.py)")
	p.add_argument("--sender", required=False, help="From address to show in emails (or set SENDER in config.py)")
	p.add_argument("--cc", required=False, help="CC addresses (comma-separated, or set CC in config.py)")
	p.add_argument("--bcc", required=False, help="BCC addresses (comma-separated, or set BCC in config.py)")
	p.add_argument("--smtp-host", default=os.getenv('SMTP_HOST'), help="SMTP host (or set SMTP_HOST env var)")
	p.add_argument("--smtp-port", type=int, default=int(os.getenv('SMTP_PORT') or 587), help="SMTP port (default 587)")
	p.add_argument("--smtp-user", default=os.getenv('SMTP_USER'), help="SMTP username (or set SMTP_USER env var)")
	p.add_argument("--smtp-pass", default=os.getenv('SMTP_PASS'), help="SMTP password (or set SMTP_PASS env var)")
	p.add_argument("--send", action="store_true", help="Actually send emails. Without this flag the script performs a dry-run.")
	return p.parse_args()


def main():
	args = parse_args()

	# load emails
	excel = args.excel or config.EXCEL_PATH
	sheet = args.sheet or config.SHEET
	email_column = args.email_column or config.EMAIL_COLUMN
	cc_column = args.cc_column or config.CC_COLUMN
	bcc_column = args.bcc_column or config.BCC_COLUMN

	try:
		recipients = load_emails_from_excel(excel, sheet, email_column, cc_column, bcc_column)
	except Exception as e:
		print(f"Failed to read emails from Excel: {e}")
		sys.exit(2)

	if not recipients:
		print("No valid recipient emails found. Exiting.")
		sys.exit(0)

	print(f"Loaded {len(recipients)} unique recipient(s). Preparing messages...")

	# prefer CLI args, then config.py, then env
	sender = args.sender or config.SENDER
	subject = args.subject or config.SUBJECT
	body = args.body or config.BODY

	# Parse global CC/BCC (comma-separated strings) - used if no column specified
	global_cc = None
	if args.cc or config.CC:
		cc_str = args.cc or config.CC
		global_cc = [e.strip() for e in cc_str.split(",") if e.strip()]

	global_bcc = None
	if args.bcc or config.BCC:
		bcc_str = args.bcc or config.BCC
		global_bcc = [e.strip() for e in bcc_str.split(",") if e.strip()]

	smtp_host = args.smtp_host or config.SMTP_HOST
	smtp_port = args.smtp_port or config.SMTP_PORT
	smtp_user = args.smtp_user or config.SMTP_USER
	smtp_pass = args.smtp_pass or config.SMTP_PASS

	attachments = config.ATTACHMENTS if config.ATTACHMENTS else None

	# Build messages - use per-recipient CC/BCC from Excel, or fall back to global
	messages = []
	for recipient_data in recipients:
		email = recipient_data['email']
		cc = recipient_data['cc'] or global_cc
		bcc = recipient_data['bcc'] or global_bcc
		msg = build_message(sender, email, subject, body, attachments, cc, bcc)
		messages.append(msg)

	if not args.send:
		print("--send flag not provided: DRY RUN - no emails will be sent.")
		print("Sample message preview:\n---")
		print(messages[0].as_string())
		print("---\nEnd preview.")
		print(f"Dry-run complete. {len(messages)} messages would have been sent.")
		return

	# Verify SMTP settings
	if not smtp_host:
		print("SMTP host is required to send email. Provide --smtp-host or set SMTP_HOST env var or edit config.py")
		sys.exit(3)

	try:
		send_messages(smtp_host, smtp_port, smtp_user, smtp_pass, messages)
	except Exception as e:
		print(f"Failed to send messages: {e}")
		sys.exit(4)

	print(f"Successfully sent {len(messages)} messages.")


if __name__ == '__main__':
	main()