import os
import sys
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "email_mcp_server.py")


@asynccontextmanager
async def email_mcp_session():
    params = StdioServerParameters(command=sys.executable, args=[SERVER_SCRIPT])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def send_email_via_mcp(session, to, subject, body):
    result = await session.call_tool(
        "send_email", arguments={"to": to, "subject": subject, "body": body}
    )
    return result.content[0].text
