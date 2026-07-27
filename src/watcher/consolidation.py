"""
Consolidation loop - periodically consolidates memories.
"""

import asyncio
import logging

from src.agents.memory_agent import MemoryAgent
from src.config import get_settings

log = logging.getLogger("memory-agent")


async def consolidation_loop(agent: MemoryAgent) -> None:
    """
    Run consolidation at configured intervals.

    Only triggers when there are enough unconsolidated memories.
    Like the brain consolidating during sleep.
    """
    settings = get_settings()
    interval = settings.consolidate_interval_minutes
    min_memories = settings.consolidate_min_memories

    log.info(f"🔄 Consolidation: every {interval} minutes (min {min_memories} memories)")

    while True:
        await asyncio.sleep(interval * 60)

        try:
            stats = agent.get_stats()
            unconsolidated = stats["unconsolidated"]

            if unconsolidated >= min_memories:
                log.info(f"🔄 Running consolidation ({unconsolidated} unconsolidated)...")
                result = agent.consolidate()
                log.info(f"🔄 {result[:100]}")
            else:
                log.info(f"🔄 Skipping consolidation ({unconsolidated} unconsolidated)")

        except Exception as e:
            log.error(f"Consolidation error: {e}")
