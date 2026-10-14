import json
import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

# =========================================================
# 設定
# =========================================================

DEFAULT_RACE_ID = "202605040502"

RACE_ID = os.environ.get("RACE_ID", DEFAULT_RACE_ID).strip()

if not re.fullmatch(r"\d{12}", RACE_ID):
    raise ValueError(
        f"RACE_IDは12桁で指定してください: {RACE_ID}"
    )

URL = (
    "https://race.netkeiba.com/race/shutuba.html"
    f"?race_id={RACE_ID}"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}


# =========================================================
# 補助関数
# =========================================================

def clean_text(value):
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        value.get_text(" ", strip=True)
    ).strip()


def first_text(row, selectors):
    for selector in selectors:
        element = row.select_one(selector)

        if element:
            text = clean_text(element)

            if text:
                return text

    return ""


def parse_body_weight(text):
    if not text:
        return "", ""

    text = text.replace(" ", "")

    match = re.search(
        r"(\d{3})(?:\(([+-]?\d+)\))?",
        text
    )

    if not match:
        return text, ""

    weight = match.group(1)
    change = match.group(2) or ""

    return weight, change


# =========================================================
# HTML取得
# =========================================================

response = requests.get(
    URL,
    headers=HEADERS,
    timeout=30
)

response.raise_for_status()

response.encoding = response.apparent_encoding

html = response.text

if not html:
    raise RuntimeError("HTMLを取得できませんでした。")

soup = BeautifulSoup(
    html,
    "html.parser"
)


# =========================================================
# 出走馬取得
# =========================================================

horses = []

rows = soup.select(
    "tr.HorseList, "
    ".HorseList"
)

for row in rows:

    horse_link = row.select_one(
        ".HorseName a, "
        "a[href*='/horse/']"
    )

    if not horse_link:
        continue

    horse_name = clean_text(horse_link)

    if not horse_name:
        continue

    horse_number = first_text(
        row,
        [
            ".Umaban",
            ".Horse_Num",
            "[class*='Umaban']"
        ]
    )

    sex_age = first_text(
        row,
        [
            ".Barei",
            ".HorseInfo .Barei",
            "[class*='Barei']"
        ]
    )

    carried_weight = first_text(
        row,
        [
            ".JockeyWeight",
            ".Weight",
            "[class*='Weight']"
        ]
    )

    jockey = first_text(
        row,
        [
            ".Jockey a",
            ".Jockey",
            "[class*='Jockey'] a"
        ]
    )

    body_weight_text = first_text(
        row,
        [
            ".Weight",
            ".HorseWeight",
            "[class*='Weight']"
        ]
    )

    body_weight, body_weight_change = parse_body_weight(
        body_weight_text
    )

    horse_id = ""

    href = horse_link.get("href", "")

    horse_id_match = re.search(
        r"/horse/(\d+)",
        href
    )

    if horse_id_match:
        horse_id = horse_id_match.group(1)

    horses.append(
        {
            "horse_number": horse_number,
            "horse_id": horse_id,
            "horse_name": horse_name,
            "sex_age": sex_age,
            "carried_weight": carried_weight,
            "jockey": jockey,
            "body_weight": body_weight,
            "body_weight_change": body_weight_change
        }
    )


# =========================================================
# 重複除去
# =========================================================

unique_horses = []
seen = set()

for horse in horses:

    key = (
        horse["horse_number"],
        horse["horse_name"]
    )

    if key in seen:
        continue

    seen.add(key)
    unique_horses.append(horse)

horses = unique_horses


# =========================================================
# 取得チェック
# =========================================================

if len(horses) == 0:

    debug = {
        "race_id": RACE_ID,
        "url": URL,
        "html_length": len(html),
        "title": soup.title.get_text(
            " ",
            strip=True
        ) if soup.title else "",
        "horse_list_count": len(
            soup.select(".HorseList")
        ),
        "horse_link_count": len(
            soup.select("a[href*='/horse/']")
        )
    }

    with open(
        "debug.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            debug,
            f,
            ensure_ascii=False,
            indent=2
        )

    raise RuntimeError(
        "出走馬を取得できませんでした。"
        " debug.json を確認してください。"
    )


# =========================================================
# JSON作成
# =========================================================

JST = timezone(
    timedelta(hours=9)
)

data = {
    "race_id": RACE_ID,
    "updated_at": datetime.now(
        JST
    ).isoformat(),
    "source": "netkeiba",
    "source_url": URL,
    "horse_count": len(horses),
    "horses": horses
}


# =========================================================
# 保存
# =========================================================

with open(
    "race.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        data,
        f,
        ensure_ascii=False,
        indent=2
    )


# =========================================================
# ログ
# =========================================================

print(
    json.dumps(
        data,
        ensure_ascii=False,
        indent=2
    )
)

print(
    f"\n取得完了: {len(horses)}頭"
)
