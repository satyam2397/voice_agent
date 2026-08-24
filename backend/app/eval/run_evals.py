"""
Two-part eval harness:

1. RAGAS -- retrieval quality (context precision/recall, faithfulness) for
   the document_retrieval MCP server.
2. DeepEval -- trigger classifier accuracy against eval_set.jsonl, and
   flash-card quality via an LLM-judge metric (G-Eval).

Run this whenever prompts or models change, to catch quality regressions
before they ship (per the spec's evaluation section). Point the judge model
at the local Ollama model during dev to keep this free; use the hosted
model only for a final pre-demo run.
"""

import json
from pathlib import Path

from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

EVAL_SET_PATH = Path(__file__).parent / "eval_set.jsonl"


def load_eval_set() -> list[dict]:
    with open(EVAL_SET_PATH) as f:
        return [json.loads(line) for line in f]


def run_trigger_classifier_eval():
    from app.orchestrator.trigger_classifier import classify

    cases = load_eval_set()
    correct = 0
    for case in cases:
        decision = classify(case["conversation_snippet"])
        if decision.triggered == case["expected_trigger"]:
            correct += 1
    accuracy = correct / len(cases)
    print(f"Trigger classifier accuracy: {accuracy:.2%} ({correct}/{len(cases)})")
    return accuracy


flash_card_relevance = GEval(
    name="Flash card relevance",
    criteria=(
        "Does the flash card directly and accurately address what the "
        "distributor asked, using only the retrieved fund data -- with no "
        "invented numbers?"
    ),
    evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
)


def run_flash_card_quality_eval(generated_examples: list[dict]):
    """generated_examples: [{"input": ..., "actual_output": ...}, ...]
    produced by running the orchestrator over the eval set."""
    for example in generated_examples:
        test_case = LLMTestCase(input=example["input"], actual_output=example["actual_output"])
        assert_test(test_case, [flash_card_relevance])


if __name__ == "__main__":
    run_trigger_classifier_eval()
    # run_flash_card_quality_eval(...) once the orchestrator can generate real output
