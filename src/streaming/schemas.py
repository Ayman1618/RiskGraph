from pyspark.sql.types import (
    BooleanType,
    DoubleType,
    MapType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

# PySpark Schema for nested Device Signal
DEVICE_SIGNAL_SPARK_SCHEMA = StructType([
    StructField("device_id", StringType(), True),
    StructField("device_fingerprint", StringType(), True),
    StructField("os", StringType(), True),
    StructField("browser", StringType(), True),
    StructField("is_emulator", BooleanType(), True),
    StructField("is_rooted", BooleanType(), True),
    StructField("screen_resolution", StringType(), True),
    StructField("user_agent", StringType(), True),
])

# PySpark Schema for Raw Transaction JSON payload
TRANSACTION_RAW_SPARK_SCHEMA = StructType([
    StructField("transaction_id", StringType(), False),
    StructField("user_id", StringType(), False),
    StructField("amount", DoubleType(), False),
    StructField("currency", StringType(), True),
    StructField("transaction_type", StringType(), True),
    StructField("payment_method", StringType(), True),
    StructField("card_token", StringType(), True),
    StructField("bank_account", StringType(), True),
    StructField("merchant_id", StringType(), True),
    StructField("device_id", StringType(), True),
    StructField("ip_address", StringType(), False),
    StructField("location_country", StringType(), True),
    StructField("location_city", StringType(), True),
    StructField("device_signals", DEVICE_SIGNAL_SPARK_SCHEMA, True),
    StructField("timestamp", TimestampType(), False),
    StructField("status", StringType(), True),
    StructField("metadata", MapType(StringType(), StringType()), True),
])

# PySpark Schema for Raw Identity Registration/Event payload
IDENTITY_RAW_SPARK_SCHEMA = StructType([
    StructField("user_id", StringType(), False),
    StructField("email", StringType(), False),
    StructField("phone", StringType(), True),
    StructField("full_name", StringType(), True),
    StructField("national_id", StringType(), True),
    StructField("kyc_status", StringType(), True),
    StructField("risk_tier", StringType(), True),
    StructField("device", DEVICE_SIGNAL_SPARK_SCHEMA, True),
    StructField("ip_address", StringType(), False),
    StructField("timestamp", TimestampType(), False),
])
