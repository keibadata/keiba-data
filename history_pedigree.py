import json
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

# アクセス間隔
WAIT_SECONDS = 1.0


def clean_text(value):
    if value is None:
        return ""

    return " ".join(
        str(value).replace("\xa0", " ").split()
    )


def load_history_db():
    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        return json.load(f)


def collect_unique_horses(history_db):
    horses = {}

    for race in history_db.get("races", []):
        for result in race.get("results", []):

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

    href = link.get("href", "")

    parts = [
        p for p in href.split("/")
        if p
    ]

    if "horse" in parts:
        try:
            i = parts.index("horse")

            if i + 1 < len(parts):
                value = parts[i + 1]

                if value.isdigit():
                    return value
        except ValueError:
            pass

    return ""


def parse_pedigree(horse_id, horse_name, html):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    table = soup.select_one(
        "table.blood_table"
    )

    if table is None:
        table = soup.find("table")

    if table is None:
        raise RuntimeError(
            "血統テーブルが見つかりません"
        )

    ancestors = []

    rows = table.find_all("tr")

    # netkeibaの5代血統表は
    # 32行 × 世代別セル結合で構成される。
    #
    # tdのrowspanから世代を判定する。
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
        cells = tr.find_all("td")

        for cell_index, td in enumerate(
            cells,
            start=1
        ):
            rowspan_raw = td.get(
                "rowspan",
                "1"
            )

            try:
                rowspan = int(rowspan_raw)
            except (TypeError, ValueError):
                rowspan = 1

            generation = rowspan_generation.get(
                rowspan
            )

            if generation is None:
                continue

            ancestor_name = clean_text(
                td.get_text(" ", strip=True)
            )

            # 生年等が同じセルにある場合を整理
            if ancestor_name:
                ancestor_name = (
                    ancestor_name
                    .replace("\n", " ")
                    .strip()
                )

            if not ancestor_name:
                continue

            link = td.find(
                "a",
                href=True
            )

            ancestor_id = extract_horse_id(
                link
            )

            position_key = (
                row_index,
                cell_index,
                generation,
                ancestor_name,
            )

            if position_key in seen_position:
                continue

            seen_position.add(position_key)

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
        "ancestor_count": len(ancestors),
        "ancestors": ancestors,
    }


def fetch_one_horse(horse):
    horse_id = horse["horse_id"]
    horse_name = horse["horse_name"]

    html = get_pedigree_html(
        horse_id
    )

    return parse_pedigree(
        horse_id,
        horse_name,
        html,
    )


def save_output(data):
    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


def main():
    history_db = load_history_db()

    horses = collect_unique_horses(
        history_db
    )

    print(
        "履歴DB出走頭数:",
        history_db.get(
            "total_horse_count",
            ""
        )
    )

    print(
        "重複除去後の血統取得対象:",
        len(horses)
    )

    completed = []
    errors = []

    total = len(horses)

    for index, horse in enumerate(
        horses,
        start=1
    ):
        horse_id = horse["horse_id"]
        horse_name = horse["horse_name"]

        print(
            f"[{index}/{total}]",
            horse_id,
            horse_name,
        )

        try:
            pedigree = fetch_one_horse(
                horse
            )

            completed.append(
                pedigree
            )

            print(
                "  OK:",
                pedigree["ancestor_count"],
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

        # 途中経過も保存
        output = {
            "updated_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "source": "netkeiba",
            "source_database": INPUT_FILE,
            "target_horse_count": total,
            "collected_horse_count": len(
                completed
            ),
            "error_count": len(errors),
            "errors": errors,
            "horses": completed,
        }

        save_output(output)

        if index < total:
            time.sleep(
                WAIT_SECONDS
            )

    print(
        "========================"
    )

    print(
        "対象:",
        total
    )

    print(
        "取得成功:",
        len(completed)
    )

    print(
        "エラー:",
        len(errors)
    )

    print(
        OUTPUT_FILE,
        "作成完了"
    )


if __name__ == "__main__":
    main()
