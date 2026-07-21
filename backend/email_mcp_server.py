import os
import smtplib
from email.mime.text import MIMEText

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

mcp = FastMCP("email-server")


@mcp.tool()
def send_email(to: str, subject: str, body: str) -> str:
    """Send a plain-text email via Gmail SMTP."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        raise RuntimeError("GMAIL_ADDRESS or GMAIL_APP_PASSWORD missing from .env")

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, [to], msg.as_string())

    return f"Email sent to {to}"


if __name__ == "__main__":
    mcp.run()
