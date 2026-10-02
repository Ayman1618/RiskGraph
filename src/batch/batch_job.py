import os
import sys
from datetime import datetime, timezone
from typing import Optional

from src.batch.bronze_to_silver import BronzeToSilverPipeline
from src.batch.silver_to_gold import SilverToGoldPipeline
from src.common.config import settings
from src.common.logger import get_logger
from src.streaming.stream_processor import build_spark_session

logger = get_logger("batch_job")


def run_daily_batch_pipeline(
    execution_date: Optional[str] = None,
    bronze_path: Optional[str] = None,
    silver_path: Optional[str] = None,
    gold_path: Optional[str] = None,
):
    """
    Executes the complete Bronze -> Silver -> Gold Batch Lakehouse pipeline.
    """
    date_str = execution_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logger.info(f"Starting RiskGraph Lakehouse Batch Pipeline for Date: {date_str}")

    spark = build_spark_session(app_name="RiskGraph-Daily-Batch-ETL")

    # Resolve S3 / Local lakehouse paths
    base_s3 = (
        f"s3a://{settings.S3_BUCKET_NAME}"
        if settings.S3_ENDPOINT_URL
        else "/tmp/riskgraph/lakehouse"
    )
    b_path = bronze_path or f"{base_s3}/{settings.S3_BRONZE_PREFIX}/transactions"
    s_path = silver_path or f"{base_s3}/{settings.S3_SILVER_PREFIX}/transactions"
    g_path = gold_path or f"{base_s3}/{settings.S3_GOLD_PREFIX}"

    try:
        # 1. Bronze -> Silver Cleansing & Enrichment
        logger.info("Executing Bronze -> Silver stage...")
        b2s = BronzeToSilverPipeline(spark)
        b2s.run(input_path=b_path, output_path=s_path)

        # 2. Silver -> Gold Feature Marts & Graph Extraction
        logger.info("Executing Silver -> Gold stage...")
        s2g = SilverToGoldPipeline(spark)
        outputs = s2g.run(silver_input_path=s_path, gold_base_path=g_path)

        logger.info(
            f"Batch Lakehouse ETL completed successfully for {date_str}. Generated artifacts: {outputs}"
        )
        return outputs

    except Exception as e:
        logger.error(f"Batch pipeline execution failed: {e}", exc_info=True)
        raise e
    finally:
        spark.stop()


if __name__ == "__main__":
    run_daily_batch_pipeline()
