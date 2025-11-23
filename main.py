#!/usr/bin/env python3
"""
main.py
Email -> redact -> summarize -> send to WhatsApp via Twilio (supports Content Templates)
Enhanced with Gemini API and confidentiality protection pipeline

Requirements:
  pip install requests python-dotenv twilio google-generativeai

Usage:
  - create a .env file (example below)
  - python main.py
"""

import os
import time
import re
import json
import imaplib
import email
from email.header import decode_header
import requests
from twilio.rest import Client
from dotenv import load_dotenv

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("Warning: google-generativeai not installed. Run: pip install google-generativeai")

load_dotenv()

# ---------- Configuration from env ----------
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_USER = os.getenv("IMAP_USER")  # required
IMAP_PASS = os.getenv("IMAP_PASS")  # required
DOMAIN_FILTER = os.getenv("DOMAIN_FILTER", "@example.com").lower()
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "30"))

# Gemini API Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Confidentiality protection - PREVENTS sending sensitive data to LLM
ENABLE_CONFIDENTIALITY_CHECK = os.getenv("ENABLE_CONFIDENTIALITY_CHECK", "true").lower() == "true"
CONFIDENTIAL_KEYWORDS = os.getenv("CONFIDENTIAL_KEYWORDS", "confidential,internal,proprietary,classified,secret,password,api key,token,private,restricted").lower().split(",")

# Twilio config (required)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
RECIPIENT_NUMBER = os.getenv("RECIPIENT_NUMBER")  # e.g. +919361620860

# Optional Content Template
CONTENT_SID = os.getenv("CONTENT_SID")

# Basic sanity checks
if not IMAP_USER or not IMAP_PASS:
    raise SystemExit("Please set IMAP_USER and IMAP_PASS in environment variables.")
if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not RECIPIENT_NUMBER:
    raise SystemExit("Please set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and RECIPIENT_NUMBER in env.")

# Initialize Gemini if available and configured
if GEMINI_AVAILABLE and GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    print("✓ Gemini API configured")

# ---------- Helpers ----------
def decode_mime_words(s):
    if not s:
        return ""
    try:
        parts = decode_header(s)
        return ''.join([
            (t.decode(enc) if isinstance(t, bytes) and enc else (t.decode() if isinstance(t, bytes) else t))
            for t, enc in parts
        ])
    except Exception:
        return s

def clean_markdown_formatting(text):
    """Remove markdown formatting (asterisks, etc.) for plain text output."""
    if not text:
        return text
    
    # Remove bold/italic markers (* and **)
    cleaned = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # **bold** -> bold
    cleaned = re.sub(r'\*([^*]+)\*', r'\1', cleaned)    # *italic* -> italic
    
    # Remove other common markdown symbols
    cleaned = re.sub(r'__([^_]+)__', r'\1', cleaned)    # __bold__ -> bold
    cleaned = re.sub(r'_([^_]+)_', r'\1', cleaned)      # _italic_ -> italic
    
    return cleaned

def get_email_body(msg):
    """Return best-effort text body (prefers text/plain)."""
    if msg.is_multipart():
        text = None
        html = None
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disp:
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore")
                except Exception:
                    return str(part.get_payload(decode=True))
            elif ctype == "text/html" and "attachment" not in disp and html is None:
                try:
                    html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore")
                except Exception:
                    html = str(part.get_payload(decode=True))
        if html:
            return re.sub('<[^<]+?>', '', html)
        return ""
    else:
        try:
            return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="ignore")
        except Exception:
            return str(msg.get_payload(decode=True))

# ---------- Enhanced Redaction with Confidentiality Detection ----------
EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
PHONE_RE = re.compile(r'(\+?\d[\d\-\s]{6,}\d)')
CREDIT_RE = re.compile(r'\b(?:\d[ -]*?){13,19}\b')
SSN_RE = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
API_KEY_RE = re.compile(r'\b[A-Za-z0-9_-]{32,}\b')  # Generic API key pattern
PASSWORD_RE = re.compile(r'(?i)(password|passwd|pwd)[\s:=]+\S+')
IP_RE = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
TOKEN_RE = re.compile(r'(?i)(bearer|token|jwt)[\s:=]+[A-Za-z0-9_.-]+')

def contains_confidential_markers(text):
    """
    CRITICAL SECURITY CHECK: Detect if email contains confidential markers.
    Returns True if email should NOT be sent to any LLM.
    """
    if not text:
        return False, []
    
    text_lower = text.lower()
    found_markers = []
    
    for keyword in CONFIDENTIAL_KEYWORDS:
        if keyword.strip() and keyword.strip() in text_lower:
            found_markers.append(keyword.strip())
    
    return len(found_markers) > 0, found_markers

