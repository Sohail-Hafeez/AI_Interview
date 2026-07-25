import os
import requests

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDER_EMAIL = os.getenv("GMAIL_ADDRESS")

mcp = FastMCP("email-server")


@mcp.tool()
def send_email(to: str, subject: str, body: str) -> str:
    """Send a plain-text email via SendGrid."""
    if not SENDGRID_API_KEY or not SENDER_EMAIL:
        raise RuntimeError("SENDGRID_API_KEY or GMAIL_ADDRESS missing from .env")

    response = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": SENDER_EMAIL},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        },
        timeout=15,
    )
    response.raise_for_status()

    return f"Email sent to {to}"


if __name__ == "__main__":
    mcp.run()
