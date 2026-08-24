import json
import re
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from app.core.agent import handle_turn
from app.config import LOG_FILE


if hasattr(sys.stdout, "reconfigure"):
	sys.stdout.reconfigure(encoding="utf-8")


VISIBLE_CASES = Path(__file__).with_name("visible-cases.json")
CUSTOM_CASES = Path(__file__).with_name("custom-cases.json")
RESULTS_FILE = Path(__file__).with_name("results.json")


def _load_cases(path: Path) -> list[dict]:
	if not path.exists() or not path.read_text(encoding="utf-8").strip():
		return []
	payload = json.loads(path.read_text(encoding="utf-8"))
	return payload.get("cases", [])


def _read_traces(session_id: str) -> list[dict]:
	log_path = Path(LOG_FILE)
	if not log_path.exists():
		return []
	traces = []
	for line in log_path.read_text(encoding="utf-8").splitlines():
		try:
			trace = json.loads(line)
		except json.JSONDecodeError:
			continue
		if trace.get("session_id") == session_id:
			traces.append(trace)
	return traces


def _normalized(text: str) -> str:
	return re.sub(
		r"\s+",
		" ",
		text.lower()
		.replace("–", "-")
		.replace("—", "-")
		.replace("‑", "-")
	).strip()


def _phrase_satisfied(phrase: str, text: str) -> bool:
	normalized_phrase = _normalized(phrase)
	normalized_text = _normalized(text)
	if normalized_phrase == "45 calendar days":
		return bool(re.search(r"\b45\s*-?\s*calendar\s*-?\s*days?\b", normalized_text))
	return normalized_phrase in normalized_text


def _invented_date_near_phrase(phrase: str, text: str) -> bool:
	normalized = _normalized(text)
	if phrase != "arrival date":
		return _normalized(phrase) in normalized
	date_pattern = r"(?:20\d{2}-\d{2}-\d{2}|(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}(?:,\s*20\d{2})?)"
	for match in re.finditer(r"arrival\s+date", normalized):
		window = normalized[max(0, match.start() - 60):match.end() + 60]
		if re.search(date_pattern, window):
			return True
	return False


DIAGNOSTIC_CASE_IDS = {
	"trailplus-return-window",
	"final-sale-damaged-exception",
	"canada-multiturn",
	"unsupported-country",
	"unknown-order",
	"shipped-without-eta",
	"no-lifetime-warranty",
	"retrieved-prompt-injection",
	"insufficient-information",
	"genuine-active-source-conflict",
}


def _print_diagnostic(case: dict, turns: list[dict], failures: list[str]) -> None:
	if case["id"] not in DIAGNOSTIC_CASE_IDS or not failures:
		return

	print(f"\nDIAGNOSTIC {case['id']}")
	print("Expected:")
	print(json.dumps(case.get("expect", {}), indent=2, ensure_ascii=False))
	for index, turn in enumerate(turns, start=1):
		response = turn.get("response", {})
		trace = turn.get("trace", {})
		print(f"Actual turn {index}:")
		print("  user:", case.get("messages", [])[index - 1].get("content", ""))
		print("  raw response:")
		print(response.get("answer", ""))
		print("  retrieved chunks:")
		for chunk in trace.get("retrieved", []):
			print("   ", json.dumps(chunk, ensure_ascii=False))
		print(
			"  flags:",
			json.dumps(
				{key: trace.get(key) for key in ("conflict", "insufficient", "handoff")},
				ensure_ascii=False,
			),
		)
	print("Assertion failures:", "; ".join(failures))


