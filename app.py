"""Streamlit Email Composer Application - Send emails with rich text formatting."""

import html as html_module
import re
import streamlit as st
from streamlit.components.v1 import html as components_html
from streamlit_quill import st_quill
from bs4 import BeautifulSoup
import os
import tempfile
from pathlib import Path
from io import BytesIO
from typing import Optional, Tuple
from functools import lru_cache
from dotenv import load_dotenv
import pandas as pd
import config
from utils.email_sender import build_message, send_message

load_dotenv()

# Page configuration
st.set_page_config(
    page_title="Email Composer",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better UI
st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 1.1rem;
    }
    .email-preview {
        border: 1px solid #ddd;
        padding: 20px;
        border-radius: 5px;
        background-color: #f9f9f9;
    }
    .email-preview ul,
    .email-preview ol {
        margin-top: 0;
        margin-bottom: 0.75rem;
        margin-left: 1.5rem;
    }
    .email-preview li {
        margin-bottom: 0.35rem;
    }
    .email-preview p {
        margin: 0 0 0.85rem 0;
    }
    </style>
""", unsafe_allow_html=True)

# Initialize session state
if "subject" not in st.session_state:
    st.session_state.subject = config.SUBJECT or ""
if "html_content" not in st.session_state:
    st.session_state.html_content = ""
if "recipient_email" not in st.session_state:
    st.session_state.recipient_email = ""
if "cc_emails" not in st.session_state:
    st.session_state.cc_emails = config.CC or ""
if "bcc_emails" not in st.session_state:
    st.session_state.bcc_emails = config.BCC or ""
if "attachments" not in st.session_state:
    st.session_state.attachments = []

HTML_TAG_RE = re.compile(r"<[^>]+>")
LIST_BLOCK_RE = re.compile(r"<(ol|ul)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
QL_UI_SPAN_RE = re.compile(
    r"<span[^>]*class=[\"'][^\"']*\bql-ui\b[^\"']*[\"'][^>]*>.*?</span>",
    re.IGNORECASE | re.DOTALL,
)


@lru_cache(maxsize=1)
def _load_quill_css() -> str:
    """Load Quill core+theme CSS used by the editor."""
    try:
        import streamlit_quill  # local import keeps startup resilient

        package_root = Path(streamlit_quill.__file__).resolve().parent
        build_dir = package_root / "frontend" / "build"
        core_css = (build_dir / "quill.core.css").read_text(encoding="utf-8")
        snow_css = (build_dir / "quill.snow.css").read_text(encoding="utf-8")
        return f"{core_css}\n{snow_css}"
    except Exception:
        # Fallback keeps preview functional if package layout changes.
        return """
            .ql-editor { white-space: pre-wrap; }
            .ql-editor ol, .ql-editor ul { padding-left: 1.5em; }
            .ql-editor li { margin-bottom: 0.2rem; }
        """


def _quill_email_css() -> str:
    """Return CSS that preserves Quill spacing/indent/list rendering."""
    return """
        body {
            margin: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            color: #1f2937;
        }
        .email-preview {
            border: 1px solid #ddd;
            padding: 16px;
            border-radius: 5px;
            background-color: #f9f9f9;
            line-height: 1.5;
            word-break: break-word;
        }
        .email-preview .ql-editor {
            padding: 0;
            white-space: pre-wrap;
        }
        .email-preview .ql-editor ol li,
        .email-preview .ql-editor ul li {
            margin-bottom: 0.2rem;
        }
        .email-preview .ql-editor p,
        .email-preview .ql-editor ol,
        .email-preview .ql-editor ul {
            margin: 0 0 0.75rem 0;
        }
        .email-preview .ql-editor p:last-child,
        .email-preview .ql-editor ol:last-child,
        .email-preview .ql-editor ul:last-child {
            margin-bottom: 0;
        }
        .email-preview .ql-editor ol,
        .email-preview .ql-editor ul {
            padding-left: 1.5em;
        }
    """


def _email_safe_css() -> str:
    """Conservative CSS intended for broad email-client compatibility."""
    return """
        body {
            margin: 0;
            font-family: Arial, Helvetica, sans-serif;
            color: #1f2937;
            line-height: 1.5;
        }
        .email-preview {
            padding: 8px 0;
            word-break: break-word;
        }
        .email-preview p {
            margin: 0 0 12px 0;
        }
        .email-preview ul,
        .email-preview ol {
            margin: 0 0 12px 0;
            padding-left: 28px;
        }
        .email-preview li {
            margin: 0 0 6px 0;
        }
    """


def build_preview_html(content: str) -> str:
    """Render preview HTML with embedded CSS (iframe-safe)."""
    return f"""
        <style>
            {_load_quill_css()}
            {_quill_email_css()}
        </style>
        <div class="email-preview">
            <div class="ql-editor">
                {content}
            </div>
        </div>
    """


def build_email_html(content: str) -> str:
    """Wrap body content with robust email-client-friendly HTML."""
    return f"""
        <html>
        <body style="margin:0; padding:0; background-color:#ffffff;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse; background-color:#ffffff;">
                <tr>
                    <td align="left" style="padding:16px;">
                        <div style="font-family:Arial,Helvetica,sans-serif; color:#1f2937; line-height:1.5; font-size:16px;">
                            {content}
                        </div>
                    </td>
                </tr>
            </table>
        </body>
        </html>
    """


def _merge_inline_style(existing: str, extra: str) -> str:
    existing = (existing or "").strip()
    extra = (extra or "").strip()
    if not existing:
        return extra
    if not extra:
        return existing
    if not existing.endswith(";"):
        existing += ";"
    return f"{existing} {extra}"


def _inline_email_styles(content: str) -> str:
    """Apply inline styles so email clients render consistently."""
    soup = BeautifulSoup(content, "html.parser")

    for tag in soup.find_all(True):
        if tag.name in ("script", "style", "meta", "link"):
            tag.decompose()
            continue
        # Drop classes/data attrs that are editor-specific noise for email clients.
        attrs_to_remove = [k for k in tag.attrs.keys() if k == "class" or k.startswith("data-")]
        for key in attrs_to_remove:
            del tag.attrs[key]

    for p in soup.find_all("p"):
        p["style"] = _merge_inline_style(p.get("style", ""), "margin:0 0 12px 0;")
        # Keep visible vertical spacing for empty lines.
        if not p.get_text(strip=True) and not p.find(True):
            p.string = "\xa0"

    for ul in soup.find_all("ul"):
        ul["style"] = _merge_inline_style(
            ul.get("style", ""),
            "margin:0 0 12px 0; padding-left:28px; list-style-position:outside;",
        )
    for ol in soup.find_all("ol"):
        ol["style"] = _merge_inline_style(
            ol.get("style", ""),
            "margin:0 0 12px 0; padding-left:28px; list-style-position:outside;",
        )
    for li in soup.find_all("li"):
        li["style"] = _merge_inline_style(li.get("style", ""), "margin:0 0 6px 0;")

    for h1 in soup.find_all("h1"):
        h1["style"] = _merge_inline_style(h1.get("style", ""), "margin:0 0 12px 0; font-size:28px;")
    for h2 in soup.find_all("h2"):
        h2["style"] = _merge_inline_style(h2.get("style", ""), "margin:0 0 12px 0; font-size:24px;")
    for h3 in soup.find_all("h3"):
        h3["style"] = _merge_inline_style(h3.get("style", ""), "margin:0 0 12px 0; font-size:20px;")

    return str(soup)


def convert_quill_lists_for_email(content: str) -> str:
    """Convert Quill flat list markup to nested semantic lists for email clients."""
    if not content:
        return content

    def _list_tag(list_type: str) -> str:
        return "ol" if list_type == "ordered" else "ul"

    def _list_style(list_type: str, depth: int) -> str:
        if list_type == "ordered":
            # Match Quill-style ordered depth: 1., a., i. (then repeat)
            ordered_styles = ("decimal", "lower-alpha", "lower-roman")
            return ordered_styles[depth % len(ordered_styles)]
        bullet_styles = ("disc", "circle", "square")
        return bullet_styles[depth % len(bullet_styles)]

    def _ordered_list_type_attr(depth: int) -> str:
        cycle = ("1", "a", "i")
        return cycle[depth % len(cycle)]

    def _build_nested_list_html(parsed_items, depth: int = 0) -> str:
        if not parsed_items:
            return ""

        roots = []
        level_nodes = {}
        for item in parsed_items:
            level = item["level"]
            node = {"type": item["type"], "html": item["html"], "children": []}
            if level == 0:
                roots.append(node)
            else:
                parent_level = level - 1
                parent = None
                while parent_level >= 0 and parent is None:
                    parent = level_nodes.get(parent_level)
                    parent_level -= 1
                if parent is None:
                    roots.append(node)
                    level = 0
                else:
                    parent["children"].append(node)
            level_nodes[level] = node
            for key in list(level_nodes.keys()):
                if key > level:
                    del level_nodes[key]

        def _render_nodes(nodes, render_depth: int = 0) -> str:
            out = []
            idx = 0
            while idx < len(nodes):
                current_type = nodes[idx]["type"]
                tag = _list_tag(current_type)
                style = _list_style(current_type, render_depth)
                if tag == "ol":
                    list_type_attr = _ordered_list_type_attr(render_depth)
                    out.append(
                        f'<ol type="{list_type_attr}" style="list-style-type: {style}; margin: 0 0 12px 0; padding-left: 28px;">'
                    )
                else:
                    out.append(
                        f'<ul style="list-style-type: {style}; margin: 0 0 12px 0; padding-left: 28px;">'
                    )
                while idx < len(nodes) and nodes[idx]["type"] == current_type:
                    node = nodes[idx]
                    out.append(f'<li style="margin: 0 0 6px 0;">{node["html"]}')
                    if node["children"]:
                        out.append(_render_nodes(node["children"], render_depth + 1))
                    out.append("</li>")
                    idx += 1
                out.append(f"</{tag}>")
            return "".join(out)

        return _render_nodes(roots, depth)

    soup = BeautifulSoup(content, "html.parser")
    list_blocks = soup.find_all(["ol", "ul"])

    for block in list_blocks:
        direct_items = block.find_all("li", recursive=False)
        if not direct_items:
            continue
        # Already semantic nested lists: keep as-is.
        if any(item.find(["ol", "ul"]) for item in direct_items):
            continue

        block_tag = block.name.lower()
        parsed_items = []
        is_quill_list = False
        for item in direct_items:
            attrs = " ".join(item.get("class", []))
            data_list = item.get("data-list")
            if data_list or "ql-indent-" in attrs or item.find("span", class_="ql-ui"):
                is_quill_list = True

            default_type = "ordered" if block_tag == "ol" else "bullet"
            list_type = data_list.lower() if data_list in ("ordered", "bullet") else default_type

            indent_match = re.search(r"ql-indent-(\d+)", attrs)
            level = int(indent_match.group(1)) if indent_match else 0

            # Remove Quill UI helper spans before rendering for email.
            for ui_span in item.find_all("span", class_="ql-ui"):
                ui_span.decompose()
            inner_html = "".join(str(child) for child in item.contents).strip()
            cleaned_inner = QL_UI_SPAN_RE.sub("", inner_html).strip()
            parsed_items.append({"type": list_type, "level": max(0, level), "html": cleaned_inner})

        if not is_quill_list:
            continue

        converted_html = _build_nested_list_html(parsed_items)
        converted_fragment = BeautifulSoup(converted_html, "html.parser")
        block.replace_with(converted_fragment)

    return str(soup)


def prepare_email_content(content: str, strict_mode: bool = True) -> str:
    """Prepare HTML for sending in a way email clients can reliably render."""
    if not strict_mode:
        return content
    converted = convert_quill_lists_for_email(content)
    return _inline_email_styles(converted)


def plain_text_to_email_html(text: str) -> str:
    """Render plain text as email-safe HTML while preserving spacing/new lines."""
    escaped = html_module.escape(text or "")
    return (
        '<div style="white-space: pre-wrap; font-family: Arial, Helvetica, sans-serif; '
        'line-height: 1.5; font-size: 16px;">'
        f"{escaped}</div>"
    )


def convert_text_lists_to_html(content: str) -> Optional[str]:
    """Convert plain-text list-like content into HTML lists."""
    lines = content.splitlines()
    if not any(re.match(r"^\s*([*\-•]|\d+[.)])\s+", line) for line in lines):
        return None

    html_parts = []
    current_level = 0

    def close_lists(level: int):
        nonlocal current_level
        while current_level > level:
            html_parts.append("</li></ul>")
            current_level -= 1

    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            close_lists(0)
            continue

        match = re.match(r"^(\s*)([*\-•]|\d+[.)])\s+(.*)$", stripped)
        if not match:
            close_lists(0)
            html_parts.append(f"<p>{html_module.escape(stripped)}</p>")
            continue

        indent = len(match.group(1).replace("\t", "    "))
        text = html_module.escape(match.group(3).strip())
        level = 1 + indent // 4

        if level > current_level:
            for _ in range(current_level, level):
                html_parts.append("<ul>")
                current_level += 1
            html_parts.append(f"<li>{text}")
        elif level < current_level:
            close_lists(level)
            html_parts.append(f"</li><li>{text}")
        else:
            if current_level == 0:
                html_parts.append("<ul>")
                current_level = 1
                html_parts.append(f"<li>{text}")
            else:
                html_parts.append(f"</li><li>{text}")

    close_lists(0)
    return "".join(html_parts)


def normalize_html_content(content: str) -> str:
    """Ensure the content is valid HTML for preview and email body."""
    if not content:
        return ""
    content = content.strip()
    if HTML_TAG_RE.search(content):
        return content
    list_html = convert_text_lists_to_html(content)
    if list_html:
        return list_html
    escaped = html_module.escape(content)
    replaced = escaped.replace("\n", "<br>")
    return f"<p>{replaced}</p>"


def plain_text_from_html(content: str) -> str:
    """Create a safe plain-text fallback from HTML content."""
    if not content:
        return ""
    text = re.sub(r"(?i)<li[^>]*>", "- ", content)
    text = re.sub(r"(?i)</(p|div|li|ul|ol|h[1-6])>", "\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"</?[^>]+>", "", text)
    text = html_module.unescape(text).replace("\r\n", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_final_email_payload(editor_content: str) -> Tuple[str, str, str]:
    """Create the exact HTML/text payload used for both preview and send."""
    normalized_html = normalize_html_content(editor_content)
    email_ready_html = prepare_email_content(normalized_html, True)
    body_text = plain_text_from_html(email_ready_html) or "This is an HTML email. Please view in an email client that supports HTML."
    email_html = build_email_html(email_ready_html)
    return email_ready_html, body_text, email_html


def parse_email_list(value: str) -> list:
    """Parse comma/semicolon/newline separated email strings safely."""
    if not value:
        return []
    parts = re.split(r"[,\n;]+", value)
    return [p.strip() for p in parts if p and p.strip()]


def get_setting(name: str, fallback=None, allow_env=True, allow_config=True):
    """Resolve a setting from env vars then config.

    Streamlit secrets are not used so users provide sensitive SMTP values via the UI.
    """
    if allow_env:
        env_value = os.getenv(name)
        if env_value not in (None, ""):
            return env_value
    if allow_config:
        return getattr(config, name, fallback)
    return fallback


def build_recipients_template_xlsx() -> bytes:
    """Create an Excel template with recipient routing columns."""
    template_df = pd.DataFrame(
        [
            {
                "recipients": "recipient1@example.com, recipient2@example.com",
                "cc": "cc1@example.com",
                "bcc": "bcc1@example.com",
            },
            {
                "recipients": "recipient3@example.com",
                "cc": "",
                "bcc": "",
            },
        ]
    )
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        template_df.to_excel(writer, index=False, sheet_name="recipients")
    output.seek(0)
    return output.getvalue()


def parse_recipients_excel(uploaded_excel_file) -> Tuple[list, Optional[str]]:
    """Parse an uploaded recipients Excel and normalize To/CC/BCC values."""
    try:
        df = pd.read_excel(uploaded_excel_file)
    except Exception as exc:
        return [], f"Unable to read Excel file: {exc}"

    if df.empty:
        return [], "The uploaded Excel file is empty."

    normalized_columns = {str(c).strip().lower(): c for c in df.columns}
    recipient_column = None
    for name in ("recipients", "recipient", "to", "email", "emails"):
        if name in normalized_columns:
            recipient_column = normalized_columns[name]
            break

    if recipient_column is None:
        return [], "Missing recipients column. Use one of: recipients, recipient, to, email, emails."

    cc_column = normalized_columns.get("cc")
    bcc_column = normalized_columns.get("bcc")

    recipient_rows = []
    for idx, row in df.iterrows():
        recipients_raw = row.get(recipient_column)
        recipients = parse_email_list("" if pd.isna(recipients_raw) else str(recipients_raw))
        if not recipients:
            continue

        cc_list = []
        bcc_list = []
        if cc_column is not None:
            cc_raw = row.get(cc_column)
            cc_list = parse_email_list("" if pd.isna(cc_raw) else str(cc_raw))
        if bcc_column is not None:
            bcc_raw = row.get(bcc_column)
            bcc_list = parse_email_list("" if pd.isna(bcc_raw) else str(bcc_raw))

        recipient_rows.append(
            {
                "row_number": idx + 2,  # +2 because Excel row 1 is header
                "to": recipients,
                "cc": cc_list,
                "bcc": bcc_list,
            }
        )

    if not recipient_rows:
        return [], "No valid recipient rows found. Ensure recipients cells are populated."

    return recipient_rows, None


def main():
    st.title("📧 Email Composer")
    st.markdown("Create and send beautifully formatted emails with rich text editing.")
    
    # Sidebar: SMTP Settings
    with st.sidebar:
        st.header("⚙️ Email Settings")
        
        st.subheader("SMTP Configuration")
        smtp_host = st.text_input(
            "SMTP Host",
            value=get_setting("SMTP_HOST", "smtp.gmail.com") or "smtp.gmail.com",
            help="e.g., smtp.gmail.com, smtp.office365.com"
        )
        smtp_port = st.number_input(
            "SMTP Port",
            value=int(get_setting("SMTP_PORT", 587) or 587),
            min_value=1,
            max_value=65535
        )
        smtp_user = st.text_input(
            "SMTP Username",
            value=get_setting("SMTP_USER", "", allow_env=False, allow_config=False) or "",
            type="password"
        )
        smtp_pass = st.text_input(
            "SMTP Password",
            value=get_setting("SMTP_PASS", "", allow_env=False, allow_config=False) or "",
            type="password"
        )
        
        st.subheader("Sender Settings")
        sender_email = st.text_input(
            "From Email",
            value=st.session_state.get("sender_email", smtp_user) or "",
            key="sender_email",
            help="The email address that will appear as the sender"
        )
    
    # Main content
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("Compose Email")
        
        # Recipient section
        st.subheader("📬 Recipients")
        recipient_email = st.text_input(
            "To (Recipient Email(s), comma-separated)",
            value=st.session_state.recipient_email,
            key="recipient_input",
            placeholder="recipient1@example.com, recipient2@example.com"
        )
        st.session_state.recipient_email = recipient_email

        recipient_list = parse_email_list(recipient_email)
        send_individually = st.checkbox(
            "Send separate emails to each recipient",
            value=False,
            help="Send a separate message to each recipient instead of one email addressed to all recipients."
        )

        col_cc, col_bcc = st.columns(2)
        with col_cc:
            cc_emails = st.text_input(
                "CC (comma-separated)",
                value=st.session_state.cc_emails,
                key="cc_input",
                placeholder="cc1@example.com, cc2@example.com"
            )
            st.session_state.cc_emails = cc_emails
        
        with col_bcc:
            bcc_emails = st.text_input(
                "BCC (comma-separated)",
                value=st.session_state.bcc_emails,
                key="bcc_input",
                placeholder="bcc@example.com"
            )
            st.session_state.bcc_emails = bcc_emails

        st.markdown("**Recipient Excel Upload (Optional)**")
        st.caption(
            "Upload an Excel file with columns: recipients, cc, bcc. "
            "If provided, email routing will follow Excel rows."
        )
        st.download_button(
            label="⬇️ Download Recipient Template",
            data=build_recipients_template_xlsx(),
            file_name="recipient_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=False,
            key="download_recipient_template",
        )

        recipient_excel_file = st.file_uploader(
            "Upload recipient Excel (.xlsx/.xls)",
            type=["xlsx", "xls"],
            key="recipient_excel_uploader",
            help="Each row can have recipients, cc, and bcc values."
        )

        excel_recipient_rows = []
        excel_parse_error = None
        if recipient_excel_file is not None:
            excel_recipient_rows, excel_parse_error = parse_recipients_excel(recipient_excel_file)
            if excel_parse_error:
                st.error(f"❌ {excel_parse_error}")
            else:
                st.success(f"✅ Loaded {len(excel_recipient_rows)} recipient row(s) from Excel.")
                st.caption("Excel rows will be used for To/CC/BCC while sending.")
        
        st.divider()
        
        # Email content section
        st.subheader("📝 Email Content")
        subject = st.text_input(
            "Subject",
            value=st.session_state.subject,
            key="subject_input",
            placeholder="Enter email subject"
        )
        st.session_state.subject = subject
        
        st.markdown("**Email Body (Rich Text)**")
        st.markdown(
            "Use the editor below to write your email with formatting, fonts, and styles.",
            help="You can use bold, italic, lists, headings, etc."
        )
        
        # Rich text editor using Streamlit Quill
        editor_content = st_quill(
            value=st.session_state.html_content,
            placeholder="Start typing your email here...",
            html=True,
            key="quill_editor"
        )
        st.session_state.html_content = editor_content
        
        st.divider()
        
        # Attachments section
        st.subheader("📎 Attachments")
        uploaded_files = st.file_uploader(
            "Upload files to attach",
            accept_multiple_files=True,
            key="file_uploader"
        )
        
        if uploaded_files:
            st.markdown("**Files to attach:**")
            for file in uploaded_files:
                st.caption(f"📄 {file.name} ({file.size / 1024:.1f} KB)")
    
    with col2:
        st.header("📋 Preview")
        
        # Preview section
        with st.container():
            st.markdown("**From:** " + sender_email)
            if excel_recipient_rows:
                total_to = sum(len(r["to"]) for r in excel_recipient_rows)
                st.markdown(f"**To:** *From Excel ({len(excel_recipient_rows)} row(s), {total_to} recipient(s))*")
            elif recipient_list:
                st.markdown("**To:** " + ", ".join(recipient_list))
                if len(recipient_list) > 1:
                    st.caption(f"Sending to {len(recipient_list)} recipients")
            else:
                st.markdown("**To:** *Not set*")
            if excel_recipient_rows:
                st.markdown("**CC/BCC:** *From Excel (row-wise)*")
            elif cc_emails:
                st.markdown("**CC:** " + cc_emails)
            if (not excel_recipient_rows) and bcc_emails:
                st.markdown("**BCC:** " + bcc_emails)
            st.markdown("**Subject:** " + (subject or "*Not set*"))
            
            st.divider()
            
            st.markdown("**Body Preview:**")
            if not editor_content or editor_content.strip() == "":
                st.info("Email body preview will appear here...")
            else:
                _, _, preview_email_html = build_final_email_payload(editor_content)
                components_html(preview_email_html, height=360, scrolling=True)
                st.caption("Preview uses the exact same HTML payload that will be sent.")
            
            if uploaded_files:
                st.markdown(f"**Attachments:** {len(uploaded_files)} file(s)")
        
        st.divider()
        
        # Action buttons
        col_send, col_draft = st.columns(2)
        
        with col_send:
            if st.button("✉️ Send Email", type="primary", use_container_width=True):
                has_excel_routing = recipient_excel_file is not None and not excel_parse_error and bool(excel_recipient_rows)
                if (not has_excel_routing) and (not recipient_list):
                    st.error("❌ Please enter at least one recipient email address.")
                elif recipient_excel_file is not None and excel_parse_error:
                    st.error("❌ Please fix the recipient Excel file errors before sending.")
                elif not subject:
                    st.error("❌ Please enter an email subject.")
                elif not editor_content or editor_content.strip() == "" or editor_content == "<p><br></p>":
                    st.error("❌ Please write an email body.")
                elif not sender_email:
                    st.error("❌ Please set the sender email address.")
                elif not smtp_user:
                    st.error("❌ Please enter your SMTP username.")
                elif not smtp_pass:
                    st.error("❌ Please enter your SMTP password.")
                else:
                    cc_list = parse_email_list(cc_emails) or None
                    bcc_list = parse_email_list(bcc_emails) or None
                    
                    def _create_message(
                        to_address: str,
                        html_body: str,
                        body_text: str,
                        attachments: Optional[list],
                        cc_override: Optional[list] = None,
                        bcc_override: Optional[list] = None,
                    ):
                        return build_message(
                            sender=sender_email,
                            recipient=to_address,
                            subject=subject,
                            body=body_text,
                            html_body=html_body,
                            cc=cc_override if cc_override is not None else cc_list,
                            bcc=bcc_override if bcc_override is not None else bcc_list,
                            attachments=attachments,
                        )

                    try:
                        _, body_text, email_html = build_final_email_payload(editor_content)
                        attachment_paths = None
                        delivered_recipients = 0
                        total_targets = len(excel_recipient_rows) if has_excel_routing else len(recipient_list)
                        if uploaded_files:
                            attachment_paths = []
                            with tempfile.TemporaryDirectory() as tmpdir:
                                for uploaded in uploaded_files:
                                    path = Path(tmpdir) / uploaded.name
                                    with path.open("wb") as f:
                                        f.write(uploaded.read())
                                    attachment_paths.append(str(path))

                                if has_excel_routing:
                                    sent_count = 0
                                    with st.spinner("Sending emails from Excel..."):
                                        for row_data in excel_recipient_rows:
                                            msg = _create_message(
                                                ", ".join(row_data["to"]),
                                                email_html,
                                                body_text,
                                                attachment_paths,
                                                cc_override=row_data["cc"] or None,
                                                bcc_override=row_data["bcc"] or None,
                                            )
                                            if send_message(
                                                smtp_host=smtp_host,
                                                smtp_port=smtp_port,
                                                message=msg,
                                                smtp_user=smtp_user,
                                                smtp_pass=smtp_pass,
                                            ):
                                                sent_count += 1
                                    delivered_recipients = sent_count
                                elif send_individually:
                                    sent_count = 0
                                    with st.spinner("Sending emails..."):
                                        for recipient in recipient_list:
                                            msg = _create_message(recipient, email_html, body_text, attachment_paths)
                                            if send_message(
                                                smtp_host=smtp_host,
                                                smtp_port=smtp_port,
                                                message=msg,
                                                smtp_user=smtp_user,
                                                smtp_pass=smtp_pass,
                                            ):
                                                sent_count += 1
                                    delivered_recipients = sent_count
                                else:
                                    msg = _create_message(", ".join(recipient_list), email_html, body_text, attachment_paths)
                                    with st.spinner("Sending email..."):
                                        sent_count = 1 if send_message(
                                            smtp_host=smtp_host,
                                            smtp_port=smtp_port,
                                            message=msg,
                                            smtp_user=smtp_user,
                                            smtp_pass=smtp_pass,
                                        ) else 0
                                        delivered_recipients = len(recipient_list) if sent_count else 0
                        else:
                            if has_excel_routing:
                                sent_count = 0
                                with st.spinner("Sending emails from Excel..."):
                                    for row_data in excel_recipient_rows:
                                        msg = _create_message(
                                            ", ".join(row_data["to"]),
                                            email_html,
                                            body_text,
                                            None,
                                            cc_override=row_data["cc"] or None,
                                            bcc_override=row_data["bcc"] or None,
                                        )
                                        if send_message(
                                            smtp_host=smtp_host,
                                            smtp_port=smtp_port,
                                            message=msg,
                                            smtp_user=smtp_user,
                                            smtp_pass=smtp_pass,
                                        ):
                                            sent_count += 1
                                delivered_recipients = sent_count
                            elif send_individually:
                                sent_count = 0
                                with st.spinner("Sending emails..."):
                                    for recipient in recipient_list:
                                        msg = _create_message(recipient, email_html, body_text, None)
                                        if send_message(
                                            smtp_host=smtp_host,
                                            smtp_port=smtp_port,
                                            message=msg,
                                            smtp_user=smtp_user,
                                            smtp_pass=smtp_pass,
                                        ):
                                            sent_count += 1
                                delivered_recipients = sent_count
                            else:
                                msg = _create_message(", ".join(recipient_list), email_html, body_text, None)
                                with st.spinner("Sending email..."):
                                    sent_count = 1 if send_message(
                                        smtp_host=smtp_host,
                                        smtp_port=smtp_port,
                                        message=msg,
                                        smtp_user=smtp_user,
                                        smtp_pass=smtp_pass,
                                    ) else 0
                                    delivered_recipients = len(recipient_list) if sent_count else 0

                        if delivered_recipients == total_targets:
                            if has_excel_routing:
                                st.success(f"✅ Email sent successfully for all {delivered_recipients} Excel row(s)!")
                            else:
                                st.success(f"✅ Email sent successfully to {delivered_recipients} recipient(s)!")
                        elif delivered_recipients > 0:
                            if has_excel_routing:
                                st.warning(f"⚠️ Email sent for {delivered_recipients} out of {total_targets} Excel row(s).")
                            else:
                                st.warning(f"⚠️ Email sent to {delivered_recipients} out of {len(recipient_list)} recipient(s).")
                        else:
                            st.error("❌ Failed to send email(s). Check SMTP settings.")
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
        
        with col_draft:
            if st.button("💾 Save Draft", use_container_width=True):
                st.info("💡 Draft saving feature coming soon!")


if __name__ == "__main__":
    main()
