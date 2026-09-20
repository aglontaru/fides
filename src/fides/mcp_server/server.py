"""FastMCP server entry point."""

from __future__ import annotations

import structlog
from mcp.server.fastmcp import FastMCP

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
    logger.info("Running MCP server on port 8000")
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
