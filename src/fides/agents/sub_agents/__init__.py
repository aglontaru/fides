"""Sub-agents module for Fides autonomous multi-agent architecture."""

from __future__ import annotations

from fides.agents.sub_agents.diff_agent import (
    DIFF_AGENT_DESCRIPTION,
    DIFF_TOOL_NAMES,
    create_diff_subagent,
    filter_diff_tools,
)
from fides.agents.sub_agents.graph_builder_agent import (
    GRAPH_BUILDER_AGENT_DESCRIPTION,
    GRAPH_BUILDER_TOOL_NAMES,
    create_graph_builder_subagent,
    filter_graph_builder_tools,
)
from fides.agents.sub_agents.indexing_agent import (
    INDEXING_AGENT_DESCRIPTION,
    INDEXING_TOOL_NAMES,
    create_indexing_subagent,
    filter_indexing_tools,
)
from fides.agents.sub_agents.legal_agent import (
    LEGAL_AGENT_DESCRIPTION,
    create_legal_subagent,
)
from fides.agents.sub_agents.query_agent import (
    QUERY_AGENT_DESCRIPTION,
    QUERY_TOOL_NAMES,
    create_query_subagent,
    filter_query_tools,
)

__all__ = [
    "DIFF_AGENT_DESCRIPTION",
    "DIFF_TOOL_NAMES",
    "GRAPH_BUILDER_AGENT_DESCRIPTION",
    "GRAPH_BUILDER_TOOL_NAMES",
    "INDEXING_AGENT_DESCRIPTION",
    "INDEXING_TOOL_NAMES",
    "LEGAL_AGENT_DESCRIPTION",
    "QUERY_AGENT_DESCRIPTION",
    "QUERY_TOOL_NAMES",
    "create_diff_subagent",
    "create_graph_builder_subagent",
    "create_indexing_subagent",
    "create_legal_subagent",
    "create_query_subagent",
    "filter_diff_tools",
    "filter_graph_builder_tools",
    "filter_indexing_tools",
    "filter_query_tools",
]
