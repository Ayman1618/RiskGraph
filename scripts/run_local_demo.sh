#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "  RiskGraph — Real-Time Fraud & Identity Platform Demo    "
echo "=========================================================="
echo ""

echo "[1/4] Checking Platform Health..."
python3 cli.py status || true
echo ""

echo "[2/4] Generating Sample Synthetic Fraud Stream (20 events)..."
python3 cli.py generate-stream --rate 0 --count 20 --fraud-ratio 0.35
echo ""

echo "[3/4] Evaluating High-Risk Transaction (Emulator + Amount > $5k)..."
python3 cli.py evaluate-tx --user-id usr_ring_0_m2 --amount 8250.00 --emulator
echo ""

echo "[4/4] Running Automated Data Quality Validation Suite..."
python3 cli.py run-dq-suite --sample-size 100
echo ""

echo "=========================================================="
echo "  RiskGraph Demo Finished Successfully!                  "
echo "=========================================================="
