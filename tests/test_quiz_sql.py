"""Tests for the offline SQL template generator in ``quiz_sql``.

``generate_sql`` is a pure function, so these run with no browser, network, or
Claude CLI. The most important case is the regression guard for dict-shaped
columns: the live DOM parser yields ``{"name", "type"}`` dicts, and the function
used to crash when joining them.
"""
import pytest

from quiz_sql import generate_sql, _column_names


# Columns as the live DOM parser produces them (dicts) vs. the plain-string form.
DICT_COLS = [
    {"name": "salesperson", "type": "varchar"},
    {"name": "amount", "type": "double"},
    {"name": "running_total", "type": "double"},
]
STR_COLS = ["salesperson", "amount", "running_total"]


def test_column_names_normalizes_dicts_and_strings():
    assert _column_names(DICT_COLS) == STR_COLS
    assert _column_names(STR_COLS) == STR_COLS
    assert _column_names([]) == []
    assert _column_names(None) == []


def test_dict_columns_do_not_crash_and_match_string_form():
    """Regression: dict-shaped expected_cols used to raise TypeError on join."""
    q = "compute a running total ordered by sale_date"
    from_dicts = generate_sql(q, ["bootcamp.sales"], DICT_COLS)
    from_strings = generate_sql(q, ["bootcamp.sales"], STR_COLS)
    assert from_dicts == from_strings
    # And it produced real SQL, not a crash or empty string.
    assert from_dicts.startswith("SELECT")
    assert "running_total" in from_dicts


def test_running_total_with_partition_and_order():
    sql = generate_sql(
        "running total of amount by salesperson ordered by sale_date",
        ["bootcamp.sales"],
        ["salesperson", "amount", "running_total"],
    )
    assert "SUM(amount) OVER (PARTITION BY salesperson ORDER BY sale_date)" in sql
    assert "AS running_total" in sql


def test_row_number_partitioned_by_department():
    sql = generate_sql(
        "assign a row_number per department by salary",
        ["bootcamp.employees"],
        ["department", "salary", "row_num"],
    )
    assert "ROW_NUMBER() OVER (PARTITION BY department ORDER BY salary DESC)" in sql
    assert "AS row_num" in sql


def test_top_score_uses_rank_and_filters_to_one():
    sql = generate_sql(
        "find the top score with ties per game_date",
        ["bootcamp.scores"],
        ["game_date", "score", "score_rank"],
    )
    assert "RANK() OVER (PARTITION BY game_date ORDER BY score DESC)" in sql
    assert "WHERE score_rank = 1" in sql


def test_customers_with_no_orders_uses_not_exists():
    sql = generate_sql(
        "customers who have not placed an order",
        ["bootcamp.customers"],
        ["customer_id", "customer_name"],
    )
    assert "NOT EXISTS" in sql
    assert "bootcamp.orders" in sql


def test_average_with_rounding():
    sql = generate_sql("average total rounded to 2 places", ["bootcamp.orders"], [])
    assert "ROUND(AVG(total)" in sql


def test_default_table_when_none_given():
    sql = generate_sql("anything unmatched", [], [])
    assert "FROM bootcamp.sales" in sql
    assert sql.startswith("SELECT *")


def test_default_selects_expected_columns_when_no_rule_matches():
    sql = generate_sql("totally unmatched question", ["my.table"], ["a", "b"])
    assert sql == "SELECT a, b\nFROM my.table"
