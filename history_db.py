import json
import subprocess
import sys
import time
from datetime import datetime, timezone


RACE_LIST_FILE = "history_races.json"
OUTPUT_FILE = "history_db.json"
TEMP_FILE = "history.json"

# netkeibaへの連続アクセスを抑える
WAIT_SECONDS = 2


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


def main():

    race_list = load_json(RACE_LIST_FILE)

    races = race_list.get("races", [])

    if not races:
        raise RuntimeError(
            "history_races.json に races がありません"
        )

    print("対象レース数:", len(races))

    collected = []
    errors = []

    for index, race in enumerate(races, start=1):

        race_id = str(
            race.get("race_id", "")
        ).strip()

        if not race_id:
            continue

        print("")
        print(
            f"[{index}/{len(races)}] 取得開始:",
            race_id
        )

        try:
            # 動作確認済みhistory.pyを実行
            subprocess.run(
                [
                    sys.executable,
                    "history.py",
                    race_id,
                ],
                check=True,
            )

            result = load_json(TEMP_FILE)

            # race_idの取り違え防止
            if str(result.get("race_id", "")) != race_id:
                raise RuntimeError(
                    "history.json のrace_idが一致しません"
                )

            result_count = len(
                result.get("results", [])
            )

            print(
                "取得成功:",
                race_id,
                "出走馬",
                result_count,
                "頭"
            )

            collected.append(result)

        except Exception as e:

            print(
                "取得失敗:",
                race_id,
                str(e)
            )

            errors.append({
                "race_id": race_id,
                "error": str(e),
            })

        # 最後のレース以外は少し待つ
        if index < len(races):
            time.sleep(WAIT_SECONDS)

    total_horses = sum(
        len(race.get("results", []))
        for race in collected
    )

    database = {
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "source": "netkeiba",

        "condition": race_list.get(
            "condition",
            {}
        ),

        "requested_race_count": len(races),

        "collected_race_count": len(collected),

        "total_horse_count": total_horses,

        "error_count": len(errors),

        "errors": errors,

        "races": collected,
    }

    save_json(
        OUTPUT_FILE,
        database
    )

    print("")
    print("==============================")
    print("history_db.json 作成完了")
    print("対象レース:", len(races))
    print("取得成功:", len(collected))
    print("取得失敗:", len(errors))
    print("全出走馬:", total_horses)
    print("==============================")

    # 全レース失敗だけはAction自体を失敗させる
    if not collected:
        raise RuntimeError(
            "全レースの取得に失敗しました"
        )


if __name__ == "__main__":
    main()
