import json
import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

INPUT_FILE = "race.json"
OUTPUT_FILE = "pedigree.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
        "Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

JST = timezone(timedelta(hours=9))


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def get_soup(url):
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    return BeautifulSoup(response.text, "html.parser")


def horse_url(horse_id):
    return f"https://db.netkeiba.com/horse/{horse_id}/"


def pedigree_url(horse_id):
    return f"https://db.netkeiba.com/horse/ped/{horse_id}/"


def extract_ancestor_id(link):
    if not link:
        return ""

    href = link.get("href", "")

    match = re.search(r"/horse/(\d+)/?", href)
    if match:
        return match.group(1)

    return ""


def extract_name(cell):
    link = cell.find("a")

    if link:
        name = clean_text(link.get_text(" ", strip=True))
    else:
        name = clean_text(cell.get_text(" ", strip=True))

    # 生年・毛色など、名前以外の付加情報を落とす
    name = re.sub(r"\s+\d{4}.*$", "", name)

    return name


def find_pedigree_table(soup):
    candidates = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")

        if not rows:
            continue

        cells = table.find_all(["td", "th"])

        # 5代血統表はセル数が多いので候補を絞る
        if len(cells) >= 20:
            candidates.append(table)

    if not candidates:
        return None

    # 最もセル数が多い表を採用
    return max(
        candidates,
        key=lambda table: len(table.find_all(["td", "th"]))
    )


def parse_pedigree(horse_id, horse_name):
    url = pedigree_url(horse_id)
    soup = get_soup(url)

    table = find_pedigree_table(soup)

    if table is None:
        raise RuntimeError(
            f"{horse_name}: 血統表を取得できませんでした"
        )

    ancestors = []
    seen_positions = set()

    rows = table.find_all("tr")

    for row_index, row in enumerate(rows, start=1):
        cells = row.find_all(["td", "th"])

        for cell_index, cell in enumerate(cells, start=1):
            name = extract_name(cell)

            if not name:
                continue

            # 不要な見出し等を除外
            if name in {
                "父",
                "母",
                "父父",
                "父母",
                "母父",
                "母母",
                "血統",
                "5代血統表",
            }:
                continue

            link = cell.find("a")
            ancestor_id = extract_ancestor_id(link)

            rowspan_raw = cell.get("rowspan", "1")

            try:
                rowspan = int(rowspan_raw)
            except ValueError:
                rowspan = 1

            # netkeibaの5代血統表ではrowspanから世代を推定できる。
            # 16→1代、8→2代、4→3代、2→4代、1→5代
            generation_map = {
                16: 1,
                8: 2,
                4: 3,
                2: 4,
                1: 5,
            }

            generation = generation_map.get(rowspan)

            if generation is None:
                continue

            position_key = (
                row_index,
                cell_index,
                generation,
                name,
                ancestor_id,
            )

            if position_key in seen_positions:
                continue

            seen_positions.add(position_key)

            ancestors.append({
                "generation": generation,
                "ancestor_name": name,
                "ancestor_id": ancestor_id,
                "row": row_index,
                "cell": cell_index,
            })

    if not ancestors:
        raise RuntimeError(
            f"{horse_name}: 祖先データが0件でした"
        )

    return {
        "horse_id": horse_id,
        "horse_name": horse_name,
        "source_url": url,
        "ancestor_count": len(ancestors),
        "ancestors": ancestors,
    }


def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        race = json.load(f)

    horses = race.get("horses", [])

    if not horses:
        raise RuntimeError("race.json に出走馬がありません")

    result = {
        "race_id": race.get("race_id", ""),
        "updated_at": datetime.now(JST).isoformat(),
        "source": "netkeiba",
        "horse_count": len(horses),
        "success_count": 0,
        "error_count": 0,
        "horses": [],
        "errors": [],
    }

    for index, horse in enumerate(horses, start=1):
        horse_id = clean_text(horse.get("horse_id", ""))
        horse_name = clean_text(horse.get("horse_name", ""))

        print(
            f"[{index}/{len(horses)}] "
            f"{horse_name} ({horse_id})"
        )

        if not horse_id:
            result["errors"].append({
                "horse_name": horse_name,
                "error": "horse_id がありません",
            })
            result["error_count"] += 1
            continue

        try:
            pedigree = parse_pedigree(
                horse_id,
                horse_name
            )

            result["horses"].append(pedigree)
            result["success_count"] += 1

            print(
                f"  OK: "
                f"{pedigree['ancestor_count']} ancestors"
            )

        except Exception as exc:
            result["errors"].append({
                "horse_id": horse_id,
                "horse_name": horse_name,
                "error": str(exc),
            })

            result["error_count"] += 1
            print(f"  ERROR: {exc}")

        # サイトへの連続アクセスを抑える
        time.sleep(1.2)

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"\n完了: "
        f"{result['success_count']}/{len(horses)}頭成功"
    )

    if result["success_count"] == 0:
        raise RuntimeError(
            "全馬の5代血統取得に失敗しました"
        )


if __name__ == "__main__":
    main()
