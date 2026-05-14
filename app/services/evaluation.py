from __future__ import annotations
import json
import random
from typing import Any

from app.db import get_db


def _load_responses(survey_id: int, class_name: str | None) -> list[dict[str, Any]]:
    conn = get_db()
    try:
        if class_name:
            rows = conn.execute(
                "SELECT payload_json FROM responses WHERE survey_id = ? AND class_name = ?",
                (survey_id, class_name),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT payload_json FROM responses WHERE survey_id = ?",
                (survey_id,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]
    finally:
        conn.close()


def aggregate_question(
    responses: list[dict[str, Any]],
    question_id: str,
    options: list[dict[str, str]],
) -> dict[str, Any]:
    counts: dict[str, int] = {opt["value"]: 0 for opt in options}
    answered = 0
    for resp in responses:
        val = resp.get(question_id)
        if val and val in counts:
            counts[val] += 1
            answered += 1

    percents: dict[str, float] = {}
    for val, cnt in counts.items():
        percents[val] = round(cnt / answered * 100, 1) if answered > 0 else 0.0

    return {
        "counts": counts,
        "percents": percents,
        "total": answered,
        "options": options,
    }


def collect_freitext(
    responses: list[dict[str, Any]],
    question_id: str,
) -> list[str]:
    texts = [resp[question_id] for resp in responses if resp.get(question_id)]
    random.shuffle(texts)
    return texts


def evaluate_survey(
    survey_id: int,
    questionnaire: dict[str, Any],
    class_name: str | None,
) -> dict[str, Any]:
    responses = _load_responses(survey_id, class_name)
    scale_options = questionnaire.get("scale", {}).get("options", [])

    result: dict[str, Any] = {
        "total_responses": len(responses),
        "sections": [],
    }

    for section in questionnaire.get("sections", []):
        sec_result = {
            "id": section["id"],
            "title": section["title"],
            "questions": [],
        }
        for q in section.get("questions", []):
            qid = q["id"]
            qtype = q["type"]

            if qtype in ("scale", "conditional"):
                opts = q.get("options", scale_options)
                sec_result["questions"].append({
                    "id": qid,
                    "type": qtype,
                    "text": q["text"],
                    "stats": aggregate_question(responses, qid, opts),
                    "show_if": q.get("show_if"),
                })
            elif qtype == "single_choice":
                opts = q.get("options", [])
                sec_result["questions"].append({
                    "id": qid,
                    "type": qtype,
                    "text": q["text"],
                    "stats": aggregate_question(responses, qid, opts),
                })
            elif qtype == "text":
                sec_result["questions"].append({
                    "id": qid,
                    "type": qtype,
                    "text": q["text"],
                    "freitexte": collect_freitext(responses, qid),
                })

        result["sections"].append(sec_result)

    return result