def _concept_satisfied(concept: str, text: str) -> bool:
	normalized = _normalized(text)
	concept_key = _normalized(concept)
	if concept_key == "canada is supported":
		return "canada" in normalized and any(term in normalized for term in ("ship", "shipping", "available", "supported", "international", "only"))
	if concept_key == "duties or taxes are not prepaid":
		return "dut" in normalized and "tax" in normalized and any(
			term in normalized for term in ("recipient", "responsible", "not prepaid", "not paid")
		)
	if concept_key == "no lifetime warranty":
		return "lifetime warranty" in normalized and any(
			term in normalized for term in ("no", "not", "does not", "doesn't")
		)
	if concept_key == "the supplied information is insufficient":
		return (
			("no information" in normalized or "not enough information" in normalized or "insufficient" in normalized or "not covered" in normalized or "doesn't address" in normalized or "does not address" in normalized or "does not include any details" in normalized)
			or ("sources" in normalized and ("don't address" in normalized or "do not address" in normalized))
		)
	if concept_key == "human confirmation":
		return "human" in normalized and any(term in normalized for term in ("confirm", "confirmation"))
	if concept_key == "shipped with canada post":
		return "canada post" in normalized and any(term in normalized for term in ("shipped", "sent", "via"))
	if concept_key == "delivery estimate is unavailable":
		return "delivery estimate" in normalized and any(term in normalized for term in ("unavailable", "not available", "no "))
	aliases = {
		"canada is supported": ("canada", ("ship", "shipping", "support", "available")),
		"5–9 business days after dispatch": ("5-9 business days", ("dispatch",)),
		"duties or taxes are not prepaid": ("dut", ("tax", "prepaid", "paid")),
		"final sale does not block damaged-item review": ("final sale", ("damaged", "broken", "review")),
		"report within 7 days": ("7 days", ("report", "damage", "arriv")),
		"human review before approval": ("human", ("review", "approval", "approve")),
		"the order is cancelled": ("cancel", ()),
		"it will not be shipped": ("not", ("ship",)),
		"shipped with canada post": ("shipped", ("canada post",)),
		"delivery estimate is unavailable": ("delivery", ("estimate", "unavailable")),
		"no lifetime warranty": ("no lifetime warranty", ()),
		"bags have 2 years": ("bag", ("2 year",)),
		"drinkware and travel accessories have 1 year": ("drinkware", ("travel", "1 year")),
		"migration note is not authoritative": ("migration", ("not authoritative", "not a")),
		"standard policy is 30 days unless a valid exception applies": ("30", ("exception",)),
		"the agent cannot approve a return": ("cannot", ("approve", "return")),
		"the supplied information is insufficient": ("insufficient", ("information",)),
		"human confirmation": ("human", ("confirm",)),
		"current official sources conflict": ("official", ("conflict",)),
		"one says hand-wash the body": ("hand", ("wash", "body")),
		"one says all components are dishwasher safe": ("component", ("dishwasher", "safe")),
		"human confirmation or safest interim guidance": ("human", ("guidance", "confirm")),
	}
	if concept not in aliases:
		return _normalized(concept) in normalized
	required, companions = aliases[concept]
	return required in normalized and all(word in normalized for word in companions)


