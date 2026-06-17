"""Canonical DataExpert bootcamp quiz curriculum — the single source of truth.

Both runners used to hardcode their own copy of the ~50 ``(slug, title)`` pairs,
and the two copies drifted:

* ``run_quizzes_v2.py`` was missing the Week 3 "Big O Notation" quiz, so its
  primary runner silently skipped a quiz it claims to solve (49 vs. 50).
* ``run_quizzes_v2.status_check`` re-derived the per-week grouping with
  magic-number slices (``ALL_QUIZZES[0:5]``, ``[5:12]``, ...) that break silently
  if the list is ever reordered.

Defining the curriculum once here keeps the runners in sync and lets the week
grouping come from real structure instead of slices. The ``title`` is only used
for display/logging; the ``slug`` is the load-bearing value (it builds the lesson
URL via ``common.lesson_url``).

This module is pure data, so it is verified by ``tests/test_quizzes.py``.
"""
from typing import Dict, List, Tuple

Quiz = Tuple[str, str]  # (lesson slug, human-readable title)

# Ordered: week label -> quizzes, in the order they are attempted and reported.
# Dicts preserve insertion order (Python 3.7+), which both runners rely on.
CURRICULUM: Dict[str, List[Quiz]] = {
    "Week 1: Data Modeling": [
        ("cumulative-data-quiz", "Cumulative Data"),
        ("scd-quiz", "Slowly Changing Dimensions"),
        ("fact-modeling-quiz", "Fact Modeling"),
        ("core-data-modeling-quiz", "Core Data Modeling Elements"),
        ("data-modeling-quiz", "Data Modeling"),
    ],
    "Week 2: SQL": [
        ("sql-growth-accounting-quiz", "Growth Accounting"),
        ("sql-aggregation-tuesdayquiz", "Aggregation"),
        ("window-functions-wednesday-quiz", "Window Functions"),
        ("thursday-quiz-a8b81", "SQL Thursday"),
        ("fridayquiz-41956", "SQL Friday"),
        ("saturdayquiz-289d8", "SQL Saturday"),
        ("sundayquiz-4bfbb", "SQL Sunday"),
    ],
    "Week 3: Python & Data Structures": [
        ("mondaybigonotation-24a31", "Big O Notation"),
        ("tuesdayquiz-2a59e", "Python Tuesday"),
        ("wednesdayquiz-795e0", "Python Wednesday"),
        ("thursdayquiz-4d179", "Python Thursday"),
        ("fridayquiz-8d36d", "Python Friday"),
        ("saturdayquiz-628a3", "Python Saturday"),
        ("sundayquiz-ff389", "Python Sunday"),
    ],
    "Week 4: Data Pipelines": [
        ("mondaydatapipelinesquiz-8f0e2", "Data Pipelines Intro"),
        ("tuesdayquiz-ba9b6", "Pipelines Tuesday"),
        ("wednesdayquiz-0d421", "Pipelines Wednesday"),
        ("thursdayquiz-5bc94", "Pipelines Thursday"),
        ("fridayquiz-efa43", "Pipelines Friday"),
        ("saturdayquiz-d2fd4", "Pipelines Saturday"),
        ("sundayquiz-c4dda", "Pipelines Sunday"),
    ],
    "Week 5: Machine Learning & AI": [
        ("mondaymlandaiquiz-e4a32", "ML & AI Intro"),
        ("tuesdayquiz-4fea1", "ML Tuesday"),
        ("wednesdayquiz-33b10", "ML Wednesday"),
        ("thursdayquiz-a6cdb", "ML Thursday"),
        ("fridayquiz-7e3bd", "ML Friday"),
        ("saturdayquiz-a156e", "ML Saturday"),
        ("sundayquiz-a92f1", "ML Sunday"),
    ],
    "Week 6: Distributed Computing": [
        ("mondayquiz-54719", "Distributed Monday"),
        ("tuesdayquiz-1895d", "Distributed Tuesday"),
        ("wednesdayquiz-2119f", "Distributed Wednesday"),
        ("thursdayquiz-4b3ee", "Distributed Thursday"),
        ("fridayquiz-1e809", "Distributed Friday"),
        ("saturdayquiz-12e15", "Distributed Saturday"),
        ("sundayquiz-29862", "Distributed Sunday"),
    ],
    "Week 7: Data Engineer Interview": [
        ("mondaydataengineerinterviewquiz-39afc", "DE Interview Monday"),
        ("tuesdayquiz-a58fc", "DE Interview Tuesday"),
        ("wednesdayquiz-8c099", "DE Interview Wednesday"),
        ("thursdayquiz-c78e7", "DE Interview Thursday"),
        ("fridayquiz-5af2b", "DE Interview Friday"),
        ("saturdayquiz-a77da", "DE Interview Saturday"),
        ("sundayquiz-1b699", "DE Interview Sunday"),
    ],
    "Week 8: AI Engineer Interview": [
        ("mondayquiz-e949d", "AI Engineer Monday"),
        ("tuesdayquiz-b98b1", "AI Engineer Tuesday"),
        ("wednesdayquiz-95a12", "AI Engineer Wednesday"),
    ],
}

# Flat list of every (slug, title) in curriculum order. ``run_quizzes_v2.main``
# iterates this; ``status_check`` groups by ``CURRICULUM`` directly.
ALL_QUIZZES: List[Quiz] = [quiz for quizzes in CURRICULUM.values() for quiz in quizzes]
