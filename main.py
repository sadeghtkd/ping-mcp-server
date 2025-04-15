from typing import Any
import subprocess
import platform
import asyncio
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from mcp.server.sse import SseServerTransport
from starlette.requests import Request
from starlette.routing import Mount, Route
from mcp.server import Server
import uvicorn

# Initialize FastMCP server for Ping tools (SSE)
mcp = FastMCP("ping")

async def run_ping_command(host: str, count: int = 4) -> str:
    """Run the ping command and return its output."""
    # Determine the correct ping command based on the OS
    current_os = platform.system().lower()
    
    if current_os == "windows":
        cmd = ["ping", "-n", str(count), host]
    else:  # Unix-like systems (Linux, macOS)
        cmd = ["ping", "-c", str(count), host]
    
    try:
        # Run the ping command asynchronously
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            return stdout.decode('utf-8')
        else:
            return f"Error: {stderr.decode('utf-8')}"
    except Exception as e:
        return f"Failed to execute ping command: {str(e)}"

@mcp.tool()
async def ping_host(host: str, count: int = 4) -> str:
    """Ping a specified host.

    Args:
        host: The hostname or IP address to ping
        count: Number of ping packets to send (default: 4)
    """
    if count < 1 or count > 20:
        return "Error: Count must be between 1 and 20."
    
    result = await run_ping_command(host, count)
    return result

@mcp.tool()
async def check_connectivity(host: str = "8.8.8.8") -> str:
    """Check if the internet connection is working by pinging a reliable host.

    Args:
        host: The hostname or IP address to ping (default: 8.8.8.8, Google's DNS)
    """
    result = await run_ping_command(host, 1)
    
    # Simple analysis of the ping result
    if "time=" in result.lower() or "bytes from" in result.lower():
        return f"Internet connection is working! Successfully pinged {host}.\n\n{result}"
    else:
        return f"Internet connection seems to be down or there's an issue reaching {host}.\n\n{result}"

def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
    """Create a Starlette application that can server the provided mcp server with SSE."""
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> None:
        async with sse.connect_sse(
                request.scope,
                request.receive,
                request._send,  # noqa: SLF001
        ) as (read_stream, write_stream):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options(),
            )

    return Starlette(
        debug=debug,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )

if __name__ == "__main__":
    mcp_server = mcp._mcp_server  # noqa: WPS437

    import argparse
    
    parser = argparse.ArgumentParser(description='Run MCP SSE-based Ping server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8080, help='Port to listen on')
    args = parser.parse_args()

    # Bind SSE request handling to MCP server
    starlette_app = create_starlette_app(mcp_server, debug=True)

    print(f"Starting Ping MCP Server on {args.host}:{args.port}")
    print("Available tools:")
    print("  - ping_host: Ping a specified host")
    print("  - check_connectivity: Check if internet connection is working")
    
    uvicorn.run(starlette_app, host=args.host, port=args.port)