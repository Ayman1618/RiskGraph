from typing import Any, Dict, List, Optional

import pandas as pd

from src.common.config import settings
from src.common.logger import get_logger
from src.graph.graph_client import Neo4jClient

logger = get_logger("graph_loader")


class Neo4jGraphLoader:
    """
    High-throughput bulk graph loader using Cypher UNWIND batches.
    """

    def __init__(self, client: Optional[Neo4jClient] = None):
        self.client = client or Neo4jClient()

    def sync_nodes_batch(self, nodes: List[Dict[str, Any]], batch_size: int = 1000):
        """
        Upserts nodes into Neo4j in parameterized UNWIND batches.
        Each node dict: {'id': '...', 'type': 'User|Device|IP|Card|Merchant', ...}
        """
        driver = self.client.get_driver()

        # Group by node label
        by_type: Dict[str, List[Dict[str, Any]]] = {}
        for n in nodes:
            ntype = n.get("type", "User")
            by_type.setdefault(ntype, []).append(n)

        with driver.session() as session:
            for ntype, items in by_type.items():
                for i in range(0, len(items), batch_size):
                    chunk = items[i : i + batch_size]
                    query = f"""
                    UNWIND $batch AS row
                    MERGE (n:{ntype} {{id: row.id}})
                    SET n += row
                    """
                    session.run(query, batch=chunk)
                    logger.debug(f"Merged {len(chunk)} {ntype} nodes into Neo4j.")

        logger.info(f"Synchronized {len(nodes)} total nodes to Neo4j.")

    def sync_edges_batch(self, edges: List[Dict[str, Any]], batch_size: int = 1000):
        """
        Upserts relationships into Neo4j in parameterized UNWIND batches.
        Each edge dict: {'source': 'user_id', 'target': 'device_id', 'relationship': 'USES_DEVICE', ...}
        """
        driver = self.client.get_driver()

        # Group by relationship type
        by_rel: Dict[str, List[Dict[str, Any]]] = {}
        for e in edges:
            rel = e.get("relationship", "CONNECTED_TO")
            by_rel.setdefault(rel, []).append(e)

        with driver.session() as session:
            for rel, items in by_rel.items():
                for i in range(0, len(items), batch_size):
                    chunk = items[i : i + batch_size]
                    query = f"""
                    UNWIND $batch AS row
                    MATCH (s {{id: row.source}})
                    MATCH (t {{id: row.target}})
                    MERGE (s)-[r:{rel}]->(t)
                    SET r.last_seen = coalesce(row.timestamp, datetime())
                    """
                    session.run(query, batch=chunk)
                    logger.debug(f"Merged {len(chunk)} {rel} relationships into Neo4j.")

        logger.info(f"Synchronized {len(edges)} total edges to Neo4j.")

    def load_from_parquet_marts(self, nodes_parquet_path: str, edges_parquet_path: str):
        """
        Reads Gold nodes and edges from Parquet and ingests into Neo4j.
        """
        logger.info(f"Reading Gold graph nodes from {nodes_parquet_path}...")
        nodes_df = pd.read_parquet(nodes_parquet_path)
        nodes_list = nodes_df.to_dict(orient="records")
        self.sync_nodes_batch(nodes_list)

        logger.info(f"Reading Gold graph edges from {edges_parquet_path}...")
        edges_df = pd.read_parquet(edges_parquet_path)
        edges_list = edges_df.to_dict(orient="records")
        self.sync_edges_batch(edges_list)

        logger.info("Gold graph sync to Neo4j completed.")
