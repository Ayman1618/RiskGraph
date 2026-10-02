import re
from typing import Any, Callable, Dict, List
import pandas as pd


class DQCheck:
    def __init__(self, check_name: str, check_type: str, description: str, func: Callable[[pd.DataFrame], Dict[str, Any]]):
        self.check_name = check_name
        self.check_type = check_type
        self.description = description
        self.func = func

    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        return self.func(df)


def check_not_null(column_name: str) -> DQCheck:
    def _check(df: pd.DataFrame) -> Dict[str, Any]:
        if column_name not in df.columns:
            return {"passed": False, "failed_count": len(df), "error": f"Column {column_name} missing"}
        nulls = df[column_name].isnull().sum()
        return {
            "passed": nulls == 0,
            "failed_count": int(nulls),
            "pass_rate": round(100.0 * (len(df) - nulls) / max(len(df), 1), 2)
        }
    return DQCheck(
        check_name=f"not_null_{column_name}",
        check_type="COMPLETENESS",
        description=f"Ensure column {column_name} contains no NULL or NaN values",
        func=_check
    )


def check_positive_amount(column_name: str = "amount") -> DQCheck:
    def _check(df: pd.DataFrame) -> Dict[str, Any]:
        if column_name not in df.columns:
            return {"passed": False, "failed_count": len(df), "error": f"Column {column_name} missing"}
        invalid = (df[column_name] <= 0).sum()
        return {
            "passed": invalid == 0,
            "failed_count": int(invalid),
            "pass_rate": round(100.0 * (len(df) - invalid) / max(len(df), 1), 2)
        }
    return DQCheck(
        check_name=f"positive_{column_name}",
        check_type="RANGE",
        description=f"Ensure all transactions have {column_name} > 0",
        func=_check
    )


def check_valid_enum(column_name: str, allowed_values: List[str]) -> DQCheck:
    def _check(df: pd.DataFrame) -> Dict[str, Any]:
        if column_name not in df.columns:
            return {"passed": False, "failed_count": len(df), "error": f"Column {column_name} missing"}
        invalid = (~df[column_name].isin(allowed_values)).sum()
        return {
            "passed": invalid == 0,
            "failed_count": int(invalid),
            "pass_rate": round(100.0 * (len(df) - invalid) / max(len(df), 1), 2)
        }
    return DQCheck(
        check_name=f"valid_enum_{column_name}",
        check_type="SCHEMA_CONFORMANCE",
        description=f"Ensure column {column_name} only contains valid values: {allowed_values}",
        func=_check
    )


def check_valid_ipv4(column_name: str = "ip_address") -> DQCheck:
    ipv4_pattern = re.compile(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$")

    def _check(df: pd.DataFrame) -> Dict[str, Any]:
        if column_name not in df.columns:
            return {"passed": False, "failed_count": len(df), "error": f"Column {column_name} missing"}
        invalid = df[column_name].apply(lambda x: not bool(ipv4_pattern.match(str(x)))).sum()
        return {
            "passed": invalid == 0,
            "failed_count": int(invalid),
            "pass_rate": round(100.0 * (len(df) - invalid) / max(len(df), 1), 2)
        }
    return DQCheck(
        check_name=f"valid_format_{column_name}",
        check_type="FORMAT",
        description=f"Ensure column {column_name} adheres to valid IPv4 format",
        func=_check
    )


def build_standard_transaction_dq_suite() -> List[DQCheck]:
    return [
        check_not_null("transaction_id"),
        check_not_null("user_id"),
        check_not_null("amount"),
        check_not_null("ip_address"),
        check_positive_amount("amount"),
        check_valid_enum("currency", ["USD", "EUR", "GBP", "CAD"]),
        check_valid_ipv4("ip_address")
    ]
