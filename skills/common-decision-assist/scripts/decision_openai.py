"""Translate the conservative CLI contract to and from OpenAI Decisions."""

import json

from decision_config import DecisionError


def _json_evidence(state):
    # Native JSON has tighter limits than the overall transport envelope.
    encoded = json.dumps(state, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(encoded) > 256 * 1024:
        raise DecisionError("INPUT_ERROR", "OpenAI structured state exceeds 256 KiB; reduce evidence.", 3)
    count, stack = 0, [(state, 0)]
    while stack:
        value, depth = stack.pop()
        count += 1
        if count > 10000:
            raise DecisionError("INPUT_ERROR", "OpenAI structured state exceeds 10,000 values.", 3)
        if isinstance(value, (dict, list)):
            depth += 1
            if depth > 32:
                raise DecisionError("INPUT_ERROR", "OpenAI structured state exceeds 32 container levels.", 3)
            children = value.values() if isinstance(value, dict) else value
            stack.extend((child, depth) for child in children)
    return [{"role": "user", "content": [{"type": "input_json", "data": state}]}]


def build_request(request):
    state = request["state"]
    if isinstance(state, str):
        evidence = state
    elif isinstance(state, dict) or all(isinstance(item, dict) for item in state):
        evidence = _json_evidence(state)
    else:
        # Mixed/scalar arrays remain text evidence, never native conversation items.
        evidence = json.dumps(state, ensure_ascii=False, allow_nan=False)
    questions = []
    for qid, question in request["questions"].items():
        item = {"name": qid, "type": question["type"], "instructions": question["instructions"]}
        if item["type"] == "choice":
            item["choices"] = [{"value": key, "description": description} for key, description in question["criteria"].items()]
        elif item["type"] == "score":
            item["levels"] = [{"label": str(index), "description": description} for index, description in enumerate(question["criteria"])]
        questions.append(item)
    return {"input": evidence, "questions": questions}


def _distribution(items, question):
    if not isinstance(items, list):
        raise DecisionError("RESPONSE_ERROR", "OpenAI probabilities must be an array.", 6)
    result = {}
    for item in items:
        if not isinstance(item, dict) or "probability" not in item:
            raise DecisionError("RESPONSE_ERROR", "OpenAI probability entry is invalid.", 6)
        value = item.get("value")
        if question["type"] == "score":
            if (not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < len(question["criteria"])
                    or item.get("label") != str(value)):
                raise DecisionError("RESPONSE_ERROR", "OpenAI score levels do not match the submitted rubric.", 6)
            value = str(value)
        elif not isinstance(value, str):
            raise DecisionError("RESPONSE_ERROR", "This adapter only supports string choice IDs.", 6)
        if value in result:
            raise DecisionError("RESPONSE_ERROR", "OpenAI returned duplicate probability values.", 6)
        result[value] = item["probability"]
    return result


def _usage(value):
    if not isinstance(value, dict):
        raise DecisionError("RESPONSE_ERROR", "OpenAI usage must be an object.", 6)
    result = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        count = value.get(key)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise DecisionError("RESPONSE_ERROR", "OpenAI token counts must be nonnegative integers.", 6)
        result[key] = count
    for key, fields in (("input_tokens_details", ("cached_tokens", "cache_write_tokens")),
                        ("output_tokens_details", ("reasoning_tokens",))):
        if key not in value:
            continue
        details = value[key]
        if not isinstance(details, dict):
            raise DecisionError("RESPONSE_ERROR", "OpenAI token details must be an object.", 6)
        result[key] = {}
        for field in fields:
            count = details.get(field)
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise DecisionError("RESPONSE_ERROR", "OpenAI token details must be nonnegative integers.", 6)
            result[key][field] = count
    return result


def normalize_response(body, questions):
    if not isinstance(body, dict) or not isinstance(body.get("answers"), list):
        raise DecisionError("RESPONSE_ERROR", "OpenAI answers must be an array.", 6)
    answers = {}
    for answer in body["answers"]:
        if not isinstance(answer, dict):
            raise DecisionError("RESPONSE_ERROR", "OpenAI answer must be an object.", 6)
        qid = answer.get("name")
        if not isinstance(qid, str) or qid not in questions or qid in answers:
            raise DecisionError("RESPONSE_ERROR", "OpenAI answer names must match submitted question IDs exactly once.", 6)
        question = questions[qid]
        kind = answer.get("type")
        if kind == "refusal":
            answers[qid] = {"type": "refusal", "requested_type": question["type"]}
            continue
        if kind != question["type"]:
            raise DecisionError("RESPONSE_ERROR", "OpenAI answer type differs from the submitted question.", 6)
        item = {"type": kind}
        if kind == "predicate":
            item["probability"] = answer.get("probability")
        else:
            field = "choice" if kind == "choice" else "score"
            item.update({field: answer.get(field), "confidence": answer.get("confidence"),
                         "probabilities": _distribution(answer.get("probabilities"), question)})
            if kind == "score":
                # Legend is the caller's original rubric, not an invented model explanation.
                item["legend"] = {str(index): description for index, description in enumerate(question["criteria"])}
        answers[qid] = item
    if set(answers) != set(questions):
        raise DecisionError("RESPONSE_ERROR", "OpenAI did not answer every submitted question.", 6)
    result = {"answers": answers}
    if isinstance(body.get("model"), str):
        result["model"] = body["model"]
    if "usage" in body:
        result["usage"] = _usage(body["usage"])
    return result
