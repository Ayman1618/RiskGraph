import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
from pydantic import BaseModel, Field

from src.common.config import settings
from src.common.logger import get_logger
from src.data_quality.dq_rules import DQCheck, build_standard_transaction_dq_suite

logger = get_logger("data_quality_runner")


class DQCheckResult(BaseModel):
    check_name: str
    check_type: str
    description: str
    passed: bool
    failed_count: int
    pass_rate: float


class DataQualityReport(BaseModel):
    dataset_name: str
    total_records: int
    total_checks: int
    passed_checks: int
    failed_checks: int
    overall_pass_rate: float
    is_dataset_healthy: bool
    results: List[DQCheckResult]
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DataQualityRunner:
    """
    Executes data quality suites across Data Lake and Database datasets.
    """

    def __init__(self, checks: Optional[List[DQCheck]] = None):
        self.checks = checks or build_standard_transaction_dq_suite()

    def run_suite(self, df: pd.DataFrame, dataset_name: str = "transactions") -> DataQualityReport:
        logger.info(
            f"Running {len(self.checks)} Data Quality checks on dataset '{dataset_name}' ({len(df)} rows)..."
        )

        results: List[DQCheckResult] = []
        passed_count = 0

        for check in self.checks:
            res = check.evaluate(df)
            passed = res.get("passed", False)
            if passed:
                passed_count += 1

            results.append(
                DQCheckResult(
                    check_name=check.check_name,
                    check_type=check.check_type,
                    description=check.description,
                    passed=passed,
                    failed_count=res.get("failed_count", 0),
                    pass_rate=res.get("pass_rate", 100.0 if passed else 0.0),
                )
            )

        failed_count = len(self.checks) - passed_count
        overall_rate = round(100.0 * passed_count / len(self.checks), 2)
        is_healthy = failed_count == 0

        report = DataQualityReport(
            dataset_name=dataset_name,
            total_records=len(df),
            total_checks=len(self.checks),
            passed_checks=passed_count,
            failed_checks=failed_count,
            overall_pass_rate=overall_rate,
            is_dataset_healthy=is_healthy,
            results=results,
        )

        logger.info(
            f"DQ Suite for '{dataset_name}' complete: {passed_count}/{len(self.checks)} checks passed "
            f"({overall_rate}%). Healthy: {is_healthy}"
        )
        return report

    def save_report_to_s3(self, report: DataQualityReport, output_dir: Optional[str] = None):
        """
        Exports DQ report as JSON artifact to Lakehouse reports directory.
        """
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"dq_report_{report.dataset_name}_{timestamp_str}.json"

        target_dir = output_dir or "/tmp/riskgraph/lakehouse/reports"
        os.makedirs(target_dir, exist_ok=True)
        filepath = os.path.join(target_dir, filename)

        with open(filepath, "w") as f:
            f.write(report.model_dump_json(indent=2))

        logger.info(f"Saved Data Quality report artifact to {filepath}")
        return filepath
