"""
Thin wrapper around MCP client sessions. New tools = a new MCP server
added to `_SERVERS` below -- no orchestrator code changes required.
"""

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

_SERVERS = {
    "fund_data": StdioServerParameters(command="python", args=["-m", "app.mcp_servers.fund_data_server"]),
    "document_retrieval": StdioServerParameters(command="python", args=["-m", "app.mcp_servers.document_retrieval_server"]),
    "distributor_profile": StdioServerParameters(command="python", args=["-m", "app.mcp_servers.distributor_profile_server"]),
}


class MCPToolRegistry:
    def __init__(self):
        self._sessions: dict[str, ClientSession] = {}
        self._tool_to_server: dict[str, str] = {}

    async def connect_all(self):
        for server_name, params in _SERVERS.items():
            read, write = await stdio_client(params).__aenter__()
            session = ClientSession(read, write)
            await session.initialize()
            self._sessions[server_name] = session

            tools = await session.list_tools()
            for tool in tools.tools:
                self._tool_to_server[tool.name] = server_name

    def list_tool_schemas(self) -> list[dict]:
        # In a full build, cache and flatten each server's list_tools() result
        # into Claude's tool schema format here.
        return []

    async def call(self, tool_name: str, tool_input: dict):
        server_name = self._tool_to_server.get(tool_name)
        if server_name is None:
            return {"error": f"unknown tool: {tool_name}"}
        session = self._sessions[server_name]
        result = await session.call_tool(tool_name, tool_input)
        return result
