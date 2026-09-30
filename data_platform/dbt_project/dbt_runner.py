from pathlib import Path
import sqlite3
from typing import Any
import pandas as pd


class DBTRunner:
    """Standalone and CI execution runner executing dbt SQL models

    against SQLite, DuckDB, or PostgreSQL engines.
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.project_dir = Path(__file__).parent
        self.staging_sql_path = self.project_dir / "models" / "staging" / "stg_incidents.sql"
        self.marts_sql_path = self.project_dir / "models" / "marts" / "fct_service_reliability.sql"
        self._init_schema()

    def _init_schema(self) -> None:
        """Initializes raw incident telemetry ingestion table."""
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS raw_incidents (
                ticket_id TEXT PRIMARY KEY,
                service_name TEXT NOT NULL,
                severity TEXT NOT NULL,
                started_at TEXT NOT NULL,
                resolved_at TEXT NOT NULL
            );
        """)
        self.conn.commit()

    def seed_incidents(self, incidents: list[dict[str, Any]]) -> int:
        """Seeds raw incident telemetry records into the database."""
        cursor = self.conn.cursor()
        inserted = 0
        for inc in incidents:
            cursor.execute("""
                INSERT OR REPLACE INTO raw_incidents (
                    ticket_id, service_name, severity, started_at, resolved_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                inc["ticket_id"],
                inc["service_name"],
                inc["severity"],
                inc["started_at"],
                inc["resolved_at"],
            ))
            inserted += 1
        self.conn.commit()
        return inserted

    def run_staging(self) -> pd.DataFrame:
        """Executes the stg_incidents staging view model."""
        with open(self.staging_sql_path, encoding="utf-8") as f:
            sql = f.read()

        cursor = self.conn.cursor()
        cursor.execute("DROP VIEW IF EXISTS stg_incidents;")
        cursor.execute(f"CREATE VIEW stg_incidents AS {sql};")
        self.conn.commit()

        return pd.read_sql_query("SELECT * FROM stg_incidents;", self.conn)

    def run_marts(self) -> pd.DataFrame:
        """Executes the fct_service_reliability mart table model."""
        with open(self.marts_sql_path, encoding="utf-8") as f:
            sql = f.read()

        cursor = self.conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS fct_service_reliability;")
        cursor.execute(f"CREATE TABLE fct_service_reliability AS {sql};")
        self.conn.commit()

        return pd.read_sql_query("SELECT * FROM fct_service_reliability;", self.conn)

    def run_pipeline(self, incidents: list[dict[str, Any]] | None = None) -> dict[str, pd.DataFrame]:
        """Runs the entire dbt ELT modeling workflow from seeds to marts."""
        if incidents:
            self.seed_incidents(incidents)

        stg_df = self.run_staging()
        marts_df = self.run_marts()

        return {
            "stg_incidents": stg_df,
            "fct_service_reliability": marts_df,
        }

    def close(self) -> None:
        self.conn.close()
