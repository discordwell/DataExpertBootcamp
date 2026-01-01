"""Run all DataExpert quizzes - Fixed with correct button selectors"""
import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright

BASE_URL = "https://www.dataexpert.io"
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

CURRICULUM = {
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


def get_answer(question: str, options: list) -> int:
    """Smart answer selection based on data engineering knowledge."""
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
    technical_terms = ["data", "table", "query", "process", "system", "function", "model", "type"]
    scores = []
    for i, o in enumerate(opts):
        score = len(o)  # Base score is length
        for term in technical_terms:
            if term in o:
                score += 10
        scores.append(score)

    return scores.index(max(scores))


async def solve_single_quiz(page, slug: str, title: str) -> dict:
    """Solve a single quiz with correct DOM selectors."""
    result = {"slug": slug, "title": title, "questions": [], "completed": False, "score": 0}

    try:
        url = f"{BASE_URL}/lesson/{slug}"
        print(f"\n  [{title}]", flush=True)
        await page.goto(url, wait_until='networkidle', timeout=60000)

        if "/sign-in" in page.url:
            print("    NOT LOGGED IN - Please log in to Chrome", flush=True)
            return result

        await asyncio.sleep(2)

        # Click Quiz tab using JavaScript
        clicked = await page.evaluate("""
            () => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const btn = buttons.find(b => b.innerText.trim() === 'Quiz' || b.innerText.includes('Quiz'));
                if (btn) { btn.click(); return true; }
                return false;
            }
        """)
        if not clicked:
            print("    Quiz tab not found", flush=True)
            return result
        await asyncio.sleep(2)

        # Click Start Quiz button
        await page.evaluate("""
            () => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const btn = buttons.find(b => b.innerText.includes('Start Quiz'));
                if (btn) btn.click();
            }
        """)
        await asyncio.sleep(1.5)

        # Click Start Quiz in modal (there's often a confirmation modal)
        await page.evaluate("""
            () => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const btns = buttons.filter(b => b.innerText.includes('Start Quiz'));
                if (btns.length > 0) btns[btns.length-1].click();
            }
        """)
        await asyncio.sleep(2)

        # Process questions - keep track of last question to detect stuck state
        last_question = ""
        stuck_count = 0

        for q_num in range(30):  # Max 30 questions
            # Extract question and options using correct selectors
            # Options are buttons inside div.space-y-3 within the modal
            quiz_data = await page.evaluate("""
                () => {
                    const text = document.body.innerText;

                    // Check if quiz is complete
                    if (text.includes('Quiz Complete') || text.includes('You passed') || text.includes('passed!')) {
                        return { completed: true };
                    }

                    // Find question number (e.g., "Question 1 of 6")
                    const qMatch = text.match(/Question (\\d+) of (\\d+)/);
                    if (!qMatch) {
                        return { noQuestion: true };
                    }

                    const currentQ = parseInt(qMatch[1]);
                    const totalQ = parseInt(qMatch[2]);

                    // Get question text from the modal
                    // The question is inside a div with specific styling containing the question text
                    const modal = document.querySelector('#modal-root') || document.body;

                    // Find the question - it's in a p tag inside the modal header area
                    let question = '';
                    const questionContainer = modal.querySelector('[data-testid="modal-body"]');
                    if (questionContainer) {
                        const questionP = questionContainer.querySelector('.text-lg.font-semibold p');
                        if (questionP) {
                            question = questionP.innerText.trim();
                        }
                    }

                    // If not found, try alternative parsing
                    if (!question) {
                        const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
                        for (let i = 0; i < lines.length; i++) {
                            if (lines[i].includes('% Complete') && i + 1 < lines.length) {
                                // Skip "Single Choice" or "Multiple Choice" lines
                                for (let j = i + 1; j < Math.min(i + 5, lines.length); j++) {
                                    if (lines[j] !== 'Single Choice' && lines[j] !== 'Multiple Choice' && lines[j].length > 10) {
                                        question = lines[j];
                                        break;
                                    }
                                }
                                break;
                            }
                        }
                    }

                    // Get options - they are buttons inside div.space-y-3
                    const options = [];
                    const optionContainer = modal.querySelector('.space-y-3');
                    if (optionContainer) {
                        const optionButtons = optionContainer.querySelectorAll('button');
                        optionButtons.forEach(btn => {
                            const pTag = btn.querySelector('p');
                            if (pTag) {
                                options.push(pTag.innerText.trim());
                            } else {
                                const text = btn.innerText.trim();
                                if (text && text.length > 3) {
                                    options.push(text);
                                }
                            }
                        });
                    }

                    return {
                        currentQ,
                        totalQ,
                        question,
                        options,
                        completed: false
                    };
                }
            """)

            if quiz_data.get('completed'):
                result["completed"] = True
                break

            if quiz_data.get('noQuestion'):
                # No question found - might be on results page
                text = await page.evaluate("document.body.innerText")
                if "passed" in text.lower() or "complete" in text.lower():
                    result["completed"] = True
                break

            question = quiz_data.get('question', '')
            options = quiz_data.get('options', [])

            # Detect if we're stuck on the same question
            if question == last_question:
                stuck_count += 1
                if stuck_count >= 3:
                    print(f"    Stuck on same question, moving on", flush=True)
                    break
            else:
                stuck_count = 0
                last_question = question

            if not question or len(options) < 2:
                print(f"    Q{q_num+1}: Parse error (q='{question[:30] if question else 'None'}...', opts={len(options)})", flush=True)
                # Take a screenshot for debugging
                await page.screenshot(path=str(DATA_DIR / f"error_{slug}_q{q_num+1}.png"))
                break

            # Get the best answer
            answer_idx = get_answer(question, options)
            answer_text = options[answer_idx] if answer_idx < len(options) else options[0]

            # Click the answer option - options are buttons inside div.space-y-3
            click_result = await page.evaluate("""
                (answerIdx) => {
                    const modal = document.querySelector('#modal-root') || document.body;
                    const optionContainer = modal.querySelector('.space-y-3');
                    if (!optionContainer) return 'no container';

                    const buttons = optionContainer.querySelectorAll('button');
                    if (buttons.length > answerIdx) {
                        buttons[answerIdx].click();
                        return 'clicked';
                    }
                    return 'button not found';
                }
            """, answer_idx)

            await asyncio.sleep(0.5)

            # Click Check Answer button
            await page.evaluate("""
                () => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const btn = buttons.find(b => b.innerText.includes('Check Answer'));
                    if (btn && !btn.disabled) btn.click();
                }
            """)
            await asyncio.sleep(1.5)

            # Check if answer was correct
            result_text = await page.evaluate("document.body.innerText")
            # Look for "Correct!" or check for absence of "Incorrect"
            correct = "Correct!" in result_text or ("Correct" in result_text and "Incorrect" not in result_text)

            result["questions"].append({
                "q": question[:150],
                "a": answer_text[:100],
                "correct": correct
            })
            if correct:
                result["score"] += 1

            status = "✓" if correct else "✗"
            print(f"    Q{q_num+1}: {status} {question[:50]}...", flush=True)

            # Click Next/Continue button
            await page.evaluate("""
                () => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    // Try Next first, then Continue
                    let btn = buttons.find(b => b.innerText.trim() === 'Next' || b.innerText.includes('Next'));
                    if (!btn) {
                        btn = buttons.find(b => b.innerText.includes('Continue'));
                    }
                    if (btn && !btn.disabled) btn.click();
                }
            """)
            await asyncio.sleep(1)

        # Print quiz summary
        total = len(result["questions"])
        if total > 0:
            pct = (result["score"] / total) * 100
            status = "PASSED" if pct >= 70 else f"{pct:.0f}%"
            print(f"    → {result['score']}/{total} ({status})", flush=True)
            if pct >= 70:
                result["completed"] = True

    except Exception as e:
        print(f"    ERROR: {str(e)[:80]}", flush=True)
        import traceback
        traceback.print_exc()

    return result


async def run_all_quizzes():
    """Run all quizzes."""
    all_results = {"timestamp": datetime.now().isoformat(), "weeks": {}}

    async with async_playwright() as p:
        print("Connecting to Chrome...", flush=True)
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        except Exception as e:
            print(f"ERROR: Could not connect to Chrome: {e}", flush=True)
            print("Make sure Chrome is running with: --remote-debugging-port=9222", flush=True)
            return None

        context = browser.contexts[0]
        page = await context.new_page()

        for week_name, quizzes in CURRICULUM.items():
            print(f"\n{'='*60}", flush=True)
            print(f"{week_name}", flush=True)
            print('='*60, flush=True)

            week_results = []
            for slug, title in quizzes:
                result = await solve_single_quiz(page, slug, title)
                week_results.append(result)

                # Save progress after each quiz
                all_results["weeks"][week_name] = week_results
                with open(DATA_DIR / "quiz_progress.json", "w") as f:
                    json.dump(all_results, f, indent=2)

            # Week summary
            completed = sum(1 for r in week_results if r["completed"])
            total_q = sum(len(r["questions"]) for r in week_results)
            total_c = sum(r["score"] for r in week_results)
            pct = (total_c/total_q*100) if total_q > 0 else 0
            print(f"\n  WEEK SUMMARY: {completed}/{len(quizzes)} passed, {total_c}/{total_q} correct ({pct:.0f}%)", flush=True)

        await page.close()

    # Save final results
    with open(DATA_DIR / "all_quiz_results.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n{'='*60}", flush=True)
    print("ALL QUIZZES COMPLETE!", flush=True)
    print('='*60, flush=True)

    # Final summary
    total_passed = sum(sum(1 for r in week if r["completed"]) for week in all_results["weeks"].values())
    total_quizzes = sum(len(week) for week in all_results["weeks"].values())
    print(f"Passed: {total_passed}/{total_quizzes} quizzes", flush=True)

    return all_results


if __name__ == "__main__":
    print("DataExpert Quiz Runner", flush=True)
    print("="*40, flush=True)
    asyncio.run(run_all_quizzes())
