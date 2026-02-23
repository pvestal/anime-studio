#!/usr/bin/env python3
"""Seed the Apache AGE graph from existing relational data.

Usage:
    cd /opt/anime-studio
    python -m scripts.seed_graph

Or:
    python scripts/seed_graph.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from packages.core.graph_sync import full_sync, graph_stats


async def main():
    print("Seeding anime_graph from relational data...")
    results = await full_sync()
    print(f"\nSync results:")
    for entity, count in results.items():
        print(f"  {entity}: {count}")

    print("\nGraph statistics:")
    stats = await graph_stats()
    print(f"  Total vertices: {stats['total_vertices']}")
    for label, count in stats["vertices"].items():
        if count > 0:
            print(f"    {label}: {count}")
    print(f"  Total edges: {stats['total_edges']}")
    for label, count in stats["edges"].items():
        if count > 0:
            print(f"    {label}: {count}")

    print("\nSeed complete.")


if __name__ == "__main__":
    asyncio.run(main())
