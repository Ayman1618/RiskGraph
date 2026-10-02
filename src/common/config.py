import os
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    ENVIRONMENT: str = "local"
    LOG_LEVEL: str = "INFO"
    APP_PORT: int = 8000
    METRICS_PORT: int = 9090

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_RAW_TRANSACTIONS_TOPIC: str = "fraud.transactions.raw"
    KAFKA_RAW_IDENTITY_TOPIC: str = "fraud.identity.raw"
    KAFKA_ALERTS_TOPIC: str = "fraud.alerts"
    KAFKA_DLQ_TOPIC: str = "fraud.dlq"
    KAFKA_CONSUMER_GROUP: str = "riskgraph-streaming-group"

    # PostgreSQL
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "riskgraph"
    POSTGRES_USER: str = "riskgraph_user"
    POSTGRES_PASSWORD: str = "riskgraph_secure_pass"
    DATABASE_URL: Optional[str] = None

    @property
    def sync_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Neo4j
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "riskgraph_graph_pass"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None

    # AWS / LocalStack S3
    AWS_ACCESS_KEY_ID: str = "test"
    AWS_SECRET_ACCESS_KEY: str = "test"
    AWS_REGION: str = "us-east-1"
    S3_ENDPOINT_URL: Optional[str] = "http://localhost:4566"
    S3_BUCKET_NAME: str = "riskgraph-lake"
    S3_BRONZE_PREFIX: str = "bronze"
    S3_SILVER_PREFIX: str = "silver"
    S3_GOLD_PREFIX: str = "gold"
    S3_REPORTS_PREFIX: str = "reports"

    # Spark
    SPARK_MASTER: str = "local[*]"
    SPARK_DRIVER_MEMORY: str = "2g"
    SPARK_EXECUTOR_MEMORY: str = "2g"


settings = Settings()