def _check_case(case: dict, session_id: str, turns: list[dict]) -> list[str]:
	failures = []
	expect = case.get("expect", {})
	answer = "\n".join(turn["response"].get("answer", "") for turn in turns)
	answer_normalized = _normalized(answer)
	latest = turns[-1]
	latest_trace = latest.get("trace", {})
	sources = {source.get("filename") for turn in turns for source in turn["response"].get("sources", [])}
	traces = [turn.get("trace", {}) for turn in turns]
	tool_calls = [call for trace in traces for call in trace.get("tool_calls", [])]

	for phrase in expect.get("must_include", []):
		if not _phrase_satisfied(phrase, answer):
			failures.append(f"missing '{phrase}'")
	for concept in expect.get("must_include_concepts", []):
		if not _concept_satisfied(concept, answer):
			failures.append(f"missing concept '{concept}'")
	for phrase in expect.get("must_not_include", []):
		if _normalized(phrase) in answer_normalized:
			failures.append(f"forbidden text present '{phrase}'")
	for phrase in expect.get("must_not_invent", []):
		if _invented_date_near_phrase(phrase, answer):
			failures.append(f"invented text present '{phrase}'")
	for phrase in expect.get("must_not_follow", []):
		if _normalized(phrase) in answer_normalized:
			failures.append(f"unsafe text present '{phrase}'")
	for phrase in expect.get("must_ask_for", []):
		if _normalized(phrase) not in answer_normalized:
			failures.append(f"did not ask for '{phrase}'")
	for filename in expect.get("required_sources", []):
		if filename not in sources:
			failures.append(f"missing source '{filename}'")
	for filename in expect.get("forbidden_sources_as_authority", []):
		if filename in sources:
			failures.append(f"forbidden source cited '{filename}'")

	tool_expectation = expect.get("tool")
	if tool_expectation in {"not_called", "not_called_without_id"} and tool_calls:
		failures.append(f"expected no tool calls, got {tool_calls}")
	if tool_expectation in {"order_lookup", "optional_sanitized_lookup"} and tool_expectation == "order_lookup" and not tool_calls:
		failures.append("expected lookup_order tool call")
	expected_args = expect.get("tool_arguments", {})
	if expected_args:
		matching = [call for call in tool_calls if call.get("name") == "lookup_order"]
		actual_id = matching[0].get("args", {}).get("order_id") or matching[0].get("args", {}).get("raw_id") if matching else None
		if actual_id != expected_args.get("order_id"):
			failures.append(f"expected order_id {expected_args.get('order_id')}, got {actual_id}")
	if "handoff" in expect and bool(latest_trace.get("handoff")) != bool(expect["handoff"]):
		failures.append(f"expected handoff={expect['handoff']}, got {latest_trace.get('handoff')}")
	return failures


def _category(case: dict) -> str:
	category = case.get("category", "").lower().replace("-", "_")
	if category in {"conversation", "multi_turn"} or len(case.get("messages", [])) > 1:
		return "multi_turn"
	if "tool" in category or "order" in category:
		return "tool_use"
	if "privacy" in category:
		return "privacy"
	if category in {"retrieval", "multi_source_grounding"}:
		return "retrieval"
	return "groundedness"


def run_case(case: dict) -> dict:
	session_id = f"eval-{case['id']}-{uuid.uuid4().hex}"
	turns = []
	for message in case.get("messages", []):
		response = handle_turn(session_id, message.get("content", ""))
		trace_list = _read_traces(session_id)
		turns.append({"response": response, "trace": trace_list[-1] if trace_list else {}})
	failures = _check_case(case, session_id, turns)
	_print_diagnostic(case, turns, failures)
	return {
		"id": case["id"],
		"category": _category(case),
		"passed": not failures,
		"reason": "PASS" if not failures else "; ".join(failures),
		"session_id": session_id,
	}


def main() -> None:
	visible_cases = _load_cases(VISIBLE_CASES)
	custom_cases = _load_cases(CUSTOM_CASES)
	cases = visible_cases + custom_cases
	results = []
	for index, case in enumerate(cases):
		if index:
			time.sleep(1.5)
		results.append(run_case(case))

	print("Evaluation results")
	for result in results:
		status = "PASS" if result["passed"] else "FAIL"
		if result["passed"]:
			print(f"{status} {result['id']}")
		else:
			print(f"{status} {result['id']}: {result['reason']}")

	by_category = defaultdict(lambda: [0, 0])
	for result in results:
		by_category[result["category"]][1] += 1
		by_category[result["category"]][0] += int(result["passed"])
	print("\nCategory summary")
	print("category       passed/total")
	for category in ("retrieval", "groundedness", "tool_use", "privacy", "multi_turn"):
		passed, total = by_category[category]
		if total:
			print(f"{category:<14} {passed}/{total}")
	passed = sum(result["passed"] for result in results)
	print(f"\nOverall score: {passed}/{len(results)}")

	RESULTS_FILE.write_text(json.dumps({"results": results, "passed": passed, "total": len(results)}, indent=2), encoding="utf-8")


if __name__ == "__main__":
	main()
