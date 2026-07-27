"""
HTTP API server using aiohttp.
"""

import asyncio

from aiohttp import web

from src.agents.memory_agent import MemoryAgent
from src.config import get_settings


def create_app(agent: MemoryAgent) -> web.Application:
    """Create and configure the aiohttp application."""
    app = web.Application()
    settings = get_settings()

    # Store agent reference in app state
    app["agent"] = agent
    app["settings"] = settings

    # Register routes
    app.router.add_get("/health", handle_health)
    app.router.add_get("/status", handle_status)
    app.router.add_get("/memories", handle_memories)
    app.router.add_get("/consolidations", handle_consolidations)
    app.router.add_get("/query", handle_query)
    app.router.add_get("/query/stream", handle_query_stream)
    app.router.add_post("/ingest", handle_ingest)
    app.router.add_post("/consolidate", handle_consolidate)
    app.router.add_post("/delete", handle_delete)
    app.router.add_post("/clear", handle_clear)

    return app


# ─── Route Handlers ────────────────────────────────────────────


async def handle_health(request: web.Request) -> web.Response:
    """Health check endpoint."""
    settings = request.app["settings"]
    return web.json_response({
        "status": "healthy",
        "model": settings.bedrock_model_id,
        "region": settings.aws_region,
    })


async def handle_status(request: web.Request) -> web.Response:
    """Memory statistics."""
    agent: MemoryAgent = request.app["agent"]
    stats = agent.get_stats()
    return web.json_response(stats)


async def handle_memories(request: web.Request) -> web.Response:
    """List all memories."""
    agent: MemoryAgent = request.app["agent"]
    data = agent.get_all_memories()
    return web.json_response(data)


async def handle_consolidations(request: web.Request) -> web.Response:
    """List all consolidation insights."""
    agent: MemoryAgent = request.app["agent"]
    data = agent.get_consolidations()
    return web.json_response(data)


async def handle_query(request: web.Request) -> web.Response:
    """Query memory with a question."""
    q = request.query.get("q", "").strip()
    if not q:
        return web.json_response({"error": "missing ?q= parameter"}, status=400)

    agent: MemoryAgent = request.app["agent"]
    answer = agent.query(q)
    return web.json_response({"question": q, "answer": answer})


async def handle_ingest(request: web.Request) -> web.Response:
    """Ingest new text."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    text = data.get("text", "").strip()
    if not text:
        return web.json_response({"error": "missing 'text' field"}, status=400)

    source = data.get("source", "api")
    agent: MemoryAgent = request.app["agent"]
    result = agent.ingest(text, source=source)
    return web.json_response({"status": "ingested", "response": result})


async def handle_consolidate(request: web.Request) -> web.Response:
    """Trigger manual consolidation."""
    agent: MemoryAgent = request.app["agent"]
    result = agent.consolidate()
    return web.json_response({"status": "done", "response": result})


async def handle_delete(request: web.Request) -> web.Response:
    """Delete a specific memory."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    memory_id = data.get("memory_id")
    if not memory_id:
        return web.json_response({"error": "missing 'memory_id' field"}, status=400)

    agent: MemoryAgent = request.app["agent"]
    result = agent.delete_memory(int(memory_id))
    return web.json_response(result)


async def handle_clear(request: web.Request) -> web.Response:
    """Clear all memories."""
    agent: MemoryAgent = request.app["agent"]
    result = agent.clear_all()
    return web.json_response(result)


async def handle_query_stream(request: web.Request) -> web.StreamResponse:
    """Stream query response via Server-Sent Events (SSE)."""
    q = request.query.get("q", "").strip()
    if not q:
        return web.json_response({"error": "missing ?q= parameter"}, status=400)

    agent: MemoryAgent = request.app["agent"]

    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    await response.prepare(request)

    # Run streaming in thread pool (boto3 is sync)
    def stream_generator():
        return list(agent.query_stream(q))

    chunks = await asyncio.get_event_loop().run_in_executor(None, stream_generator)

    for chunk in chunks:
        data = f"data: {chunk}\n\n"
        await response.write(data.encode("utf-8"))

    await response.write(b"data: [DONE]\n\n")
    await response.write_eof()
    return response
