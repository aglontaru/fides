"""FastMCP server entry point."""

from __future__ import annotations

import sys

import structlog
from mcp.server.fastmcp import FastMCP

# Prevent duplicate FastMCP instance when invoked as `python -m fides.mcp_server.server`
if __name__ == "__main__" and "fides.mcp_server.server" not in sys.modules:
    sys.modules["fides.mcp_server.server"] = sys.modules[__name__]

logger = structlog.get_logger(__name__)

mcp = FastMCP(
    name="fides-tools",
    instructions="Shared tooling for the Fides legislation knowledge graph RAG system",
    host="0.0.0.0",  # noqa: S104
    port=8000,
)

# Import tool modules to register tools on the mcp instance
import fides.mcp_server.tools.diff_tools  # noqa: E402
import fides.mcp_server.tools.document_tools  # noqa: E402
import fides.mcp_server.tools.neo4j_tools  # noqa: E402
import fides.mcp_server.tools.vector_tools  # noqa: F401, E402


def main() -> None:
    """Run the FastMCP server."""
    tools = mcp._tool_manager.list_tools()
    logger.info("Starting MCP server", tool_count=len(tools), tool_names=[t.name for t in tools])
    mcp.run(transport="sse")


if __name__ == "__main__":
    main()
