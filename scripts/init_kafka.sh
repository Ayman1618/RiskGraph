#!/usr/bin/env bash
set -e

KAFKA_BROKER=${KAFKA_BOOTSTRAP_SERVERS:-"localhost:9092"}

echo "Waiting for Kafka broker at $KAFKA_BROKER to become ready..."
until kafka-topics --bootstrap-server "$KAFKA_BROKER" --list > /dev/null 2>&1; do
    echo "Waiting for Kafka..."
    sleep 2
done

echo "Creating Kafka topics for RiskGraph..."
topics=(
    "fraud.transactions.raw:4:1"
    "fraud.identity.raw:4:1"
    "fraud.alerts:2:1"
    "fraud.dlq:1:1"
)

for t in "${topics[@]}"; do
    IFS=":" read -r name parts repl <<< "$t"
    kafka-topics --bootstrap-server "$KAFKA_BROKER" \
        --create --if-not-exists \
        --topic "$name" \
        --partitions "$parts" \
        --replication-factor "$repl" || true
    echo "Created or verified topic: $name"
done

echo "All Kafka topics successfully initialized."
