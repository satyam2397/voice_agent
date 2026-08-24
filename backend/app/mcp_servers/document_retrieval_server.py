"""
MCP server: document_retrieval

Vector search over fund_documents.embedding (pgvector). If the vector store
is unreachable, this must degrade gracefully -- return an empty/cached
result rather than raising and crashing the whole pipeline.
"""

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from sentence_transformers import SentenceTransformer

from app.db.models import FundDocument
from app.db.session import SessionLocal

server = Server("document_retrieval")
_embedder = SentenceTransformer("all-MiniLM-L6-v2")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_fund_documents",
            description="Semantic search over factsheets, commentary, and brochures for a fund.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 3},
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name != "search_fund_documents":
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    query_embedding = _embedder.encode(arguments["query"]).tolist()
    top_k = arguments.get("top_k", 3)

    session = SessionLocal()
    try:
        results = (
            session.query(FundDocument)
            .order_by(FundDocument.embedding.cosine_distance(query_embedding))
            .limit(top_k)
            .all()
        )
        if not results:
            return [TextContent(type="text", text="No matching documents found.")]
        return [TextContent(type="text", text=doc.chunk_text) for doc in results]
    except Exception:
        # Degrade gracefully -- don't take down the pipeline over a DB blip.
        return [TextContent(type="text", text="[document retrieval unavailable, continuing without it]")]
    finally:
        session.close()


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
