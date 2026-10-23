import json
import os
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

REQUEST_INTERVAL = 1.2
TIMEOUT = 20


def clean_text(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "")
    ).strip()


def load_json(path, default=None):
    if default is None:
        default = {}

    if not os.path.exists(path):
        return default

    try:
        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception:
        return default


def save_json(path, data):
    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def get_soup(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT
    )

    response.raise_for_status()

    response.encoding = (
        response.apparent_encoding
    )

    return BeautifulSoup(
        response.text,
        "html.parser"
    )


def horse_url(horse_id):
    return (
        f"https://db.netkeiba.com/"
        f"horse/{horse_id}/"
    )


def pedigree_url(horse_id):
    return (
        f"https://db.netkeiba.com/"
        f"horse/ped/{horse_id}/"
    )


def extract_ancestor_id(link):
    if not link:
        return ""

    href = link.get(
        "href",
        ""
    )

    match = re.search(
        r"/horse/(\d+)/?",
        href
    )

    if match:
        return match.group(1)

    return ""


def extract_name(cell):
    link = cell.find("a")

    if link:
        name = clean_text(
            link.get_text(
                " ",
                strip=True
            )
        )

    else:
        name = clean_text(
            cell.get_text(
                " ",
                strip=True
            )
        )

    # 生年・毛色などを除去
    name = re.sub(
        r"\s+\d{4}.*$",
        "",
        name
    )

    return name


def find_pedigree_table(soup):
    candidates = []

    for table in soup.find_all(
        "table"
    ):
        rows = table.find_all("tr")

        if not rows:
            continue

        cells = table.find_all(
            ["td", "th"]
        )

        if len(cells) >= 20:
            candidates.append(table)

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda table: len(
            table.find_all(
                ["td", "th"]
            )
        )
    )


def parse_pedigree(
    horse_id,
    horse_name
):
    url = pedigree_url(
        horse_id
    )

    soup = get_soup(url)

    table = find_pedigree_table(
        soup
    )

    if table is None:
        raise RuntimeError(
            f"{horse_name}: "
            "血統表を取得できませんでした"
        )

    ancestors = []
    seen_positions = set()

    rows = table.find_all("tr")

    for row_index, row in enumerate(
        rows,
        start=1
    ):
        cells = row.find_all(
            ["td", "th"]
        )

        for cell_index, cell in enumerate(
            cells,
            start=1
        ):
            name = extract_name(
                cell
            )

            if not name:
                continue

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

            ancestor_id = (
                extract_ancestor_id(
                    link
                )
            )

            rowspan_raw = cell.get(
                "rowspan",
                "1"
            )

            try:
                rowspan = int(
                    rowspan_raw
                )
            except ValueError:
                rowspan = 1

            generation_map = {
                16: 1,
                8: 2,
                4: 3,
                2: 4,
                1: 5,
            }

            generation = (
                generation_map.get(
                    rowspan
                )
            )

            if generation is None:
                continue

            position_key = (
                row_index,
                cell_index,
                generation,
                name,
                ancestor_id,
            )

            if (
                position_key
                in seen_positions
            ):
                continue

            seen_positions.add(
                position_key
            )

            ancestors.append({
                "generation":
                    generation,

                "ancestor_name":
                    name,

                "ancestor_id":
                    ancestor_id,

                "row":
                    row_index,

                "cell":
                    cell_index,
            })

    if not ancestors:
        raise RuntimeError(
            f"{horse_name}: "
            "祖先データが0件でした"
        )

    return {
        "horse_id":
            horse_id,

        "horse_name":
            horse_name,

        "source_url":
            url,

        "ancestor_count":
            len(ancestors),

        "ancestors":
            ancestors,
    }


def valid_cached_pedigree(
    item
):
    if not isinstance(
        item,
        dict
    ):
        return False

    horse_id = clean_text(
        item.get("horse_id")
    )

    ancestors = item.get(
        "ancestors"
    )

    if not horse_id:
        return False

    if not isinstance(
        ancestors,
        list
    ):
        return False

    if not ancestors:
        return False

    # 最低限、世代と祖先名が存在するか確認
    valid_count = 0

    for ancestor in ancestors:
        if not isinstance(
            ancestor,
            dict
        ):
            continue

        if (
            ancestor.get(
                "generation"
            )
            and clean_text(
                ancestor.get(
                    "ancestor_name"
                )
            )
        ):
            valid_count += 1

    return valid_count > 0


def build_cache(
    old_data
):
    cache = {}

    if not isinstance(
        old_data,
        dict
    ):
        return cache

    for item in (
        old_data.get(
            "horses",
            []
        )
        or []
    ):
        if not valid_cached_pedigree(
            item
        ):
            continue

        horse_id = clean_text(
            item.get("horse_id")
        )

        cache[horse_id] = item

    return cache


