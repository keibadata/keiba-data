import json
import os
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup


INPUT_FILE = "history_db.json"
OUTPUT_FILE = "history_pedigree.json"

BASE_URL = "https://db.netkeiba.com/horse/ped/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}

WAIT_SECONDS = 1.0


def clean_text(value):
    if value is None:
        return ""

    return " ".join(
        str(value).replace("\xa0", " ").split()
    )


def load_json(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else {}

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


def collect_unique_horses(history_db):
    horses = {}

    for race in history_db.get("races", []):
        if not isinstance(race, dict):
            continue

        for result in race.get("results", []):
            if not isinstance(result, dict):
                continue

            horse_id = clean_text(
                result.get("horse_id")
            )

            horse_name = clean_text(
                result.get("horse_name")
            )

            if not horse_id:
                continue

            if horse_id not in horses:
                horses[horse_id] = {
                    "horse_id": horse_id,
                    "horse_name": horse_name,
                }

    return list(horses.values())


def get_existing_pedigrees():
    data = load_json(
        OUTPUT_FILE,
        {}
    )

    horses = data.get(
        "horses",
        []
    )

    if not isinstance(horses, list):
        horses = []

    result = {}

    for horse in horses:
        if not isinstance(horse, dict):
            continue

        horse_id = clean_text(
            horse.get("horse_id")
        )

        ancestors = horse.get(
            "ancestors",
            []
        )

        if (
            horse_id
            and isinstance(ancestors, list)
            and len(ancestors) > 0
        ):
            result[horse_id] = horse

    return result


def get_pedigree_html(horse_id):
    url = BASE_URL + horse_id + "/"

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()
    response.encoding = response.apparent_encoding

    return response.text


def extract_horse_id(link):
    if not link:
        return ""

    href = link.get(
        "href",
        ""
    )

    parts = [
        part
        for part in href.split("/")
        if part
    ]

    if "horse" not in parts:
        return ""

    try:
        index = parts.index(
            "horse"
        )

        if index + 1 >= len(parts):
            return ""

        value = parts[index + 1]

        if value.isdigit():
            return value

    except ValueError:
        pass

    return ""


def parse_pedigree(
    horse_id,
    horse_name,
    html
):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    table = soup.select_one(
        "table.blood_table"
    )

    if table is None:
        table = soup.find(
            "table"
        )

    if table is None:
        raise RuntimeError(
            "血統テーブルが見つかりません"
        )

    ancestors = []

    rows = table.find_all(
        "tr"
    )

    rowspan_generation = {
        16: 1,
        8: 2,
        4: 3,
        2: 4,
        1: 5,
    }

    seen_position = set()

    for row_index, tr in enumerate(
        rows,
        start=1
    ):
        cells = tr.find_all(
            "td"
        )

        for cell_index, td in enumerate(
            cells,
            start=1
        ):
            rowspan_raw = td.get(
                "rowspan",
                "1"
            )

            try:
                rowspan = int(
                    rowspan_raw
                )
            except (
                TypeError,
                ValueError
            ):
                rowspan = 1

            generation = (
                rowspan_generation.get(
                    rowspan
                )
            )

            if generation is None:
                continue

            ancestor_name = clean_text(
                td.get_text(
                    " ",
                    strip=True
                )
            )

            if not ancestor_name:
                continue

            link = td.find(
                "a",
                href=True
            )

            ancestor_id = (
                extract_horse_id(
                    link
                )
            )

            position_key = (
                row_index,
                cell_index,
                generation,
                ancestor_name,
            )

            if position_key in seen_position:
                continue

            seen_position.add(
                position_key
            )

            ancestors.append({
                "generation": generation,
                "ancestor_name": ancestor_name,
                "ancestor_id": ancestor_id,
                "row": row_index,
                "cell": cell_index,
            })

    if not ancestors:
        raise RuntimeError(
            "祖先データを取得できませんでした"
        )

    return {
        "horse_id": horse_id,
        "horse_name": horse_name,
        "ancestor_count": len(
            ancestors
        ),
        "ancestors": ancestors,
    }


def fetch_one_horse(horse):
    horse_id = horse[
        "horse_id"
    ]

    horse_name = horse[
        "horse_name"
    ]

    html = get_pedigree_html(
        horse_id
    )

    return parse_pedigree(
        horse_id,
        horse_name,
        html,
    )


def build_output(
    pedigree_map,
    target_count,
    new_count,
    reused_count,
    errors
):
    horses = list(
        pedigree_map.values()
    )

    horses.sort(
        key=lambda horse: str(
            horse.get(
                "horse_id",
                ""
            )
        )
    )

    return {
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "source": "netkeiba",
        "source_database": INPUT_FILE,
        "database_type": (
            "incremental_accumulated"
        ),

        "target_horse_count": (
            target_count
        ),

        "database_horse_count": len(
            horses
        ),

        "latest_update": {
            "newly_collected_count": (
                new_count
            ),
            "existing_reused_count": (
                reused_count
            ),
            "error_count": len(
                errors
            ),
            "errors": errors,
        },

        # 既存コードとの互換性維持
        "collected_horse_count": len(
            horses
        ),
        "error_count": len(
            errors
        ),
        "errors": errors,

        "horses": horses,
    }


def main():
    history_db = load_json(
        INPUT_FILE,
        {}
    )

    target_horses = (
        collect_unique_horses(
            history_db
        )
    )

    if not target_horses:
        raise RuntimeError(
            "history_db.json に血統取得対象馬がいません"
        )

    pedigree_map = (
        get_existing_pedigrees()
    )

    existing_before = len(
        pedigree_map
    )

    pending = []

    for horse in target_horses:
        horse_id = horse[
            "horse_id"
        ]

        if horse_id not in pedigree_map:
            pending.append(
                horse
            )

    reused_count = (
        len(target_horses)
        - len(pending)
    )

    print("========================")
    print("履歴血統DB 増分更新")
    print(
        "履歴DBユニーク馬:",
        len(target_horses)
    )
    print(
        "既存血統DB:",
        existing_before
    )
    print(
        "既存再利用:",
        reused_count
    )
    print(
        "新規取得対象:",
        len(pending)
    )
    print("========================")

    errors = []
    new_count = 0

    for index, horse in enumerate(
        pending,
        start=1
    ):
        horse_id = horse[
            "horse_id"
        ]

        horse_name = horse[
            "horse_name"
        ]

        print(
            f"[{index}/{len(pending)}]",
            horse_id,
            horse_name,
        )

        try:
            pedigree = (
                fetch_one_horse(
                    horse
                )
            )

            pedigree_map[
                horse_id
            ] = pedigree

            new_count += 1

            print(
                "  OK:",
                pedigree[
                    "ancestor_count"
                ],
                "祖先"
            )

        except Exception as e:
            print(
                "  ERROR:",
                str(e)
            )

            errors.append({
                "horse_id": horse_id,
                "horse_name": horse_name,
                "error": str(e),
            })

        # 途中でもDBを保存
        output = build_output(
            pedigree_map,
            len(target_horses),
            new_count,
            reused_count,
            errors,
        )

        save_json(
            OUTPUT_FILE,
            output
        )

        if index < len(pending):
            time.sleep(
                WAIT_SECONDS
            )

    # pending=0でも必ず保存
    output = build_output(
        pedigree_map,
        len(target_horses),
        new_count,
        reused_count,
        errors,
    )

    save_json(
        OUTPUT_FILE,
        output
    )

    missing_ids = [
        horse["horse_id"]
        for horse in target_horses
        if horse["horse_id"]
        not in pedigree_map
    ]

    print("========================")
    print(
        "最終血統DB:",
        len(pedigree_map)
    )
    print(
        "今回新規取得:",
        new_count
    )
    print(
        "取得失敗:",
        len(errors)
    )
    print(
        "未取得馬:",
        len(missing_ids)
    )
    print(
        OUTPUT_FILE,
        "更新完了"
    )
    print("========================")

    if missing_ids:
        raise RuntimeError(
            "履歴DB内に血統未取得馬があります: "
            + str(len(missing_ids))
            + "頭"
        )


if __name__ == "__main__":
    main()
