# EmailAgent 📧🤖

An intelligent email monitoring and notification system that automatically fetches, processes, and summarizes emails from specific domains, then sends WhatsApp notifications via Twilio. Features AI-powered summarization using Google's Gemini API and comprehensive confidentiality protection.

## ✨ Features

- 🔄 **Real-time Email Monitoring**: Continuously polls IMAP inbox for new emails
- 🎯 **Domain Filtering**: Monitors emails from specific domains only
- 🤖 **AI-Powered Summarization**: Uses Google Gemini API for intelligent email summarization
- 🔒 **Confidentiality Protection**: Automatic detection and redaction of sensitive information
- 📱 **WhatsApp Notifications**: Sends summaries via Twilio WhatsApp Business API
- 🌐 **Web Dashboard**: Beautiful Flask-based UI for monitoring and control
- 🔐 **PII Redaction**: Automatically redacts emails, phone numbers, credit cards, SSNs, API keys, passwords, IPs, and tokens
- 📊 **Summary History**: Tracks and displays all processed emails with timestamps

## 🛡️ Security Features

### Confidentiality Detection
- Detects confidential markers in email content
- Prevents sensitive emails from being sent to external LLMs
- Configurable confidential keywords list
- Automatic flagging and special handling of sensitive content

### Data Redaction
Automatically redacts:
- Email addresses
- Phone numbers
- Credit card numbers
- Social Security Numbers (SSNs)
- API keys and tokens
- Passwords
- IP addresses
- Bearer tokens and JWTs

## 🏗️ Architecture

```
EmailAgent/
├── app.py                      # Flask web application
├── main.py                     # Core email monitoring logic
├── templates/
│   └── index.html             # Web dashboard UI
├── email_summaries.json        # Stored summaries
├── processed_emails.json       # Processed email tracking
├── last_check_timestamp.txt    # Timestamp tracking
├── .env                        # Environment configuration (not in repo)
├── .env.example               # Example environment file
└── README.md                   # This file
```

## 🚀 Quick Start

### Prerequisites

- Python 3.12 or higher
- Gmail account with IMAP enabled and App Password
- Twilio account with WhatsApp Business API access
- Google Gemini API key

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/GokulanV7/EmailAgent.git
   cd EmailAgent
   ```

2. **Install dependencies**
   ```bash
   pip install requests python-dotenv twilio google-generativeai flask
   ```

3. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your actual credentials
   ```

4. **Enable Gmail IMAP Access**
   - Go to Gmail Settings → See all settings → Forwarding and POP/IMAP
   - Enable IMAP
   - Create an App Password (if using 2FA): Google Account → Security → 2-Step Verification → App passwords

### Running the Application

#### Option 1: Web Dashboard (Recommended)
```bash
python app.py
```
Visit `http://localhost:5000` to access the web dashboard where you can:
- Start/stop email monitoring
- View real-time status
- Browse email summaries
- See processing statistics

#### Option 2: Command Line
```bash
python main.py
```
Runs the email monitor directly in the terminal.

## ⚙️ Configuration

