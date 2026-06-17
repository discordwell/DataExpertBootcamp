"""Tests for the offline answer heuristic in ``quiz_heuristics``.

These lock in the behaviour of ``get_answer`` so future edits to the keyword
rules don't silently change which option gets picked. Every case is built so
exactly one option carries the keyword the matching rule looks for, which makes
the expected index unambiguous regardless of option order.
"""
import pytest

from quiz_heuristics import get_answer


# Each case: (question, options, expected_index). The expected option is the one
# the relevant rule should select; the distractors deliberately avoid its keywords.
RULE_CASES = [
    # --- Week 1: Data Modeling ---
    ("Why use a struct or array column?",
     ["it is a complex nested type", "a plain integer", "a single string"], 0),
    ("What is the cumulative table design approach?",
     ["a running total aggregated over time", "delete old rows nightly", "a simple key lookup"], 0),
    ("Best practice for slowly changing dimensions?",
     ["use type 2 to track history", "overwrite the old value", "drop the column"], 0),
    ("What belongs in a fact table?",
     ["numeric measures and metrics", "purely descriptive labels", "static colors"], 0),
    ("What is the grain of a table?",
     ["the lowest level of detail / granularity", "the database vendor", "the file name"], 0),
    ("What does idempotent mean?",
     ["produces the same result run multiple times", "random output each run", "raises on rerun"], 0),
    ("Compare a surrogate key to a business key",
     ["an artificial generated value with no business meaning", "the customer's email", "a color code"], 0),
    ("Describe a star schema",
     ["a denormalized design with a central fact", "a graph database", "a flat csv file"], 0),

    # --- Week 2: SQL ---
    ("How do window functions work?",
     ["use OVER with PARTITION BY", "use a plain GROUP BY", "use a temp file"], 0),
    ("What is a CTE?",
     ["a WITH clause, optionally recursive, for readability", "a database trigger", "a stored colour"], 0),
    ("What does the HAVING clause do?",
     ["filter aggregate results after group", "rename a column", "create an index file"], 0),
    ("Difference between UNION and intersection?",
     ["returns distinct unique rows, removing duplicates", "multiplies the tables", "renames columns"], 0),

    # --- Week 3: Big-O / data structures ---
    ("What is the time complexity of binary search?",
     ["O(log n)", "O(p)", "O(z squared)"], 0),
    ("Bubble sort uses a nested loop; its time complexity is?",
     ["O(n^2)", "O(j)", "O(k)"], 0),
    ("Describe a stack",
     ["LIFO: last in first out via push pop", "a sorted heap of colours", "a random bag"], 0),
    ("Describe a queue",
     ["FIFO: first in first out via enqueue dequeue", "a sorted set of colours", "a random bag"], 0),

    # --- Week 4: Pipelines ---
    ("What is ETL?",
     ["extract transform load into a warehouse", "a network protocol", "a chart type"], 0),
    ("What is a DAG used for in orchestration?",
     ["a graph with no cycle expressing dependencies", "a circular buffer", "a single file"], 0),

    # --- Week 5: ML/AI ---
    ("What is overfitting and how do you fix it?",
     ["add regularization or dropout and more data", "use fewer comments", "rename variables"], 0),
    ("What is supervised learning?",
     ["it uses labeled data with a target", "it clusters raw input", "it just guesses"], 0),

    # --- Week 6: Distributed ---
    ("What is a Spark shuffle?",
     ["an expensive network redistribute to avoid", "a free local copy", "a small lookup"], 0),
    ("What does broadcast do in a join?",
     ["send a small table to each node to avoid shuffle", "delete the table", "sort the rows"], 0),

    # --- Weeks 7-8: Interview ---
    ("Explain the CAP theorem",
     ["you can only pick two of three: consistency, availability, partition tolerance",
      "every system is always fast", "it is about pricing"], 0),
    ("What does ACID stand for?",
     ["atomic consistent isolated durable", "a soft eventual state", "a cheap fast store"], 0),
]


@pytest.mark.parametrize("question,options,expected", RULE_CASES)
def test_rule_selects_expected_option(question, options, expected):
    assert get_answer(question, options) == expected


@pytest.mark.parametrize("question,options,expected", RULE_CASES)
def test_rules_are_order_independent(question, options, expected):
    """Reversing the option order should still pick the same option text."""
    expected_text = options[expected]
    reversed_opts = list(reversed(options))
    chosen = get_answer(question, reversed_opts)
    assert reversed_opts[chosen] == expected_text


def test_default_scorer_prefers_longer_jargon_rich_option():
    # No rule matches "clouds"; the fallback prefers the longest, most technical option.
    options = [
        "short",
        "a much longer and more detailed answer about the data system process model",
        "medium length answer",
    ]
    assert get_answer("Tell me something random about clouds", options) == 1


def test_default_scorer_jargon_breaks_length_ties():
    # Two equal-length options; the one containing technical terms wins (+10 each).
    techy = "data table query rows abcd wxyz"   # 3 technical terms: data/table/query
    plain = "z" * len(techy)                     # identical length, zero technical terms
    assert len(plain) == len(techy)
    assert get_answer("no keywords here at all", [plain, techy]) == 1


def test_case_insensitive():
    # Upper-case question and options still match the lowercase rules.
    assert get_answer("WHAT DOES IDEMPOTENT MEAN?",
                      ["PRODUCES THE SAME RESULT EVERY TIME", "RAISES AN ERROR"]) == 0


def test_single_option_returns_zero():
    assert get_answer("anything at all", ["only choice"]) == 0


def test_empty_options_raises():
    with pytest.raises(ValueError):
        get_answer("a question", [])


@pytest.mark.parametrize("question,options,_expected", RULE_CASES)
def test_return_is_always_valid_index(question, options, _expected):
    idx = get_answer(question, options)
    assert isinstance(idx, int)
    assert 0 <= idx < len(options)
