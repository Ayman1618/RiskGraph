import json
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="riskgraph",
    help="RiskGraph — Real-Time Fraud & Identity Data Engineering Platform CLI",
    add_completion=False,
)
console = Console()


@app.command("status")
def status_cmd():
    """
    Checks the status and health of all local platform services (PostgreSQL, Kafka, Redis, Neo4j, LocalStack).
    """
    from src.common.config import settings

    console.print(Panel.fit("[bold cyan]RiskGraph Platform Health & Service Status[/bold cyan]"))

    table = Table(title="Infrastructure Components", show_header=True, header_style="bold magenta")
    table.add_column("Service", style="dim", width=15)
    table.add_column("Endpoint", width=30)
    table.add_column("Status", justify="center")

    # PostgreSQL
    try:
        import psycopg2

        conn = psycopg2.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            dbname=settings.POSTGRES_DB,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            connect_timeout=2,
        )
        conn.close()
        table.add_row(
            "PostgreSQL",
            f"{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}",
            "[green]ONLINE[/green]",
        )
    except Exception as e:
        table.add_row(
            "PostgreSQL",
            f"{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}",
            f"[red]OFFLINE[/red] ({e})",
        )

    # Redis
    try:
        import redis

        r = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            socket_connect_timeout=2,
        )
        r.ping()
        table.add_row(
            "Redis", f"{settings.REDIS_HOST}:{settings.REDIS_PORT}", "[green]ONLINE[/green]"
        )
    except Exception as e:
        table.add_row(
            "Redis", f"{settings.REDIS_HOST}:{settings.REDIS_PORT}", f"[red]OFFLINE[/red] ({e})"
        )

    # Neo4j
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
        driver.verify_connectivity()
        driver.close()
        table.add_row("Neo4j", settings.NEO4J_URI, "[green]ONLINE[/green]")
    except Exception as e:
        table.add_row("Neo4j", settings.NEO4J_URI, f"[red]OFFLINE[/red] ({e})")

    # Kafka
    try:
        import socket

        host, port_str = settings.KAFKA_BOOTSTRAP_SERVERS.split(":")[0], int(
            settings.KAFKA_BOOTSTRAP_SERVERS.split(":")[1]
        )
        s = socket.create_connection((host, port_str), timeout=1)
        s.close()
        table.add_row("Kafka", settings.KAFKA_BOOTSTRAP_SERVERS, "[green]ONLINE[/green]")
    except Exception as e:
        table.add_row(
            "Kafka", settings.KAFKA_BOOTSTRAP_SERVERS, f"[yellow]OFFLINE / LOCAL-MODE[/yellow]"
        )

    console.print(table)


@app.command("generate-stream")
def stream_cmd(
    rate: float = typer.Option(5.0, "--rate", "-r", help="Events per second"),
    count: Optional[int] = typer.Option(
        20, "--count", "-c", help="Total events to produce (None for infinite)"
    ),
    fraud_ratio: float = typer.Option(
        0.25, "--fraud-ratio", "-f", help="Ratio of fraud attack injections"
    ),
    to_kafka: bool = typer.Option(False, "--kafka", "-k", help="Stream directly to Kafka topic"),
):
    """
    Generates synthetic transaction and identity streams with realistic fraud vectors.
    """
    from src.common.config import settings
    from src.generator.generator import SyntheticEventGenerator, publish_to_kafka

    if to_kafka:
        console.print(
            f"[bold green]Streaming to Kafka topic: {settings.KAFKA_RAW_TRANSACTIONS_TOPIC}[/bold green]"
        )
        publish_to_kafka(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            rate_per_sec=rate,
            count=count,
            fraud_ratio=fraud_ratio,
        )
        return

    console.print(
        f"[bold cyan]Generating {count or 'continuous'} synthetic events (Fraud Ratio: {fraud_ratio * 100}%)...[/bold cyan]"
    )
    gen = SyntheticEventGenerator(fraud_ratio=fraud_ratio)

    table = Table(
        title="Generated Transaction Stream Sample", show_header=True, header_style="bold blue"
    )
    table.add_column("Tx ID", style="dim", width=16)
    table.add_column("User ID", width=22)
    table.add_column("Amount", justify="right")
    table.add_column("IP", width=15)
    table.add_column("Device ID", width=24)
    table.add_column("Injected Attack", style="bold")

    for tx, _ in gen.generate_stream(rate_per_sec=rate, max_events=count):
        attack = tx.metadata.get("fraud_type_injected", "none")
        style = "red" if attack != "none" else "green"
        table.add_row(
            tx.transaction_id,
            tx.user_id,
            f"${tx.amount:,.2f}",
            tx.ip_address,
            tx.device_id or "N/A",
            f"[{style}]{attack.upper()}[/{style}]",
        )

    console.print(table)