All configuration is managed through environment variables in the `.env` file:

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `IMAP_HOST` | IMAP server hostname | `imap.gmail.com` |
| `IMAP_USER` | Email account username | `your.email@gmail.com` |
| `IMAP_PASS` | Email account password/app password | `your_app_password` |
| `GEMINI_API_KEY` | Google Gemini API key | `AIzaSy...` |
| `TWILIO_ACCOUNT_SID` | Twilio account SID | `AC...` |
| `TWILIO_AUTH_TOKEN` | Twilio auth token | `...` |
| `TWILIO_WHATSAPP_FROM` | Twilio WhatsApp number | `whatsapp:+14155238886` |
| `RECIPIENT_NUMBER` | WhatsApp recipient number | `+1234567890` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DOMAIN_FILTER` | Filter emails from specific domain | `@example.com` |
| `POLL_SECONDS` | Email check interval (seconds) | `30` |
| `ENABLE_CONFIDENTIALITY_CHECK` | Enable confidentiality detection | `true` |
| `CONFIDENTIAL_KEYWORDS` | Comma-separated confidential keywords | `confidential,internal,...` |
| `CONTENT_SID` | Twilio Content Template SID (optional) | - |

## 📱 Twilio WhatsApp Setup

1. Create a Twilio account at https://www.twilio.com/
2. Set up WhatsApp Sandbox or get approved WhatsApp Business API access
3. Get your Account SID and Auth Token from Twilio Console
4. Note your Twilio WhatsApp number (usually `whatsapp:+14155238886` for sandbox)
5. Send join code to your WhatsApp number to activate the connection

## 🤖 Google Gemini API Setup

1. Visit https://makersuite.google.com/app/apikey
2. Create a new API key
3. Add the key to your `.env` file as `GEMINI_API_KEY`

## 📖 Usage Examples

### Web Dashboard
Access the web interface to:
- **Start monitoring**: Click the "Start Monitoring" button
- **Stop monitoring**: Click the "Stop Monitoring" button
- **View summaries**: Browse all processed email summaries with timestamps
- **Check status**: Real-time monitoring status indicator

### Programmatic Usage
```python
import main

# Start monitoring with a stop event
import threading
stop_event = threading.Event()
main.start_monitoring(stop_event)

# Stop monitoring
stop_event.set()
```

## 🔒 Confidentiality Handling

When an email contains confidential markers:
1. Email is flagged as confidential
2. Summary explicitly notes "CONFIDENTIAL EMAIL DETECTED"
3. Content is NOT sent to external LLM APIs
4. A generic notice is generated instead
5. Redacted data remains masked

Example output for confidential email:
```
⚠️ CONFIDENTIAL EMAIL DETECTED (markers: confidential, internal)
Subject: Important Internal Matter
From: sender@company.com

[CONFIDENTIAL_CONTENT_NOT_PROCESSED]
This email contains confidential markers and has not been sent to external APIs.
```

## 🧪 Testing

Test the email monitoring system:
1. Send a test email to your monitored address from a domain matching `DOMAIN_FILTER`
2. Check the console output or web dashboard for processing confirmation
3. Verify WhatsApp notification arrival
4. Review the summary in `email_summaries.json`

## 📝 Data Persistence

- **email_summaries.json**: Stores all email summaries with metadata
- **processed_emails.json**: Tracks processed email IDs to avoid duplicates
- **last_check_timestamp.txt**: Maintains the last check timestamp for incremental processing

## 🛠️ Troubleshooting

### Common Issues

**IMAP Connection Failed**
- Verify IMAP is enabled in Gmail settings
- Check if you're using an App Password (required for 2FA accounts)
- Ensure firewall allows IMAP connections

**Twilio WhatsApp Not Working**
- Verify you've joined the WhatsApp sandbox with the join code
- Check that recipient number includes country code with `+`
- Ensure Account SID and Auth Token are correct

**Gemini API Errors**
- Verify API key is valid and active
- Check API quotas and rate limits
- Ensure the API is enabled in Google Cloud Console

**No Emails Detected**
- Confirm `DOMAIN_FILTER` matches sender domains
- Check if emails are actually arriving in INBOX (not spam/filtered)
- Verify timestamp file for incremental checking

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is open source and available under the MIT License.

## 🔗 Links

- [Twilio Documentation](https://www.twilio.com/docs/whatsapp)
- [Google Gemini API](https://ai.google.dev/)
- [Gmail IMAP Guide](https://support.google.com/mail/answer/7126229)

## 👤 Author

**GokulanV7**
- GitHub: [@GokulanV7](https://github.com/GokulanV7)

## 🙏 Acknowledgments

- Google Gemini for AI-powered summarization
- Twilio for WhatsApp Business API
- Flask for web framework
- All contributors and users of this project

---

Made with ❤️ by GokulanV7