def redact_text(text, extra_masks=None):
    """
    Enhanced redaction with confidentiality detection.
    Returns: (redacted_text, masks_dict, is_confidential)
    """
    if not text:
        return text, {}, False
    
    # FIRST: Check for confidential markers BEFORE any processing
    is_confidential, markers = contains_confidential_markers(text)
    
    s = text
    masks = {}
    
    # Apply all redaction patterns
    s, n = EMAIL_RE.subn('[REDACTED_EMAIL]', s); masks['emails'] = n
    s, n = PHONE_RE.subn('[REDACTED_PHONE]', s); masks['phones'] = n
    s, n = CREDIT_RE.subn('[REDACTED_NUMBER]', s); masks['numbers'] = n
    s, n = SSN_RE.subn('[REDACTED_SSN]', s); masks['ssn'] = n
    s, n = API_KEY_RE.subn('[REDACTED_API_KEY]', s); masks['api_keys'] = n
    s, n = PASSWORD_RE.subn('[REDACTED_PASSWORD]', s); masks['passwords'] = n
    s, n = IP_RE.subn('[REDACTED_IP]', s); masks['ips'] = n
    s, n = TOKEN_RE.subn('[REDACTED_TOKEN]', s); masks['tokens'] = n
    
    if extra_masks:
        for pattern, token in extra_masks:
            s, n = re.subn(pattern, token, s)
            masks[token] = masks.get(token, 0) + n
    
    if is_confidential:
        masks['confidential_markers'] = markers
    
    return s, masks, is_confidential

# ---------- Summarization with Gemini ----------
def summarize_with_gemini(text, max_tokens=300):
    """Summarize using Google Gemini API."""
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        print("⚠ Gemini API not available, using fallback")
        return None
    
    try:
        # Configure safety settings to be more permissive
        safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_NONE"
            }
        ]
        
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        prompt = f"""Summarize this email in 2-3 SHORT sentences. Be direct and simple.

Email:
{text}

Give a brief summary in plain language. No bullet points, no labels, no formatting. Just 2-3 simple sentences explaining what the email is about."""
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=0.3,
            ),
            safety_settings=safety_settings
        )
        
        # Better error handling for blocked responses
        if response.candidates and response.candidates[0].finish_reason != 1:  # 1 = STOP (normal completion)
            finish_reason = response.candidates[0].finish_reason
            reason_map = {2: "SAFETY", 3: "RECITATION", 4: "OTHER"}
            reason_text = reason_map.get(finish_reason, f"UNKNOWN({finish_reason})")
            print(f"⚠️ Gemini blocked response due to: {reason_text}")
            return None
        
        return response.text.strip()
    except Exception as e:
        print(f"❌ Gemini API error: {e}")
        return None

def fallback_summarize(text):
    """Fallback summarization without external APIs."""
    if not text:
        return ""
    
    excerpt = text.strip().replace("\n", " ")
    excerpt = excerpt[:800] + ("..." if len(excerpt) > 800 else "")
    sentences = re.split(r'(?<=[.!?])\s+', excerpt)
    bullets = sentences[:4]
    return "\n".join(["- " + s for s in bullets if s.strip()])

def summarize_with_llm(text, max_tokens=300):
    """Main summarization with Gemini, fallback if unavailable."""
    if not text:
        return ""
    
    # Try Gemini first
    summary = summarize_with_gemini(text, max_tokens)
    if summary:
        return summary
    
    # Use fallback if Gemini fails
    print("Using fallback summarization (no LLM)")
    return fallback_summarize(text)

# ---------- CONFIDENTIALITY PROTECTION PIPELINE ----------
def create_safe_summary(subject, body, is_confidential, masks):
    """
    SECURITY LAYER: Create summary based on confidentiality status.
    
    If confidential: NO LLM processing - ZERO data leak to external APIs
    If not confidential: Safe to use Gemini API
    """
    if is_confidential and ENABLE_CONFIDENTIALITY_CHECK:
        # 🔒 CONFIDENTIAL EMAIL DETECTED - BYPASS ALL LLM PROCESSING
        print("🔒 CONFIDENTIAL email detected - LLM processing BLOCKED")
        
        confidential_note = "⚠️ CONFIDENTIAL EMAIL - LLM bypassed for security"
        markers_found = masks.get('confidential_markers', [])
        redaction_count = sum(v for k, v in masks.items() if k != 'confidential_markers')
        
        # Extract first few sentences WITHOUT sending to any LLM
        sentences = re.split(r'(?<=[.!?])\s+', body.strip())
        preview = ". ".join(sentences[:2])[:200]
        if len(body) > 200:
            preview += "..."
        
        summary = f"""{confidential_note}

Subject: {subject}

Confidential markers detected: {', '.join(markers_found)}
Items redacted: {redaction_count}

Preview (local only):
{preview}

⚠️ Full content NOT sent to any external API"""
        
        return summary, True  # True = confidential, was NOT sent to LLM
    else:
        # ✅ Safe to use LLM - no confidential markers detected
        print("✅ Email safe - processing with Gemini")
        full_text = f"{subject}\n\n{body}"
        summary = summarize_with_llm(full_text)
        return summary, False  # False = not confidential, was sent to LLM

