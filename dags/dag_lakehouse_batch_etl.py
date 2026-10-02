"""
Airflow DAG: Daily Lakehouse Batch ETL (Bronze -> Silver -> Gold)
Orchestrates PySpark batch transformations and Data Quality gates.
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
    "retry_delay": timedelta(minutes=3),
}

dag = DAG(
    dag_id="daily_lakehouse_batch_etl",
    default_args=default_args,
    description="Daily Lakehouse ETL: Bronze cleansing to Silver and Gold feature marts",
    schedule_interval="@daily",
    catchup=False,
    max_active_runs=1,
    tags=["riskgraph", "spark", "lakehouse", "batch", "etl"]
)


def run_bronze_to_silver_task(**context):
    from src.batch.bronze_to_silver import BronzeToSilverPipeline
    from src.streaming.stream_processor import build_spark_session
    from src.common.config import settings

    spark = build_spark_session(app_name="Airflow-Bronze-To-Silver")
    b2s = BronzeToSilverPipeline(spark)

    base = f"s3a://{settings.S3_BUCKET_NAME}" if settings.S3_ENDPOINT_URL else "/tmp/riskgraph/lakehouse"
    input_path = f"{base}/{settings.S3_BRONZE_PREFIX}/transactions"
    output_path = f"{base}/{settings.S3_SILVER_PREFIX}/transactions"

    b2s.run(input_path=input_path, output_path=output_path)
    spark.stop()


def run_silver_data_quality_task(**context):
    import pandas as pd
    from src.data_quality.dq_runner import DataQualityRunner
    from src.common.config import settings

    base = f"s3a://{settings.S3_BUCKET_NAME}" if settings.S3_ENDPOINT_URL else "/tmp/riskgraph/lakehouse"
    silver_path = f"{base}/{settings.S3_SILVER_PREFIX}/transactions"

    # In production, read silver parquet via pyarrow/boto3
    df = pd.read_parquet(silver_path) if not silver_path.startswith("s3a://") else pd.DataFrame()
    if not df.empty:
        runner = DataQualityRunner()
        report = runner.run_suite(df, dataset_name="silver_transactions")
        runner.save_report_to_s3(report)
        if not report.is_dataset_healthy:
            raise ValueError(f"Data Quality checks failed for Silver dataset. Pass rate: {report.overall_pass_rate}%")


def run_silver_to_gold_task(**context):
    from src.batch.silver_to_gold import SilverToGoldPipeline
    from src.streaming.stream_processor import build_spark_session
    from src.common.config import settings

    spark = build_spark_session(app_name="Airflow-Silver-To-Gold")
    s2g = SilverToGoldPipeline(spark)

    base = f"s3a://{settings.S3_BUCKET_NAME}" if settings.S3_ENDPOINT_URL else "/tmp/riskgraph/lakehouse"
    silver_path = f"{base}/{settings.S3_SILVER_PREFIX}/transactions"
    gold_path = f"{base}/{settings.S3_GOLD_PREFIX}"

    outputs = s2g.run(silver_input_path=silver_path, gold_base_path=gold_path)
    spark.stop()
    return outputs


with dag:
    t1_bronze_to_silver = PythonOperator(
        task_id="bronze_to_silver_cleansing",
        python_callable=run_bronze_to_silver_task
    )

    t2_silver_dq = PythonOperator(
        task_id="silver_data_quality_gate",
        python_callable=run_silver_data_quality_task
    )

    t3_silver_to_gold = PythonOperator(
        task_id="silver_to_gold_feature_marts",
        python_callable=run_silver_to_gold_task
    )

    t1_bronze_to_silver >> t2_silver_dq >> t3_silver_to_gold