@app.command("evaluate-tx")
def evaluate_cmd(
    user_id: str = typer.Option("usr_ring_0_m1_a1b2", "--user-id", "-u", help="User ID"),
    amount: float = typer.Option(6500.0, "--amount", "-a", help="Transaction amount"),
    ip_address: str = typer.Option("192.0.2.10", "--ip", help="IP address"),
    device_id: Optional[str] = typer.Option(
        "dev_shared_ring_0_abc", "--device-id", help="Device ID"
    ),
    device_fingerprint: Optional[str] = typer.Option(
        "fp_shared_ring_0_123", "--device-fp", help="Device fingerprint"
    ),
    card_token: Optional[str] = typer.Option(None, "--card", help="Card token"),
    is_emulator: bool = typer.Option(False, "--emulator", help="Flag if device is an emulator"),
):
    """
    Evaluates a single transaction through the Real-Time Risk Engine.
    """
    from src.common.models import RiskEvaluationRequest
    from src.risk_engine.evaluator import RiskEvaluator

    req = RiskEvaluationRequest(
        user_id=user_id,
        amount=amount,
        ip_address=ip_address,
        device_id=device_id,
        device_fingerprint=device_fingerprint,
        card_token=card_token,
        is_emulator=is_emulator,
    )

    evaluator = RiskEvaluator()
    resp = evaluator.evaluate(req)

    dec_color = (
        "green" if resp.decision == "APPROVE" else "yellow" if resp.decision == "REVIEW" else "red"
    )
    console.print(
        Panel(
            f"[bold]Transaction ID:[/bold] {resp.transaction_id}\n"
            f"[bold]User ID:[/bold] {resp.user_id}\n"
            f"[bold]Risk Score:[/bold] {resp.risk_score} / 100.0\n"
            f"[bold]Decision:[/bold] [{dec_color}]{resp.decision.value}[/{dec_color}]\n"
            f"[bold]Evaluation Latency:[/bold] {resp.latency_ms} ms\n"
            f"[bold]5m Velocity Count:[/bold] {resp.velocity_5m_count}\n"
            f"[bold]Reasons:[/bold] {', '.join(resp.reasons)}",
            title="RiskGraph Real-Time Evaluation Result",
            border_style=dec_color,
        )
    )

    if resp.triggered_rules:
        r_table = Table(title="Triggered Risk Rules", show_header=True, header_style="bold red")
        r_table.add_column("Rule ID", width=25)
        r_table.add_column("Category", width=12)
        r_table.add_column("Weight", justify="right")
        r_table.add_column("Description")
        for r in resp.triggered_rules:
            r_table.add_row(r.rule_id, r.category, str(r.weight), r.description)
        console.print(r_table)


@app.command("run-dq-suite")
def dq_suite_cmd(
    sample_size: int = typer.Option(
        500, "--sample-size", "-n", help="Number of synthetic transactions to test"
    )
):
    """
    Runs automated Data Quality validation tests and generates quality reports.
    """
    import pandas as pd

    from src.data_quality.dq_runner import DataQualityRunner
    from src.generator.generator import SyntheticEventGenerator

    console.print(
        f"[bold cyan]Generating sample of {sample_size} records for Data Quality validation...[/bold cyan]"
    )
    gen = SyntheticEventGenerator()
    events = []
    for tx, _ in gen.generate_stream(rate_per_sec=0, max_events=sample_size):
        events.append(tx.model_dump())

    df = pd.DataFrame(events)

    runner = DataQualityRunner()
    report = runner.run_suite(df, dataset_name="transactions_sample")
    saved_path = runner.save_report_to_s3(report)

    status_color = "green" if report.is_dataset_healthy else "red"
    console.print(
        Panel(
            f"[bold]Dataset:[/bold] {report.dataset_name}\n"
            f"[bold]Total Records:[/bold] {report.total_records:,}\n"
            f"[bold]Total Checks:[/bold] {report.total_checks}\n"
            f"[bold]Passed Checks:[/bold] [green]{report.passed_checks}[/green]\n"
            f"[bold]Failed Checks:[/bold] [red]{report.failed_checks}[/red]\n"
            f"[bold]Overall Pass Rate:[/bold] [{status_color}]{report.overall_pass_rate}%[/{status_color}]\n"
            f"[bold]Artifact Location:[/bold] {saved_path}",
            title="Data Quality Suite Report",
            border_style=status_color,
        )
    )

    table = Table(
        title="Data Quality Individual Checks", show_header=True, header_style="bold cyan"
    )
    table.add_column("Check Name", width=25)
    table.add_column("Type", width=20)
    table.add_column("Passed?", justify="center", width=10)
    table.add_column("Pass Rate", justify="right")
    table.add_column("Description")

    for c in report.results:
        p_str = "[green]PASSED[/green]" if c.passed else "[red]FAILED[/red]"
        table.add_row(c.check_name, c.check_type, p_str, f"{c.pass_rate}%", c.description)

    console.print(table)


@app.command("detect-rings")
def detect_rings_cmd(
    min_size: int = typer.Option(3, "--min-size", "-m", help="Minimum members in ring")
):
    """
    Queries Neo4j Identity Graph for multi-account fraud rings sharing devices or IPs.
    """
    from src.graph.graph_analytics import GraphFraudAnalytics

    analytics = GraphFraudAnalytics()
    try:
        rings = analytics.find_fraud_rings(min_ring_size=min_size)
        console.print(
            f"[bold green]Discovered {len(rings)} Identity Fraud Rings in Neo4j (Min Size: {min_size})[/bold green]"
        )
        for r in rings:
            console.print(
                Panel(
                    f"[bold]Shared Device ID:[/bold] {r.get('shared_device_id')}\n"
                    f"[bold]Ring Size:[/bold] {r.get('ring_size')} accounts\n"
                    f"[bold]Linked User IDs:[/bold] {', '.join(r.get('ring_members', []))}",
                    title="Identity Fraud Ring Alert",
                    border_style="red",
                )
            )
    except Exception as e:
        console.print(f"[yellow]Neo4j query notice (run with Neo4j active): {e}[/yellow]")


if __name__ == "__main__":
    app()
