"""Describe implemented adapter capabilities without credentials or networking."""


def get_capabilities(protocol):
    probability_type = "predicate" if protocol == "openai" else "noul"
    return {
        "question_types": ["choice", "score", probability_type],
        "max_questions": 400 if protocol == "openai" else 64,
        "max_choice_options": 64,
        "score_levels": {"min": 2, "max": 10},
        "max_request_bytes": 1048576,
        "evidence": ["text", "structured_json"],
        "images": False, "native_conversation": False,
        "scenarios": {
            "classification": {
                "type": "choice", "parameters": ["state", "questions.<id>.instructions", "questions.<id>.criteria"],
                "collect": ["evidence", "candidate meanings", "observable selection rules", "UNKNOWN fallback"],
            },
            "candidate_comparison": {
                "type": "choice", "parameters": ["state", "questions.<id>.instructions", "questions.<id>.criteria"],
                "collect": ["candidate facts and sources", "hard constraints", "relevant user preferences", "unknowns"],
            },
            "rubric_scoring": {
                "type": "score", "parameters": ["state", "questions.<id>.instructions", "questions.<id>.criteria"],
                "collect": ["evidence", "2-10 ordered levels", "observable criteria for adjacent levels"],
            },
            "proposition_probability": {
                "type": probability_type, "parameters": ["state", "questions.<id>.instructions"],
                "optional_parameters": ["questions.<id>.thresholds.false_at_most", "questions.<id>.thresholds.true_at_least"],
                "collect": ["one explicit proposition", "object and time scope", "supporting and opposing evidence", "unknowns", "application thresholds if routing"],
            },
        },
        "unsupported": ["image input", "native messages/tool-call input", "audio/files", "field extraction", "generated explanations", "automatic actions", "dependent questions in one request", "boolean choice values", "explicit prompt cache controls"],
    }
