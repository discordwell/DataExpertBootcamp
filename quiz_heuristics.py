"""Offline keyword heuristic for answering multiple-choice quiz questions.

This module holds the pure, dependency-free answer-selection logic used by the
offline quiz runners (``run_all_quizzes.py`` and ``quiz_solver.py``). It does not
touch the network or a browser, which makes it cheap to unit test — see
``tests/test_quiz_heuristics.py``.

The heuristic is intentionally simple: a long list of ``topic -> keyword`` rules
that map a question to the option whose text best matches the expected answer.
When no rule fires it falls back to a length-plus-jargon score, which tends to
prefer the most complete-sounding option.

For the harder quizzes the ``run_quizzes_v2.py`` runner delegates to the Claude
CLI instead of this heuristic; this module is the offline best-effort fallback.
"""
from typing import List

# Generic technical terms used by the fallback scorer to bias toward the most
# substantive-looking option when no specific rule matches.
TECHNICAL_TERMS = ["data", "table", "query", "process", "system", "function", "model", "type"]


def get_answer(question: str, options: List[str]) -> int:
    """Return the index of the best-guess answer for a multiple-choice question.

    Args:
        question: The question text.
        options: The answer option strings, in display order.

    Returns:
        The 0-based index into ``options`` of the chosen answer. Always a valid
        index as long as ``options`` is non-empty.

    Raises:
        ValueError: If ``options`` is empty (there is nothing to choose).
    """
    if not options:
        raise ValueError("get_answer requires at least one option")

    q = question.lower()
    opts = [o.lower() for o in options]

    # Data Modeling - Week 1
    if "struct" in q and "array" in q:
        for i, o in enumerate(opts):
            if "complex" in o: return i
    if "cumulative" in q and ("table" in q or "design" in q or "approach" in q):
        for i, o in enumerate(opts):
            if any(x in o for x in ["running total", "aggregate over time", "historical", "growing"]): return i
    if "slowly changing" in q or "scd" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["type 2", "track history", "version", "historical"]): return i
    if "type 1" in q and "scd" in q.lower():
        for i, o in enumerate(opts):
            if any(x in o for x in ["overwrite", "no history", "update in place"]): return i
    if "type 2" in q and "scd" in q.lower():
        for i, o in enumerate(opts):
            if any(x in o for x in ["new row", "history", "effective date", "version"]): return i
    if "fact table" in q or "fact model" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["measure", "metric", "event", "transaction", "numeric", "foreign key"]): return i
    if "dimension" in q and ("table" in q or "model" in q):
        for i, o in enumerate(opts):
            if any(x in o for x in ["attribute", "descriptive", "context", "who", "what", "where"]): return i
    if "grain" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["level of detail", "granularity", "atomic", "lowest", "single row"]): return i
    if "idempotent" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["same result", "multiple times", "repeatable", "no side effect"]): return i
    if "surrogate key" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["artificial", "generated", "no business meaning", "sequence"]): return i
    if "natural key" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["business", "meaningful", "real-world", "domain"]): return i
    if "star schema" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["denormalized", "fact center", "simple", "one level"]): return i
    if "snowflake schema" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["normalized", "dimension split", "hierarchy"]): return i
    if "degenerate dimension" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["fact table", "no dimension table", "transaction id"]): return i
    if "junk dimension" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["flag", "indicator", "low cardinality", "miscellaneous"]): return i
    if "conformed dimension" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["shared", "multiple fact", "consistent", "enterprise"]): return i

    # SQL - Week 2
    if "window function" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["over", "partition", "rank", "row_number", "running"]): return i
    if "cte" in q or "common table expression" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["with", "recursive", "readability", "temporary"]): return i
    if "group by" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["aggregate", "sum", "count", "combine rows"]): return i
    if "having" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["filter aggregate", "after group", "condition on aggregate"]): return i
    if "inner join" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["both", "match", "intersection"]): return i
    if "left join" in q or "left outer" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["all from left", "null for right", "preserve left"]): return i
    if "cross join" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["cartesian", "all combinations", "multiply"]): return i
    if "union" in q and "union all" not in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["distinct", "unique", "remove duplicate"]): return i
    if "union all" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["all rows", "include duplicate", "faster"]): return i
    if "subquery" in q or "sub-query" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["nested", "inner", "within"]): return i
    if "index" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["faster", "lookup", "b-tree", "performance"]): return i
    if "partition by" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["group", "window", "divide", "segment"]): return i
    if "row_number" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["sequential", "unique", "1,2,3"]): return i
    if "rank" in q and "dense" not in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["gap", "skip", "tie"]): return i
    if "dense_rank" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["no gap", "consecutive", "no skip"]): return i
    if "lag" in q or "lead" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["previous", "next", "offset", "row"]): return i

    # Big O / Algorithms - Week 3
    if "big o" in q or "time complexity" in q or "space complexity" in q:
        if "hash" in q and ("lookup" in q or "search" in q or "get" in q):
            for i, o in enumerate(opts):
                if "o(1)" in o or "constant" in o: return i
        if "binary search" in q:
            for i, o in enumerate(opts):
                if "o(log" in o or "logarithmic" in o: return i
        if "linear search" in q:
            for i, o in enumerate(opts):
                if "o(n)" in o and "o(n^2)" not in o: return i
        if "bubble sort" in q or "nested loop" in q:
            for i, o in enumerate(opts):
                if "o(n^2)" in o or "o(n²)" in o or "quadratic" in o: return i
        if "merge sort" in q or "quick sort" in q:
            for i, o in enumerate(opts):
                if "o(n log" in o or "n log n" in o: return i
    if "hash table" in q or "dictionary" in q or "hashmap" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["o(1)", "constant", "key-value"]): return i
    if "linked list" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["node", "pointer", "sequential access"]): return i
    if "array" in q and "vs" in q and "list" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["contiguous", "fixed", "index"]): return i
    if "stack" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["lifo", "last in first out", "push pop"]): return i
    if "queue" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["fifo", "first in first out", "enqueue dequeue"]): return i
    if "tree" in q and "binary" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["two children", "left right", "hierarchical"]): return i
    if "recursion" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["call itself", "base case", "self-referential"]): return i

    # Data Pipelines - Week 4
    if "etl" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["extract transform load", "data warehouse", "batch"]): return i
    if "elt" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["extract load transform", "transform after", "modern"]): return i
    if "dag" in q or "directed acyclic" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["no cycle", "dependencies", "workflow", "one direction"]): return i
    if "batch" in q and "processing" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["scheduled", "interval", "group", "throughput"]): return i
    if "stream" in q and "processing" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["real-time", "continuous", "low latency", "event"]): return i
    if "airflow" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["orchestrat", "dag", "schedule", "workflow"]): return i
    if "data lake" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["raw", "unstructured", "schema on read", "storage"]): return i
    if "data warehouse" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["structured", "schema on write", "olap", "analytical"]): return i
    if "data mart" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["subset", "department", "specific", "focused"]): return i
    if "schema on read" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["interpret", "query time", "flexible"]): return i
    if "schema on write" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["define", "load time", "validated"]): return i

    # ML/AI - Week 5
    if "overfitting" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["regularization", "dropout", "validation", "more data", "train too well"]): return i
    if "underfitting" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["more complex", "more features", "train poorly"]): return i
    if "supervised" in q and "learning" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["labeled", "target", "classification", "regression"]): return i
    if "unsupervised" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["clustering", "unlabeled", "pattern", "no target"]): return i
    if "reinforcement" in q and "learning" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["reward", "agent", "environment", "action"]): return i
    if "bias" in q and "variance" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["tradeoff", "balance", "complexity"]): return i
    if "cross validation" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["fold", "k-fold", "split", "evaluate"]): return i
    if "gradient descent" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["minimize", "loss", "step", "optimization"]): return i
    if "neural network" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["layer", "neuron", "deep learning", "weights"]): return i
    if "transformer" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["attention", "self-attention", "parallel", "nlp"]): return i
    if "embedding" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["vector", "representation", "dense", "semantic"]): return i

    # Distributed Computing - Week 6
    if "spark" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["rdd", "dataframe", "distributed", "lazy", "in-memory"]): return i
    if "rdd" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["resilient", "immutable", "distributed"]): return i
    if "partition" in q and ("data" in q or "key" in q or "spark" in q):
        for i, o in enumerate(opts):
            if any(x in o for x in ["distribute", "parallel", "shard", "split"]): return i
    if "shuffle" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["expensive", "network", "redistribute", "avoid"]): return i
    if "lazy evaluation" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["defer", "action", "optimize", "not immediate"]): return i
    if "action" in q and "transformation" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["trigger", "collect", "count", "return"]): return i
    if "broadcast" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["small", "each node", "join", "avoid shuffle"]): return i
    if "map reduce" in q or "mapreduce" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["map", "reduce", "parallel", "distributed"]): return i
    if "hadoop" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["hdfs", "mapreduce", "distributed", "batch"]): return i
    if "kafka" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["stream", "message", "pub sub", "topic", "event"]): return i

    # Interview questions - Weeks 7-8
    if "cap theorem" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["consistency", "availability", "partition", "two of three"]): return i
    if "acid" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["atomic", "consistent", "isolated", "durable"]): return i
    if "base" in q and ("acid" in q or "eventual" in q):
        for i, o in enumerate(opts):
            if any(x in o for x in ["eventual", "available", "soft state"]): return i
    if "normalization" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["reduce redundancy", "anomal", "3nf", "integrity"]): return i
    if "denormalization" in q:
        for i, o in enumerate(opts):
            if any(x in o for x in ["performance", "read", "redundancy", "query speed"]): return i

    # Default: prefer options that are longer and more detailed (often correct)
    # Also prefer options with technical terms
    scores = []
    for i, o in enumerate(opts):
        score = len(o)  # Base score is length
        for term in TECHNICAL_TERMS:
            if term in o:
                score += 10
        scores.append(score)

    return scores.index(max(scores))
