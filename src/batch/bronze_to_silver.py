import os
from typing import Optional

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import (
    col,
    current_timestamp,
    date_format,
    lower,
    row_number,
    sha2,
    trim,
    when,
    coalesce,
    lit
)
from pyspark.sql.window import Window

from src.common.config import settings
from src.common.logger import get_logger

logger = get_logger("bronze_to_silver")


class BronzeToSilverPipeline:
    """
    Cleanses, deduplicates, validates, and enriches raw Bronze Lakehouse data
    to produce curated Silver datasets.
    """

    def __init__(self, spark: SparkSession):
        self.spark = spark

    def run(self, input_path: str, output_path: str) -> DataFrame:
        logger.info(f"Starting Bronze -> Silver transformation from {input_path} to {output_path}")

        # 1. Read Bronze raw Parquet dataset
        raw_df = self.spark.read.parquet(input_path)
        initial_count = raw_df.count()
        logger.info(f"Read {initial_count} records from Bronze layer.")

        # 2. Cleansing and Standardization
        cleansed_df = (
            raw_df
            .filter(col("transaction_id").isNotNull() & col("user_id").isNotNull())
            .filter(col("amount") > 0)
            .withColumn("amount", col("amount").cast("double"))
            .withColumn("currency", coalesce(upper(trim(col("currency"))), lit("USD")))
            .withColumn("user_id", trim(col("user_id")))
            .withColumn("ip_address", trim(col("ip_address")))
            .withColumn("device_id", coalesce(trim(col("device_id")), lit("UNKNOWN_DEVICE")))
            .withColumn("card_token", coalesce(trim(col("card_token")), lit("UNKNOWN_CARD")))
            .withColumn("merchant_id", coalesce(trim(col("merchant_id")), lit("DIRECT_TRANSFER")))
        )

        # 3. Deduplication (Keep latest transaction per transaction_id)
        window_spec = Window.partitionBy("transaction_id").orderBy(col("timestamp").desc())
        deduped_df = (
            cleansed_df
            .withColumn("row_num", row_number().over(window_spec))
            .filter(col("row_num") == 1)
            .drop("row_num")
        )

        # 4. Enrichment & Feature flags
        silver_df = (
            deduped_df
            .withColumn("ip_network_prefix", expr("substring_index(ip_address, '.', 3)"))
            .withColumn("is_high_value", when(col("amount") >= 5000.0, lit(True)).otherwise(lit(False)))
            .withColumn("tx_date", date_format(col("timestamp"), "yyyy-MM-dd"))
            .withColumn("silver_processed_at", current_timestamp())
        )

        final_count = silver_df.count()
        logger.info(f"Writing {final_count} deduplicated and enriched records to Silver layer at {output_path}...")

        (
            silver_df.write
            .mode("overwrite")
            .partitionBy("tx_date")
            .parquet(output_path)
        )

        logger.info("Bronze to Silver ETL completed successfully.")
        return silver_df


# Helper for upper if needed
from pyspark.sql.functions import upper, expr
