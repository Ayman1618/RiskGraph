"""
Airflow DAG: Lakehouse Storage Compaction & Retention
Optimizes small Parquet files produced by streaming micro-batches.
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "riskgraph-data-eng",
    "depends_on_past": False,
    "start_date": datetime(2026, 1, 1),
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

dag = DAG(
    dag_id="lakehouse_compaction_maintenance",
    default_args=default_args,
    description="Compacts streaming micro-batch files into optimized Parquet partitions",
    schedule_interval="0 2 * * *",  # 2 AM daily
    catchup=False,
    tags=["riskgraph", "maintenance", "lakehouse"]
)


def compact_bronze_lakehouse_task(**context):
    from src.streaming.stream_processor import build_spark_session
    from src.common.config import settings

    spark = build_spark_session(app_name="Airflow-Lakehouse-Compaction")
    base = f"s3a://{settings.S3_BUCKET_NAME}" if settings.S3_ENDPOINT_URL else "/tmp/riskgraph/lakehouse"
    bronze_path = f"{base}/{settings.S3_BRONZE_PREFIX}/transactions"

    try:
        df = spark.read.parquet(bronze_path)
        # Re-partition into optimal chunk sizes
        (
            df.coalesce(4)
            .write
            .mode("overwrite")
            .partitionBy("year", "month", "day")
            .parquet(bronze_path)
        )
        print("Bronze lakehouse compaction completed.")
    except Exception as e:
        print(f"Bronze compaction note: {e}")
    finally:
        spark.stop()


with dag:
    t1_compact = PythonOperator(
        task_id="compact_bronze_streaming_files",
        python_callable=compact_bronze_lakehouse_task
    )
