"""
Always-On Memory Agent - Main Entry Point

Wires together all modules and starts the agent:
- Initializes database
- Creates the memory agent
- Starts background tasks (file watcher, consolidation)
- Starts the HTTP API server

Usage:
    python -m src.main
    python -m src.main --port 9000 --watch ./docs
"""

import argparse
import asyncio
import logging
import signal
import sys

from aiohttp import web

from src.config import get_settings
from src.db import init_database
from src.agents import MemoryAgent
from src.api import create_app
from src.watcher import watch_folder, consolidation_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="[%H:%M]",
)
log = logging.getLogger("memory-agent")


async def run(args: argparse.Namespace) -> None:
    """Main async entry point."""
    settings = get_settings()

    # Initialize database schema
    init_database()

    # Create the agent
    agent = MemoryAgent()

    # Log startup info
    log.info("🧠 Always-On Memory Agent (Bedrock) starting")
    log.info(f"   Model:        {settings.bedrock_model_id}")
    log.info(f"   Region:       {settings.aws_region}")
    log.info(f"   Database:     {settings.db_path}")
    log.info(f"   Watch:        {settings.watch_dir}")
    log.info(f"   Consolidate:  every {settings.consolidate_interval_minutes}m")
    log.info(f"   API:          http://{settings.host}:{settings.port}")
    log.info("")

    # Start background tasks
    tasks = [
        asyncio.create_task(watch_folder(agent)),
        asyncio.create_task(consolidation_loop(agent)),
    ]

    # Start HTTP server
    app = create_app(agent)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.host, settings.port)
    await site.start()

    log.info(f"✅ Agent running.")
    log.info(f"   Drop files in {settings.watch_dir}/ or POST to http://localhost:{settings.port}/ingest")
    log.info("")

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        await runner.cleanup()


def main() -> None:
    """Parse CLI args (override env vars) and start the event loop."""
    parser = argparse.ArgumentParser(
        description="Always-On Memory Agent - AWS Bedrock",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--port", type=int, help="HTTP API port")
    parser.add_argument("--watch", type=str, help="Folder to watch for files")
    parser.add_argument("--consolidate-every", type=int, help="Consolidation interval (minutes)")
    parser.add_argument("--model", type=str, help="Bedrock model ID")
    parser.add_argument("--region", type=str, help="AWS region")

    args = parser.parse_args()

    # CLI args override environment variables
    import os
    if args.port:
        os.environ["PORT"] = str(args.port)
    if args.watch:
        os.environ["WATCH_DIR"] = args.watch
    if args.consolidate_every:
        os.environ["CONSOLIDATE_INTERVAL"] = str(args.consolidate_every)
    if args.model:
        os.environ["BEDROCK_MODEL_ID"] = args.model
    if args.region:
        os.environ["AWS_REGION"] = args.region

    # Clear cached settings so they pick up CLI overrides
    from src.config.settings import get_settings as _get_settings
    _get_settings.cache_clear()

    # Run
    loop = asyncio.new_event_loop()

    def shutdown(sig):
        log.info(f"\n👋 Shutting down (signal {sig})...")
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown, sig)

    try:
        loop.run_until_complete(run(args))
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        loop.close()
        log.info("🧠 Agent stopped.")


if __name__ == "__main__":
    main()