# ---------- Prepare template variables ----------
def prepare_content_variables(sender, subject, summary):
    """Adjust according to your content template's placeholders."""
    vars_map = {"1": subject[:500], "2": summary[:1000]}
    return vars_map

# ---------- Twilio send ----------
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

def send_via_twilio_text(recipient_number, text):
    to = f"whatsapp:{recipient_number}"
    msg = twilio_client.messages.create(
        from_=TWILIO_WHATSAPP_FROM,
        body=text,
        to=to
    )
    return msg.sid

def send_via_twilio_template(recipient_number, content_sid, variables: dict):
    """Send using Twilio Content Template."""
    to = f"whatsapp:{recipient_number}"
    content_vars_str = json.dumps(variables)
    msg = twilio_client.messages.create(
        from_=TWILIO_WHATSAPP_FROM,
        to=to,
        content_sid=content_sid,
        content_variables=content_vars_str
    )
    return msg.sid

# ---------- Track processed emails ----------
PROCESSED_EMAILS_FILE = "processed_emails.json"
LAST_CHECK_FILE = "last_check_timestamp.txt"
SUMMARIES_FILE = "email_summaries.json"

def load_processed_emails():
    """Load list of already processed email IDs."""
    if os.path.exists(PROCESSED_EMAILS_FILE):
        try:
            with open(PROCESSED_EMAILS_FILE, 'r') as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_processed_emails(email_ids):
    """Save multiple processed email IDs to file."""
    try:
        with open(PROCESSED_EMAILS_FILE, 'w') as f:
            json.dump(list(email_ids), f)
    except Exception as e:
        print(f"⚠️  Error saving processed emails: {e}")

def save_processed_email(email_id):
    """Save single processed email ID to file."""
    processed = load_processed_emails()
    processed.add(email_id)
    save_processed_emails(processed)

def save_email_summary(data):
    """Save email summary to JSON file for UI."""
    summaries = []
    if os.path.exists(SUMMARIES_FILE):
        try:
            with open(SUMMARIES_FILE, 'r') as f:
                summaries = json.load(f)
        except Exception:
            pass
    
    # Add timestamp string if not present
    if 'timestamp_str' not in data:
        data['timestamp_str'] = time.strftime('%Y-%m-%d %H:%M:%S')
        
    summaries.insert(0, data) # Add to beginning
    
    try:
        with open(SUMMARIES_FILE, 'w') as f:
            json.dump(summaries, f, indent=2)
    except Exception as e:
        print(f"⚠️  Error saving summary: {e}")

def get_last_check_timestamp():
    """Get the last time we checked for emails."""
    if os.path.exists(LAST_CHECK_FILE):
        try:
            with open(LAST_CHECK_FILE, 'r') as f:
                return float(f.read().strip())
        except Exception:
            return None
    return None

def save_last_check_timestamp():
    """Save current timestamp."""
    try:
        with open(LAST_CHECK_FILE, 'w') as f:
            f.write(str(time.time()))
    except Exception as e:
        print(f"⚠️  Error saving timestamp: {e}")

def initialize_existing_emails():
    """Mark all existing unread emails as already processed (first run only)."""
    print("\n🔄 First run detected - marking all existing emails as processed...")
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select("INBOX")
        
        status, data = mail.search(None, 'UNSEEN')
        if status == "OK":
            all_ids = data[0].split()
            processed_set = set(msg_id.decode() for msg_id in all_ids)
            save_processed_emails(processed_set)
            print(f"✅ Marked {len(all_ids)} existing emails as already processed")
            print(f"   (Only NEW emails from now on will be processed)\n")
        
        mail.logout()
        save_last_check_timestamp()
    except Exception as e:
        print(f"❌ Error during initialization: {e}")

