from typing import Any, Dict, List, Optional
from src.common.config import settings
from src.common.logger import get_logger
from src.common.models import GraphFeatures
from src.graph.graph_client import Neo4jClient

logger = get_logger("graph_analytics")


class GraphFraudAnalytics:
    """
    Advanced Graph Analytics Engine for Fraud and Identity Networks.
    Extracts topological features, detects synthetic rings, and evaluates multi-hop fraud proximity.
    """

    def __init__(self, client: Optional[Neo4jClient] = None):
        self.client = client or Neo4jClient()

    def get_user_graph_features(self, user_id: str) -> GraphFeatures:
        """
        Calculates graph-derived fraud signals for a given user in real-time.
        """
        query = """
        MATCH (u:User {id: $user_id})
        
        // 1. Shared Devices Count (Number of OTHER users sharing the same device)
        OPTIONAL MATCH (u)-[:USES_DEVICE]->(d:Device)<-[:USES_DEVICE]-(other_dev_u:User)
        WHERE other_dev_u <> u
        WITH u, count(DISTINCT other_dev_u) AS shared_device_count

        // 2. Shared IP Count (Number of OTHER users sharing the same IP)
        OPTIONAL MATCH (u)-[:ORIGINATED_FROM_IP]->(i:IP)<-[:ORIGINATED_FROM_IP]-(other_ip_u:User)
        WHERE other_ip_u <> u
        WITH u, shared_device_count, count(DISTINCT other_ip_u) AS shared_ip_count

        // 3. Shared Card Count (Number of OTHER users sharing the same Card)
        OPTIONAL MATCH (u)-[:PAID_WITH]->(c:Card)<-[:PAID_WITH]-(other_card_u:User)
        WHERE other_card_u <> u
        WITH u, shared_device_count, shared_ip_count, count(DISTINCT other_card_u) AS shared_card_count

        // 4. Proximity to Known Fraudulent Node (Shortest path up to 3 hops)
        OPTIONAL MATCH p = shortestPath((u)-[*1..3]-(fraud:User {is_fraudulent: true}))
        WHERE fraud <> u
        WITH u, shared_device_count, shared_ip_count, shared_card_count,
             coalesce(length(p), 99) AS min_hop_to_fraud,
             collect(DISTINCT fraud.id) AS connected_fraud_node_ids

        RETURN 
            shared_device_count,
            shared_ip_count,
            shared_card_count,
            CASE WHEN min_hop_to_fraud < 99 THEN min_hop_to_fraud ELSE null END AS hop_distance_to_fraud,
            connected_fraud_node_ids
        """

        try:
            driver = self.client.get_driver()
            with driver.session() as session:
                result = session.run(query, user_id=user_id)
                record = result.single()

                if not record:
                    return GraphFeatures(user_id=user_id)

                shared_device = record.get("shared_device_count", 0) or 0
                shared_ip = record.get("shared_ip_count", 0) or 0
                shared_card = record.get("shared_card_count", 0) or 0
                hop_dist = record.get("hop_distance_to_fraud")
                fraud_nodes = record.get("connected_fraud_node_ids", []) or []

                is_ring = (shared_device >= 3) or (shared_card >= 2) or (shared_ip >= 5 and shared_device >= 1)

                return GraphFeatures(
                    user_id=user_id,
                    shared_device_count=shared_device,
                    shared_ip_count=shared_ip,
                    shared_card_count=shared_card,
                    hop_distance_to_fraud=hop_dist,
                    is_identity_ring_member=is_ring,
                    connected_fraud_node_ids=fraud_nodes
                )
        except Exception as e:
            logger.warning(f"Error extracting graph features for user {user_id}: {e}")
            # Fallback safe features
            return GraphFeatures(user_id=user_id)

    def find_fraud_rings(self, min_ring_size: int = 3) -> List[Dict[str, Any]]:
        """
        Discovers tightly connected clusters of users sharing devices, IPs, or cards (Identity Rings).
        """
        driver = self.client.get_driver()

        query = """
        MATCH (d:Device)<-[:USES_DEVICE]-(u:User)
        WITH d, collect(u.id) AS users, count(u) AS user_count
        WHERE user_count >= $min_ring_size
        RETURN 
            d.id AS shared_device_id,
            d.fingerprint AS fingerprint,
            users AS ring_members,
            user_count AS ring_size
        ORDER BY ring_size DESC
        LIMIT 50
        """

        with driver.session() as session:
            result = session.run(query, min_ring_size=min_ring_size)
            return [record.data() for record in result]

    def get_user_subgraph(self, user_id: str, depth: int = 2) -> Dict[str, Any]:
        """
        Extracts 2-hop neighborhood of a user for visual UI / investigation exploration.
        """
        driver = self.client.get_driver()

        query = """
        MATCH (u:User {id: $user_id})
        CALL apoc.path.subgraphAll(u, {maxLevel: $depth})
        YIELD nodes, relationships
        RETURN 
            [n IN nodes | {id: n.id, labels: labels(n), properties: properties(n)}] AS nodes,
            [r IN relationships | {source: startNode(r).id, target: endNode(r).id, type: type(r)}] AS edges
        """

        # Standard fallback if APOC is not installed
        fallback_query = """
        MATCH (u:User {id: $user_id})-[r1]-(n1)
        OPTIONAL MATCH (n1)-[r2]-(n2)
        RETURN 
            collect(DISTINCT {id: u.id, label: 'User'}) + 
            collect(DISTINCT {id: n1.id, label: labels(n1)[0]}) + 
            collect(DISTINCT {id: n2.id, label: labels(n2)[0]}) AS nodes,
            collect(DISTINCT {source: startNode(r1).id, target: endNode(r1).id, type: type(r1)}) +
            collect(DISTINCT {source: startNode(r2).id, target: endNode(r2).id, type: type(r2)}) AS edges
        """

        with driver.session() as session:
            try:
                res = session.run(fallback_query, user_id=user_id)
                rec = res.single()
                if rec:
                    return {
                        "user_id": user_id,
                        "nodes": [n for n in rec.get("nodes", []) if n and n.get("id")],
                        "edges": [e for e in rec.get("edges", []) if e and e.get("source")]
                    }
            except Exception as e:
                logger.error(f"Error fetching subgraph for user {user_id}: {e}")

        return {"user_id": user_id, "nodes": [{"id": user_id, "label": "User"}], "edges": []}
