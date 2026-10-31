"""経験・確認待ち項目を、確認済み評価と混同しないための共通処理。"""

import math


EVIDENCE_VERSION = "evidence_v1"

CONDITION_CHANGES = {
    "前走は今回と異なる馬場種別",
    "前走から距離短縮",
    "前走から距離延長",
}


def actual_issues(previous):
    if not isinstance(previous, dict):
        return []

    issues = previous.get("issues", [])

    if not isinstance(issues, list):
        return []

    return [
        issue
        for issue in issues
        if (
            isinstance(issue, str)
            and issue not in CONDITION_CHANGES
        )
    ]


def confirmed_evidence(
    records,
    target_race_id,
    *,
    kind=None,
    issues=None,
):
    if not target_race_id or not isinstance(records, list):
        return []

    accepted = []
    seen = set()

    for record in records:
        if not isinstance(record, dict):
            continue

        if (
            record.get("status") != "confirmed"
            or str(record.get("target_race_id", ""))
            != str(target_race_id)
            or not str(record.get("source", "")).strip()
            or not str(record.get("fact", "")).strip()
        ):
            continue

        if kind is not None and record.get("kind") != kind:
            continue

        if issues is not None and record.get("issue") not in issues:
            continue

        # 同じ課題への複数記録を、克服件数に重複計上しない。
        if issues is not None:
            key = record.get("issue")
        else:
            key = (
                record.get("source"),
                record.get("fact"),
            )

        if key in seen:
            continue

        seen.add(key)
        accepted.append(dict(record))

    return accepted


def assessment_score(
    assessment,
    target_race_id,
    kind,
):
    """独立した確認済み評価だけを受け入れる。"""

    if not isinstance(assessment, dict):
        return None

    if (
        assessment.get("version") != EVIDENCE_VERSION
        or str(assessment.get("target_race_id", ""))
        != str(target_race_id)
        or assessment.get("status") != "confirmed"
    ):
        return None

    evidence = confirmed_evidence(
        assessment.get("evidence"),
        target_race_id,
        kind=kind,
    )

    if not evidence:
        return None

    value = assessment.get("score")

    if isinstance(value, bool):
        return None

    try:
        value = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(value):
        return None

    if not 0 <= value <= 100:
        return None

    return round(value, 1)


def resolution_evidence(
    previous,
    target_race_id,
):
    if not isinstance(previous, dict):
        return []

    return confirmed_evidence(
        previous.get("verified_overcoming_evidence"),
        target_race_id,
        kind="issue_resolution",
        issues=actual_issues(previous),
    )