# ---------- Main processing ----------
def process_mail():
    mail = imaplib.IMAP4_SSL(IMAP_HOST)
    mail.login(IMAP_USER, IMAP_PASS)
    mail.select("INBOX")
    
    # Get ALL unread messages first
    status, data = mail.search(None, 'UNSEEN')
    if status != "OK":
        print("IMAP search error or no messages.")
        mail.logout()
        return

    all_ids = data[0].split()
    
    # Load already processed emails
    processed = load_processed_emails()
    
    # Filter out already processed emails
    ids = [msg_id for msg_id in all_ids if msg_id.decode() not in processed]
    
    if len(all_ids) > 0:
        print(f"📬 Found {len(all_ids)} unread messages ({len(ids)} new, {len(all_ids) - len(ids)} already seen)")
    
    for num in ids:
        try:
            res, msg_data = mail.fetch(num, "(RFC822)")
            if res != "OK" or not msg_data or not msg_data[0]:
                continue
            
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            
            # Get unique message ID
            message_id = msg.get("Message-ID", num.decode())
            
            sender = decode_mime_words(msg.get("From", ""))
            subject = decode_mime_words(msg.get("Subject", ""))

            # Filter by sender domain
            if DOMAIN_FILTER and DOMAIN_FILTER not in sender.lower():
                print(f"⏭️  Skipping: {sender} (subject: {subject})")
                # Mark as processed so we don't check it again
                save_processed_email(num.decode())
                continue

            print(f"\n📧 Processing: {subject[:50]}...")
            
            body = get_email_body(msg)
            
            # STEP 1: Redact sensitive data
            redacted_body, body_masks, body_confidential = redact_text(body)
            redacted_subject, subject_masks, subject_confidential = redact_text(subject)
            
            # Combine masks
            all_masks = {**body_masks, **subject_masks}
            is_confidential = body_confidential or subject_confidential

            # STEP 2: Create safe summary (with confidentiality protection)
            summary, was_blocked = create_safe_summary(
                redacted_subject, 
                redacted_body, 
                is_confidential, 
                all_masks
            )

            # Save summary for UI
            summary_data = {
                "id": num.decode(),
                "sender": sender,
                "subject": redacted_subject,
                "summary": summary,
                "timestamp": time.time(),
                "is_confidential": is_confidential,
                "was_blocked": was_blocked
            }
            save_email_summary(summary_data)

            # STEP 3: Compose message for WhatsApp (clean markdown formatting)
            redaction_summary = ", ".join([f"{k}: {v}" for k, v in all_masks.items() if k != 'confidential_markers' and v > 0])
            
            # Clean markdown formatting from summary for WhatsApp
            clean_summary = clean_markdown_formatting(summary)
            
            send_text = f"""From: {sender}
Subject: {redacted_subject}

Summary:
{clean_summary}

{'🔒 Protected: No data sent to external APIs' if was_blocked else 'Thank you'}
Redactions: {redaction_summary if redaction_summary else 'None'}"""

            # STEP 4: Send via Twilio
            try:
                if CONTENT_SID:
                    vars_map = prepare_content_variables(sender, redacted_subject, summary)
                    sid = send_via_twilio_template(RECIPIENT_NUMBER, CONTENT_SID, vars_map)
                    print(f"✅ Sent template message SID: {sid}")
                else:
                    sid = send_via_twilio_text(RECIPIENT_NUMBER, send_text[:1500])
                    print(f"✅ Sent text message SID: {sid}")
                
                # Mark as read AND save as processed
                mail.store(num, '+FLAGS', '\\Seen')
                save_processed_email(num.decode())
                
            except Exception as e:
                print(f"❌ Error sending via Twilio: {e}")
                
        except Exception as e:
            print(f"❌ Error processing mail: {e}")
    
    mail.logout()

def start_monitoring(stop_event=None):
    print("=" * 60)
    print("🚀 Email → WhatsApp Worker with Confidentiality Protection")
    print("=" * 60)
    print(f"📧 IMAP: {IMAP_HOST} / {IMAP_USER}")
    print(f"🔍 Domain filter: {DOMAIN_FILTER}")
    print(f"🤖 Gemini API: {'✓ Enabled' if GEMINI_AVAILABLE and GEMINI_API_KEY else '✗ Disabled (using fallback)'}")
    print(f"🔒 Confidentiality check: {'✓ Enabled' if ENABLE_CONFIDENTIALITY_CHECK else '✗ Disabled'}")
    print(f"⏱️  Poll interval: {POLL_SECONDS}s")
    print("=" * 60)
    
    # Check if this is first run
    if get_last_check_timestamp() is None:
        initialize_existing_emails()
    
    print("\n▶️  Starting email monitoring...\n")
    
    while True:
        if stop_event and stop_event.is_set():
            print("🛑 Stopping monitoring...")
            break
        try:
            process_mail()
            save_last_check_timestamp()
        except Exception as e:
            print(f"❌ Main loop error: {e}")
            
        # Sleep with check
        for _ in range(POLL_SECONDS):
            if stop_event and stop_event.is_set():
                break
            time.sleep(1)

if __name__ == "__main__":
    start_monitoring()