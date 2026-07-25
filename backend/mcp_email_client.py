import os
import sys
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "email_mcp_server.py")


@asynccontextmanager
async def email_mcp_session():
    # StdioServerParameters(env=None) does NOT inherit the parent environment --
    # the MCP SDK passes only a minimal safe subset, which strips GMAIL_ADDRESS
    # and GMAIL_APP_PASSWORD. Locally the server still found them via .env, but
    # in a container (no .env file) the subprocess would have no credentials.
    params = StdioServerParameters(
        command=sys.executable, args=[SERVER_SCRIPT], env=dict(os.environ)
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def send_email_via_mcp(session, to, subject, body):
    result = await session.call_tool(
        "send_email", arguments={"to": to, "subject": subject, "body": body}
    )
    # MCP reports tool failures as a result with isError=True rather than by
    # raising, so without this check a failed send looks identical to success.
    if getattr(result, "isError", False):
        detail = result.content[0].text if result.content else "unknown MCP error"
        raise RuntimeError(detail)
    return result.content[0].text
