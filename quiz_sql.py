"""Offline template-based SQL generator for the quiz runner.

``generate_sql`` is the pattern-matching fallback used by ``run_quizzes_v2.py``
when the Claude CLI fails to produce a usable query. It maps keywords in the
question to a Trino/Presto SQL template, filling in the expected output columns.

Like ``quiz_heuristics``, this module is pure (no network, browser, or CLI), so
it is unit-tested directly in ``tests/test_quiz_sql.py``.
"""
from typing import List, Union

# The DOM parser yields columns as ``{"name": ..., "type": ...}`` dicts, while
# older callers pass plain name strings. ``generate_sql`` only needs the names.
Column = Union[str, dict]


def _column_names(expected_cols: List[Column]) -> List[str]:
    """Normalize a mixed list of column dicts/strings to a list of name strings."""
    names = []
    for c in expected_cols or []:
        names.append(c["name"] if isinstance(c, dict) else c)
    return names


def generate_sql(question: str, tables: list, expected_cols: list) -> str:
    """Generate SQL based on question requirements and expected columns.

    ``expected_cols`` may be a list of ``{"name", "type"}`` dicts (as produced by
    the live DOM parser) or a plain list of column-name strings; both are
    accepted.
    """
    q = question.lower()
    table = tables[0] if tables else "bootcamp.sales"

    # Normalize columns to names so the templates can join them as strings even
    # when the caller passes {"name", "type"} dicts.
    expected_cols = _column_names(expected_cols)

    # Use expected columns to build proper SELECT
    base_cols = [c for c in expected_cols if c not in ['running_total', 'row_num', 'rn', 'prev_amount', 'next_amount', 'rank']]

    # Running total / cumulative sum
    if "running total" in q or "cumulative" in q:
        partition_col = None
        order_col = None
        sum_col = "amount"

        if "salesperson" in q:
            partition_col = "salesperson"
        if "sale_date" in q or "ordered by" in q:
            order_col = "sale_date"

        # Find the running_total column name from expected
        running_col = "running_total"
        for c in expected_cols:
            if "running" in c or "total" in c:
                running_col = c
                break

        select_cols = ", ".join(base_cols) if base_cols else "*"

        if partition_col and order_col:
            return f"""SELECT {select_cols}, SUM({sum_col}) OVER (PARTITION BY {partition_col} ORDER BY {order_col}) AS {running_col}
FROM {table}"""
        elif order_col:
            return f"""SELECT {select_cols}, SUM({sum_col}) OVER (ORDER BY {order_col}) AS {running_col}
FROM {table}"""

    # Top score / rank with ties - need to filter to rank=1
    if "top score" in q or ("rank" in q and "ties" in q):
        # Find partition and order columns from expected
        partition_col = next((c for c in expected_cols if "date" in c or "game" in c), "game_date")
        score_col = next((c for c in expected_cols if "score" in c and "rank" not in c), "score")
        rank_col = next((c for c in expected_cols if "rank" in c), "score_rank")

        # Build the expected columns
        select_cols = ", ".join(expected_cols) if expected_cols else "*"

        # Use subquery with RANK, then filter to rank=1 for "top" scores
        return f"""SELECT {select_cols} FROM (SELECT *, RANK() OVER (PARTITION BY {partition_col} ORDER BY {score_col} DESC) AS {rank_col}, COUNT(*) OVER (PARTITION BY {partition_col}) AS players_that_day FROM {table}) t WHERE {rank_col} = 1"""

    # Row number / ranking (no ties)
    if "row_number" in q or ("rank" in q and "ties" not in q):
        partition = None
        order = "id"
        if "department" in q:
            partition = "department"
        if "salary" in q:
            order = "salary DESC"

        select_cols = ", ".join(base_cols) if base_cols else "*"
        rn_col = next((c for c in expected_cols if "row" in c or "rn" in c or "rank" in c), "row_num")

        if partition:
            return f"""SELECT {select_cols}, ROW_NUMBER() OVER (PARTITION BY {partition} ORDER BY {order}) AS {rn_col} FROM {table}"""
        return f"""SELECT {select_cols}, ROW_NUMBER() OVER (ORDER BY {order}) AS {rn_col} FROM {table}"""

    # Session calculation from event logs
    if "session" in q and ("consecutive" in q or "gap" in q or "event" in q):
        # Complex sessionization query using LAG and gap detection
        return f"""WITH event_gaps AS ( SELECT *, LAG(event_time) OVER (PARTITION BY user_id ORDER BY event_time) AS prev_time, CASE WHEN event_time - LAG(event_time) OVER (PARTITION BY user_id ORDER BY event_time) > INTERVAL '30 minutes' OR LAG(event_time) OVER (PARTITION BY user_id ORDER BY event_time) IS NULL THEN 1 ELSE 0 END AS new_session FROM {table} ), sessions AS ( SELECT *, SUM(new_session) OVER (PARTITION BY user_id ORDER BY event_time) AS session_num FROM event_gaps ) SELECT user_id, session_num, MIN(event_time) AS session_start, MAX(event_time) AS session_end, EXTRACT(EPOCH FROM (MAX(event_time) - MIN(event_time)))/60 AS duration_minutes, COUNT(*) AS event_count FROM sessions GROUP BY user_id, session_num"""

    # LAG / previous
    if "previous" in q or "lag" in q:
        select_cols = ", ".join(base_cols) if base_cols else "*"
        return f"""SELECT {select_cols}, LAG(amount, 1) OVER (ORDER BY sale_date) AS prev_amount
FROM {table}"""

    # LEAD / next
    if "next" in q or "lead" in q:
        select_cols = ", ".join(base_cols) if base_cols else "*"
        return f"""SELECT {select_cols}, LEAD(amount, 1) OVER (ORDER BY sale_date) AS next_amount
FROM {table}"""

    # Most recent price (Trino-compatible using ROW_NUMBER)
    if "most recent" in q and "price" in q:
        # Find the date/timestamp column for ordering
        order_col = "effective_date"
        if "updated_at" in q:
            order_col = "updated_at"

        select_cols = ", ".join(expected_cols) if expected_cols else "product_id, price, effective_date"
        return f"""SELECT {select_cols}
FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY {order_col} DESC) AS rn
    FROM {table}
) t
WHERE rn = 1"""

    # Customers with no orders
    if ("have not" in q or "never" in q or "no order" in q) and "customer" in q:
        # Use expected columns directly without table prefix
        select_cols = ", ".join(expected_cols) if expected_cols else "customer_id, customer_name"
        return f"""SELECT {select_cols}
FROM {table} c
WHERE NOT EXISTS (
    SELECT 1 FROM bootcamp.orders o
    WHERE o.customer_id = c.customer_id
)"""

    # Average with rounding
    if "average" in q or "avg" in q:
        if "round" in q:
            return f"""SELECT ROUND(AVG(total)::numeric, 2) AS average
FROM {table}"""
        return f"""SELECT AVG(amount) AS average
FROM {table}"""

    # Count with GROUP BY
    if "count" in q and "group" in q:
        group_col = expected_cols[0] if expected_cols else "category"
        return f"""SELECT {group_col}, COUNT(*) AS count
FROM {table}
GROUP BY {group_col}"""

    # HAVING clause question
    if "having" in q or "filter" in q and "group" in q:
        return f"""SELECT category, SUM(amount) AS total
FROM {table}
GROUP BY category
HAVING SUM(amount) > 1000"""

    # Default: select expected columns
    if expected_cols:
        return f"SELECT {', '.join(expected_cols)}\nFROM {table}"
    return f"SELECT *\nFROM {table}\nLIMIT 100"
