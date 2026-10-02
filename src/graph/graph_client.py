from typing import Any, Dict, List, Optional

from neo4j import Driver, GraphDatabase

from src.common.config import settings
from src.common.logger import get_logger

logger = get_logger("graph_client")


class Neo4jClient:
    """
    Manages connection pool and schema constraints for Neo4j Identity Graph.
    """

    def __init__(
        self, uri: Optional[str] = None, user: Optional[str] = None, password: Optional[str] = None
    ):
        self.uri = uri or settings.NEO4J_URI
        self.user = user or settings.NEO4J_USER
        self.password = password or settings.NEO4J_PASSWORD
        self._driver: Optional[Driver] = None

    def get_driver(self) -> Driver:
        if self._driver is None:
            logger.info(f"Connecting to Neo4j at {self.uri}...")
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                max_connection_lifetime=3600,
                max_connection_pool_size=50,
            )
        return self._driver

    def close(self):
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j driver connection closed.")

    def init_schema(self):
        """
        Creates uniqueness constraints and indexes for high-speed graph traversals.
        """
        driver = self.get_driver()
        constraints = [
            "CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE",
            "CREATE CONSTRAINT device_id_unique IF NOT EXISTS FOR (d:Device) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT ip_unique IF NOT EXISTS FOR (i:IP) REQUIRE i.id IS UNIQUE",
            "CREATE CONSTRAINT card_unique IF NOT EXISTS FOR (c:Card) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT merchant_unique IF NOT EXISTS FOR (m:Merchant) REQUIRE m.id IS UNIQUE",
            "CREATE INDEX user_fraud_status_idx IF NOT EXISTS FOR (u:User) ON (u.is_fraudulent)",
            "CREATE INDEX device_fingerprint_idx IF NOT EXISTS FOR (d:Device) ON (d.fingerprint)",
        ]

        with driver.session() as session:
            for query in constraints:
                try:
                    session.run(query)
                    logger.info(f"Executed Neo4j schema constraint: {query.split()[2]}")
                except Exception as e:
                    logger.warning(f"Neo4j constraint initialization warning: {e}")

    def execute_query(
        self, query: str, parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes a Cypher query and returns records as list of dictionaries.
        """
        driver = self.get_driver()
        with driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]
