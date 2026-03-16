"""Tests for the synthetic data generator."""

import os
import sqlite3
import tempfile

import pandas as pd
import pytest

from src.data_generator import (
    create_database,
    generate_usage_data,
    load_usage_data,
    seed_sections,
    setup_demo_database,
)
from config.settings import DEFAULT_SECTIONS, METRIC_COLUMNS


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


class TestCreateDatabase:
    def test_creates_tables(self, db_path):
        conn = create_database(db_path)
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        conn.close()
        assert "platform_sections" in tables
        assert "usage_metrics" in tables
        assert "forecasts" in tables
        assert "variance_reports" in tables


class TestSeedSections:
    def test_inserts_default_sections(self, db_path):
        conn = create_database(db_path)
        seed_sections(conn)
        rows = conn.execute("SELECT * FROM platform_sections").fetchall()
        conn.close()
        assert len(rows) == len(DEFAULT_SECTIONS)


class TestGenerateUsageData:
    def test_returns_dataframe(self):
        df = generate_usage_data(num_months=12)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_contains_all_metrics(self):
        df = generate_usage_data(num_months=6)
        for metric in METRIC_COLUMNS:
            assert metric in df.columns

    def test_contains_all_sections(self):
        df = generate_usage_data(num_months=6)
        expected_ids = {s["section_id"] for s in DEFAULT_SECTIONS}
        assert set(df["section_id"].unique()) == expected_ids

    def test_deterministic_with_seed(self):
        df1 = generate_usage_data(num_months=6, seed=99)
        df2 = generate_usage_data(num_months=6, seed=99)
        pd.testing.assert_frame_equal(df1, df2)


class TestLoadUsageData:
    def test_loads_into_database(self, db_path):
        conn = create_database(db_path)
        seed_sections(conn)
        df = generate_usage_data(num_months=6)
        load_usage_data(conn, df)
        count = conn.execute("SELECT COUNT(*) FROM usage_metrics").fetchone()[0]
        conn.close()
        assert count == len(df)


class TestSetupDemoDatabase:
    def test_full_setup(self, db_path):
        conn = setup_demo_database(db_path, num_months=12)
        sections = conn.execute("SELECT COUNT(*) FROM platform_sections").fetchone()[0]
        metrics = conn.execute("SELECT COUNT(*) FROM usage_metrics").fetchone()[0]
        conn.close()
        assert sections == len(DEFAULT_SECTIONS)
        assert metrics > 0
