"""
Airflow DAG: Identity Graph Sync & Graph Risk Intelligence
Orchestrates loading Gold graph entities into Neo4j and syncing fraud rings.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "riskgraph-data-eng",
    "depends_on_past": False,
    "start_date": datetime(2026, 1, 1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

dag = DAG(
    dag_id="identity_graph_sync_dag",
    default_args=default_args,
    description="Synchronizes Gold graph nodes/edges to Neo4j and refreshes fraud rings",
    schedule_interval="@hourly",
    catchup=False,
    max_active_runs=1,
    tags=["riskgraph", "neo4j", "identity-graph", "fraud-detection"],
)


def init_neo4j_constraints_task(**context):
    from src.graph.graph_client import Neo4jClient

    client = Neo4jClient()
    client.init_schema()
    client.close()


def load_gold_to_neo4j_task(**context):
    from src.common.config import settings
    from src.graph.graph_loader import Neo4jGraphLoader

    base = (
        f"s3a://{settings.S3_BUCKET_NAME}"
        if settings.S3_ENDPOINT_URL
        else "/tmp/riskgraph/lakehouse"
    )
    nodes_path = f"{base}/{settings.S3_GOLD_PREFIX}/graph_nodes"
    edges_path = f"{base}/{settings.S3_GOLD_PREFIX}/graph_edges"

    loader = Neo4jGraphLoader()
    # In local execution, loads parquet files into Neo4j
    try:
        loader.load_from_parquet_marts(nodes_path, edges_path)
    except Exception as e:
        print(f"Warning/Info: Parquet paths might need local path mapping: {e}")


def tag_fraud_rings_task(**context):
    from src.graph.graph_analytics import GraphFraudAnalytics

    analytics = GraphFraudAnalytics()
    rings = analytics.find_fraud_rings(min_ring_size=3)
    print(f"Discovered {len(rings)} active fraud rings in Neo4j Identity Graph.")


with dag:
    t1_schema = PythonOperator(
        task_id="init_neo4j_schema_constraints", python_callable=init_neo4j_constraints_task
    )

    t2_load = PythonOperator(
        task_id="sync_gold_graph_to_neo4j", python_callable=load_gold_to_neo4j_task
    )

    t3_rings = PythonOperator(
        task_id="detect_and_tag_fraud_rings", python_callable=tag_fraud_rings_task
    )

    t1_schema >> t2_load >> t3_rings
