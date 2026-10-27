"""保存済みsnapshotだけを読み、アプリ用の軽量履歴indexを生成する。"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
JST = timezone(timedelta(hours=9))
INDEX_SCHEMA_VERSION = 1
SUPPORTED_SNAPSHOT_SCHEMAS = (1, 2)


def text(value):
    return "" if value is None else str(value).strip()


def parse_datetime(value, field):
    value = text(value)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field}: invalid datetime {value!r}") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{field}: timezone is required")
    return result.astimezone(JST)


def load_snapshot(path, root):
    relative = path.relative_to(root)
    if len(relative.parts) != 3:
        raise ValueError("expected race_date/race_id/snapshot_id.json")
    path.resolve().relative_to(root.resolve())
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("snapshot must be an object")
    schema = data.get("schema_version")
    if type(schema) is not int or schema not in SUPPORTED_SNAPSHOT_SCHEMAS:
        raise ValueError(f"unsupported snapshot schema: {schema!r}")
    if data.get("snapshot_kind") != "prediction":
        raise ValueError("snapshot_kind must be prediction")
    race = data.get("race")
    analysis = data.get("analysis")
    if not isinstance(race, dict) or not isinstance(analysis, dict):
        raise ValueError("race and analysis must be objects")
    race_id = text(race.get("race_id"))
    if not re.fullmatch(r"\d{12}", race_id):
        raise ValueError("race_id must contain 12 digits")
    if relative.parts[1] != race_id or text(analysis.get("race_id")) != race_id:
        raise ValueError("race_id mismatch between path/race/analysis")
    race_number = int(race_id[-2:])
    if not 1 <= race_number <= 12:
        raise ValueError("race number must be 1-12")
    race_date = text(race.get("race_date"))
    if race_date:
        if date.fromisoformat(race_date).isoformat() != race_date:
            raise ValueError("race_date must be YYYY-MM-DD")
    if relative.parts[0] != (race_date or "date_unknown"):
        raise ValueError("race_date mismatch between path and race")
    snapshot_id = text(data.get("snapshot_id"))
    if not snapshot_id or path.stem != snapshot_id:
        raise ValueError("snapshot_id mismatch with filename")
    saved_at = parse_datetime(data.get("prediction_saved_at"), "prediction_saved_at")
    source_at = text(data.get("source_final_analysis_updated_at"))
    if source_at:
        source_at = parse_datetime(source_at, "source_final_analysis_updated_at").isoformat()
    ranking = analysis.get("ranking")
    if not isinstance(ranking, list) or not ranking:
        raise ValueError("analysis.ranking must be a nonempty list")
    if not all(isinstance(horse, dict) for horse in ranking):
        raise ValueError("every ranking entry must be an object")
    summary = analysis.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("analysis.summary must be an object")
    for field, count in [
        ("race.horse_count", race.get("horse_count")),
        ("analysis.summary.runner_count", summary.get("runner_count")),
    ]:
        if type(count) is not int or count != len(ranking):
            raise ValueError(f"{field}: expected {len(ranking)}, got {count!r}")
    timing = data.get("timing")
    if not isinstance(timing, dict):
        raise ValueError("timing must be an object")
    eligible = timing.get("evaluation_eligible")
    if eligible is not None and type(eligible) is not bool:
        raise ValueError("evaluation_eligible must be true/false/null")
    # 古い版にない解析版番号は推測せずnullのまま残す。
    metadata = {
        "snapshot_id": snapshot_id,
        "snapshot_path": f"prediction_snapshots/{relative.as_posix()}",
        "schema_version": schema,
        "prediction_saved_at": saved_at.isoformat(),
        "source_final_analysis_updated_at": source_at or None,
        "analysis_version": text(analysis.get("analysis_version")) or None,
        "analysis_mode": text(data.get("analysis_mode"))
        or text(analysis.get("analysis_mode")) or "normal",
        "timing_status": text(timing.get("status")) or None,
        "evaluation_eligible": eligible,
        "horse_count": len(ranking),
    }
    digest = hashlib.sha256(
        json.dumps(analysis, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    ).hexdigest()
    return {
        "race": race,
        "race_id": race_id,
        "race_number": race_number,
        "saved_at": saved_at,
        "metadata": metadata,
        # 更新日時が不明な記録同士は同一解析と決めつけない。
        "group_key": (race_id, source_at or snapshot_id, digest),
    }


def build_index(root):
    if not root.is_dir():
        raise ValueError(f"snapshot directory is missing: {root}")
    paths = sorted(root.rglob("*.json"))
    if not paths:
        raise ValueError("no snapshots found; existing index will not be replaced")
    records = []
    seen_ids = set()
    for path in paths:
        try:
            record = load_snapshot(path, root)
            snapshot_id = record["metadata"]["snapshot_id"]
            if snapshot_id in seen_ids:
                raise ValueError(f"duplicate snapshot_id: {snapshot_id}")
            seen_ids.add(snapshot_id)
            records.append(record)
        except Exception as exc:
            raise ValueError(f"{path}: {exc}") from exc
    grouped = {}
    for record in records:
        grouped.setdefault(record["group_key"], []).append(record)
    races = {}
    for variants in grouped.values():
        # 同一解析の形式違いは新しいschemaを代表にする。元の参照は全件保持。
        variants.sort(
            key=lambda row: (row["metadata"]["schema_version"], row["saved_at"],
                             row["metadata"]["snapshot_id"]),
            reverse=True,
        )
        preferred = variants[0]
        version = dict(preferred["metadata"])
        version["snapshot_file_count"] = len(variants)
        version["schema_variants"] = [dict(row["metadata"]) for row in variants]
        race_id = preferred["race_id"]
        entry = races.setdefault(race_id, {"records": [], "versions": []})
        entry["records"].extend(variants)
        entry["versions"].append(version)
    result = []
    for race_id, entry in races.items():
        versions = entry["versions"]
        versions.sort(
            key=lambda row: (parse_datetime(row["prediction_saved_at"], "prediction_saved_at"),
                             row["snapshot_id"]),
            reverse=True,
        )
        latest = versions[0]
        record = next(row for row in entry["records"]
                      if row["metadata"]["snapshot_id"] == latest["snapshot_id"])
        race = record["race"]
        race_name = text(race.get("race_name"))
        race_class = text(race.get("race_class"))
        result.append({
            "race_id": race_id,
            "race_date": text(race.get("race_date")) or None,
            "track": text(race.get("track")) or None,
            "race_number": record["race_number"],
            "race_name": race_name or None,
            "race_class": race_class or None,
            "display_name": race_name or race_class or "レース名不明",
            "display_name_source": "race_name" if race_name else (
                "race_class" if race_class else "unknown"),
            "analysis_mode": latest["analysis_mode"],
            "latest_snapshot_id": latest["snapshot_id"],
            "latest_snapshot_path": latest["snapshot_path"],
            "latest_prediction_saved_at": latest["prediction_saved_at"],
            "latest_analysis_version": latest["analysis_version"],
            "version_count": len(versions),
            "snapshot_file_count": len(entry["records"]),
            "versions": versions,
        })
    # 開催日の新しい順。同日は競馬場、Rの順。日付不明は末尾。
    result.sort(key=lambda row: (row["track"] or "", row["race_number"], row["race_id"]))
    result.sort(key=lambda row: row["race_date"] or "", reverse=True)
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "index_kind": "prediction_history",
        "generated_at": datetime.now(JST).isoformat(),
        "summary": {
            "race_count": len(result),
            "version_count": len(grouped),
            "snapshot_file_count": len(records),
            "schema_duplicate_file_count": len(records) - len(grouped),
        },
        "races": result,
    }


def write_index(output, index):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent,
            prefix=f".{output.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(index, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-root", type=Path,
                        default=BASE_DIR / "prediction_snapshots")
    parser.add_argument("--output", type=Path,
                        default=BASE_DIR / "prediction_history_index.json")
    args = parser.parse_args()
    root = args.snapshot_root.resolve()
    output = args.output.resolve()
    # snapshot自身を出力先に指定しても上書きしない。
    if output == root or root in output.parents:
        raise ValueError("output must be outside the snapshot directory")
    index = build_index(root)
    write_index(output, index)
    print("PREDICTION HISTORY INDEX OK")
    for key, value in index["summary"].items():
        print(f"{key}: {value}")
    print(f"output: {output}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"PREDICTION HISTORY INDEX FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
