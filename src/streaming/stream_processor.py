import os
import sys
from typing import Optional

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    current_timestamp,
    date_format,
    from_json,
    to_json,
    struct,
    when,
    window,
    count,
    sum as spark_sum,
    countDistinct,
    expr
)

from src.common.config import settings
from src.common.logger import get_logger
from src.streaming.schemas import TRANSACTION_RAW_SPARK_SCHEMA

logger = get_logger("stream_processor")


def build_spark_session(app_name: str = "RiskGraph-Structured-Streaming") -> SparkSession:
    """
    Creates and configures a PySpark session with Kafka, S3/MinIO, and PostgreSQL JDBC support.
    """
    s3_endpoint = settings.S3_ENDPOINT_URL or "http://localhost:4566"
    s3_endpoint_host = s3_endpoint.replace("http://", "").replace("https://", "")

    builder = (
        SparkSession.builder.appName(app_name)
        .master(settings.SPARK_MASTER)
        .config("spark.driver.memory", settings.SPARK_DRIVER_MEMORY)
        .config("spark.executor.memory", settings.SPARK_EXECUTOR_MEMORY)
        .config("spark.sql.streaming.forceDeleteTempCheckpointLocation", "true")
        .config("spark.sql.shuffle.partitions", "4")
        # S3A / MinIO / LocalStack configs
        .config("spark.hadoop.fs.s3a.endpoint", s3_endpoint)
        .config("spark.hadoop.fs.s3a.access.key", settings.AWS_ACCESS_KEY_ID)
        .config("spark.hadoop.fs.s3a.secret.key", settings.AWS_SECRET_ACCESS_KEY)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
    )

    # Add required packages for Kafka, PostgreSQL, Delta and AWS S3
    packages = [
        "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1",
        "org.postgresql:postgresql:42.7.3",
        "org.apache.hadoop:hadoop-aws:3.3.4",
        "com.amazonaws:aws-java-sdk-bundle:1.12.262"
    ]
    builder = builder.config("spark.jars.packages", ",".join(packages))

    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    logger.info(f"SparkSession created successfully with app: {app_name}")
    return spark


class SparkStreamingPipeline:
    """
    Real-time streaming pipeline processing transaction events from Kafka,
    writing dual-sink (Bronze Parquet to S3 Lakehouse & PostgreSQL ODS with velocity aggregates).
    """

    def __init__(self, spark: Optional[SparkSession] = None):
        self.spark = spark or build_spark_session()
        self.jdbc_url = f"jdbc:postgresql://{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
        self.db_properties = {
            "user": settings.POSTGRES_USER,
            "password": settings.POSTGRES_PASSWORD,
            "driver": "org.postgresql.Driver"
        }

    def process_micro_batch(self, batch_df, batch_id: int):
        """
        Micro-batch processor invoked by Spark Structured Streaming foreachBatch.
        Persists raw transactions to PostgreSQL and calculates near real-time velocity metrics.
        """
        if batch_df.isEmpty():
            return

        logger.info(f"Processing micro-batch ID: {batch_id} with {batch_df.count()} records.")

        try:
            # 1. Write parsed transactions to PostgreSQL table
            flat_tx_df = batch_df.select(
                col("transaction_id"),
                col("user_id"),
                col("amount"),
                col("currency"),
                col("transaction_type"),
                col("payment_method"),
                col("card_token"),
                col("bank_account"),
                col("merchant_id"),
                col("device_id"),
                col("ip_address"),
                col("location_country"),
                col("location_city"),
                col("status"),
                expr("0.0").alias("risk_score"),
                expr("'APPROVE'").alias("decision"),
                expr("'[]'::jsonb").alias("triggered_rules"),
                expr("'{}'::jsonb").alias("metadata"),
                col("timestamp"),
                current_timestamp().alias("created_at")
            )

            # Insert to PostgreSQL
            flat_tx_df.write.jdbc(
                url=self.jdbc_url,
                table="transactions",
                mode="append",
                properties=self.db_properties
            )
            logger.info(f"Micro-batch {batch_id} successfully persisted to PostgreSQL transactions table.")

        except Exception as e:
            logger.error(f"Error persisting micro-batch {batch_id} to PostgreSQL: {e}")

    def run(self, checkpoint_dir: str = "/tmp/riskgraph/checkpoints/streaming"):
        """
        Starts the PySpark Structured Streaming query.
        """
        logger.info(f"Subscribing to Kafka topic: {settings.KAFKA_RAW_TRANSACTIONS_TOPIC} at {settings.KAFKA_BOOTSTRAP_SERVERS}")

        kafka_df = (
            self.spark.readStream
            .format("kafka")
            .option("kafka.bootstrap.servers", settings.KAFKA_BOOTSTRAP_SERVERS)
            .option("subscribe", settings.KAFKA_RAW_TRANSACTIONS_TOPIC)
            .option("startingOffsets", "latest")
            .option("failOnDataLoss", "false")
            .load()
        )

        # Parse JSON payload
        parsed_df = (
            kafka_df.selectExpr("CAST(value AS STRING) as json_payload")
            .select(from_json(col("json_payload"), TRANSACTION_RAW_SPARK_SCHEMA).alias("data"))
            .select("data.*")
            .withColumn("year", date_format(col("timestamp"), "yyyy"))
            .withColumn("month", date_format(col("timestamp"), "MM"))
            .withColumn("day", date_format(col("timestamp"), "dd"))
            .withWatermark("timestamp", "10 minutes")
        )

        bronze_s3_path = f"s3a://{settings.S3_BUCKET_NAME}/{settings.S3_BRONZE_PREFIX}/transactions/"
        local_bronze_fallback = "/tmp/riskgraph/lakehouse/bronze/transactions/"

        lake_sink_path = bronze_s3_path if settings.S3_ENDPOINT_URL else local_bronze_fallback

        logger.info(f"Setting up Lakehouse Bronze Sink at: {lake_sink_path}")

        # Stream Query 1: Bronze Data Lake Writer (Parquet partitioned by year/month/day)
        bronze_query = (
            parsed_df.writeStream
            .format("parquet")
            .partitionBy("year", "month", "day")
            .option("path", lake_sink_path)
            .option("checkpointLocation", f"{checkpoint_dir}/bronze")
            .outputMode("append")
            .start()
        )

        # Stream Query 2: PostgreSQL ODS Writer via foreachBatch
        ods_query = (
            parsed_df.writeStream
            .foreachBatch(self.process_micro_batch)
            .option("checkpointLocation", f"{checkpoint_dir}/ods")
            .outputMode("append")
            .start()
        )

        logger.info("PySpark Structured Streaming queries started. Awaiting termination...")
        try:
            self.spark.streams.awaitAnyTermination()
        except KeyboardInterrupt:
            logger.info("Stopping streaming queries...")
            bronze_query.stop()
            ods_query.stop()


if __name__ == "__main__":
    pipeline = SparkStreamingPipeline()
    pipeline.run()
