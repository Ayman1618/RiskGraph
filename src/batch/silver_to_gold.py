import os
from typing import Dict, Tuple

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import (
    avg,
    col,
    count,
    countDistinct,
    current_timestamp,
    lit,
    max as spark_max,
    min as spark_min,
    sum as spark_sum,
    when
)

from src.common.config import settings
from src.common.logger import get_logger

logger = get_logger("silver_to_gold")


class SilverToGoldPipeline:
    """
    Transforms curated Silver transactions into Gold Feature Marts and
    Identity Graph Nodes and Edges for Neo4j synchronization.
    """

    def __init__(self, spark: SparkSession):
        self.spark = spark

    def run(self, silver_input_path: str, gold_base_path: str) -> Dict[str, str]:
        logger.info(f"Starting Silver -> Gold transformation from {silver_input_path} into {gold_base_path}")

        silver_df = self.spark.read.parquet(silver_input_path)

        # 1. Gold Feature Mart: User Daily Aggregates
        user_features_df = (
            silver_df.groupBy("user_id", "tx_date")
            .agg(
                count("transaction_id").alias("daily_tx_count"),
                spark_sum("amount").alias("daily_total_amount"),
                avg("amount").alias("daily_avg_amount"),
                spark_max("amount").alias("daily_max_amount"),
                countDistinct("device_id").alias("distinct_devices_count"),
                countDistinct("ip_address").alias("distinct_ips_count"),
                countDistinct("card_token").alias("distinct_cards_count"),
                countDistinct("merchant_id").alias("distinct_merchants_count"),
                spark_sum(when(col("is_high_value"), 1).otherwise(0)).alias("high_value_tx_count")
            )
            .withColumn("gold_generated_at", current_timestamp())
        )

        user_features_path = f"{gold_base_path}/features_user_daily"
        user_features_df.write.mode("overwrite").partitionBy("tx_date").parquet(user_features_path)
        logger.info(f"Wrote user daily features to {user_features_path}")

        # 2. Gold Feature Mart: Device Risk & Multi-User Sharing
        device_risk_df = (
            silver_df.filter(col("device_id") != "UNKNOWN_DEVICE")
            .groupBy("device_id")
            .agg(
                countDistinct("user_id").alias("shared_users_count"),
                count("transaction_id").alias("total_tx_count"),
                spark_sum("amount").alias("total_volume"),
                spark_max("timestamp").alias("last_seen_timestamp")
            )
            .withColumn("is_shared_device_ring", when(col("shared_users_count") >= 3, lit(True)).otherwise(lit(False)))
            .withColumn("gold_generated_at", current_timestamp())
        )

        device_risk_path = f"{gold_base_path}/features_device_risk"
        device_risk_df.write.mode("overwrite").parquet(device_risk_path)
        logger.info(f"Wrote device risk features to {device_risk_path}")

        # 3. Gold Graph Extract: Nodes
        user_nodes = silver_df.select("user_id").distinct().withColumnRenamed("user_id", "id").withColumn("type", lit("User"))
        device_nodes = silver_df.filter(col("device_id") != "UNKNOWN_DEVICE").select("device_id").distinct().withColumnRenamed("device_id", "id").withColumn("type", lit("Device"))
        ip_nodes = silver_df.select("ip_address").distinct().withColumnRenamed("ip_address", "id").withColumn("type", lit("IP"))
        card_nodes = silver_df.filter(col("card_token") != "UNKNOWN_CARD").select("card_token").distinct().withColumnRenamed("card_token", "id").withColumn("type", lit("Card"))
        merchant_nodes = silver_df.filter(col("merchant_id") != "DIRECT_TRANSFER").select("merchant_id").distinct().withColumnRenamed("merchant_id", "id").withColumn("type", lit("Merchant"))

        all_nodes_df = user_nodes.union(device_nodes).union(ip_nodes).union(card_nodes).union(merchant_nodes)
        nodes_path = f"{gold_base_path}/graph_nodes"
        all_nodes_df.write.mode("overwrite").parquet(nodes_path)

        # 4. Gold Graph Extract: Edges (User -> Device, User -> IP, User -> Card, User -> Merchant)
        edges_user_device = (
            silver_df.filter(col("device_id") != "UNKNOWN_DEVICE")
            .select(
                col("user_id").alias("source"),
                col("device_id").alias("target"),
                lit("USES_DEVICE").alias("relationship"),
                col("timestamp")
            )
            .distinct()
        )

        edges_user_ip = (
            silver_df.select(
                col("user_id").alias("source"),
                col("ip_address").alias("target"),
                lit("ORIGINATED_FROM_IP").alias("relationship"),
                col("timestamp")
            )
            .distinct()
        )

        edges_user_card = (
            silver_df.filter(col("card_token") != "UNKNOWN_CARD")
            .select(
                col("user_id").alias("source"),
                col("card_token").alias("target"),
                lit("PAID_WITH").alias("relationship"),
                col("timestamp")
            )
            .distinct()
        )

        edges_user_merchant = (
            silver_df.filter(col("merchant_id") != "DIRECT_TRANSFER")
            .select(
                col("user_id").alias("source"),
                col("merchant_id").alias("target"),
                lit("TRANSACTED_WITH").alias("relationship"),
                col("timestamp")
            )
            .distinct()
        )

        all_edges_df = edges_user_device.union(edges_user_ip).union(edges_user_card).union(edges_user_merchant)
        edges_path = f"{gold_base_path}/graph_edges"
        all_edges_df.write.mode("overwrite").parquet(edges_path)
        logger.info(f"Wrote graph nodes ({nodes_path}) and edges ({edges_path})")

        return {
            "user_features": user_features_path,
            "device_risk": device_risk_path,
            "graph_nodes": nodes_path,
            "graph_edges": edges_path
        }