def normalize_cached_item(
    cached,
    horse_id,
    horse_name
):
    item = dict(cached)

    item["horse_id"] = (
        horse_id
    )

    # 名前は今回race.json側を優先
    if horse_name:
        item["horse_name"] = (
            horse_name
        )

    ancestors = (
        item.get(
            "ancestors",
            []
        )
        or []
    )

    item["ancestor_count"] = (
        len(ancestors)
    )

    if not item.get(
        "source_url"
    ):
        item["source_url"] = (
            pedigree_url(
                horse_id
            )
        )

    return item


def main():
    race = load_json(
        INPUT_FILE
    )

    horses = race.get(
        "horses",
        []
    )

    if not horses:
        raise RuntimeError(
            "race.json に出走馬がありません"
        )

    # =====================================================
    # 既存 pedigree.json をキャッシュとして読む
    # =====================================================

    old_data = load_json(
        OUTPUT_FILE,
        {}
    )

    cache = build_cache(
        old_data
    )

    print("")
    print(
        "===== Pedigree Cache ====="
    )
    print(
        "cached horses:",
        len(cache)
    )
    print(
        "target horses:",
        len(horses)
    )
    print("")

    result = {
        "race_id":
            race.get(
                "race_id",
                ""
            ),

        "updated_at":
            datetime.now(
                JST
            ).isoformat(),

        "source":
            "netkeiba",

        "cache_enabled":
            True,

        "horse_count":
            len(horses),

        "success_count":
            0,

        "cache_hit_count":
            0,

        "fetched_count":
            0,

        "error_count":
            0,

        "horses":
            [],

        "errors":
            [],
    }

    for index, horse in enumerate(
        horses,
        start=1
    ):
        horse_id = clean_text(
            horse.get(
                "horse_id",
                ""
            )
        )

        horse_name = clean_text(
            horse.get(
                "horse_name",
                ""
            )
        )

        print(
            f"[{index}/{len(horses)}] "
            f"{horse_name} "
            f"({horse_id})"
        )

        if not horse_id:
            result[
                "errors"
            ].append({
                "horse_name":
                    horse_name,

                "error":
                    "horse_id がありません",
            })

            result[
                "error_count"
            ] += 1

            continue

        # =================================================
        # CACHE HIT
        # =================================================

        cached = cache.get(
            horse_id
        )

        if (
            cached is not None
            and valid_cached_pedigree(
                cached
            )
        ):
            pedigree = (
                normalize_cached_item(
                    cached,
                    horse_id,
                    horse_name
                )
            )

            result[
                "horses"
            ].append(
                pedigree
            )

            result[
                "success_count"
            ] += 1

            result[
                "cache_hit_count"
            ] += 1

            print(
                "  CACHE HIT:",
                pedigree[
                    "ancestor_count"
                ],
                "ancestors"
            )

            # キャッシュなら待機不要
            continue

        # =================================================
        # CACHE MISS
        # =================================================

        try:
            pedigree = (
                parse_pedigree(
                    horse_id,
                    horse_name
                )
            )

            result[
                "horses"
            ].append(
                pedigree
            )

            result[
                "success_count"
            ] += 1

            result[
                "fetched_count"
            ] += 1

            print(
                "  FETCH OK:",
                pedigree[
                    "ancestor_count"
                ],
                "ancestors"
            )

        except Exception as exc:
            result[
                "errors"
            ].append({
                "horse_id":
                    horse_id,

                "horse_name":
                    horse_name,

                "error":
                    str(exc),
            })

            result[
                "error_count"
            ] += 1

            print(
                "  ERROR:",
                exc
            )

        # 新規取得した場合だけ待機
        time.sleep(
            REQUEST_INTERVAL
        )

    # =====================================================
    # 出走順をrace.jsonと同じ順番に固定
    # =====================================================

    horse_order = {
        clean_text(
            horse.get(
                "horse_id"
            )
        ): index
        for index, horse in enumerate(
            horses
        )
    }

    result[
        "horses"
    ].sort(
        key=lambda item: (
            horse_order.get(
                clean_text(
                    item.get(
                        "horse_id"
                    )
                ),
                9999
            )
        )
    )

    result[
        "updated_at"
    ] = datetime.now(
        JST
    ).isoformat()

    save_json(
        OUTPUT_FILE,
        result
    )

    print("")
    print(
        "===== Pedigree Result ====="
    )

    print(
        "success:",
        f"{result['success_count']}/"
        f"{len(horses)}"
    )

    print(
        "cache hit:",
        result[
            "cache_hit_count"
        ]
    )

    print(
        "new fetch:",
        result[
            "fetched_count"
        ]
    )

    print(
        "errors:",
        result[
            "error_count"
        ]
    )

    if (
        result[
            "success_count"
        ] == 0
    ):
        raise RuntimeError(
            "全馬の5代血統取得に"
            "失敗しました"
        )

    # =====================================================
    # 欠損を黙って通さない
    # =====================================================

    if (
        result[
            "success_count"
        ]
        != len(horses)
    ):
        raise RuntimeError(
            "血統取得が全頭分揃っていません: "
            f"{result['success_count']}/"
            f"{len(horses)}"
        )


if __name__ == "__main__":
    main()
