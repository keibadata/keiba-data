import json
import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

# ==========================================
# 設定
# ==========================================

DEFAULT_RACE_ID = "202605040502"

# GitHub ActionsからRACE_IDが渡されたらそれを使用。
# 渡されなければDEFAULT_RACE_IDを使用。
RACE_ID = os.environ.get("RACE_ID", DEFAULT_RACE_ID).strip()

if not re.fullmatch(r"\d{12}", RACE_ID):
    raise ValueError(
        f"RACE_IDが不正です: {RACE_ID} "
        "12桁のnetkeibaレースIDを指定してください。"
    )

URL = (
    "https://race.netkeiba.com/race/"
    f"shutuba.html?race_id={RACE_ID}"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}


# ==========================================
# 補助関数
# ==========================================

def clean_text(element):
    if element is None:
        return ""
    return element.get_text(" ", strip=True)


def first_text(row, selectors):
    for selector in selectors:
        element = row.select_one(selector)
        if element:
            value = clean_text(element)
            if value:
                return value
    return ""


def normalize_weight(value):
    if not value:
        return ""

    match = re.search(r"\d+(?:\.\d+)?", value)
    return match.group(0) if match else value


def parse_body_weight(value):
    if not value:
        return "", ""

    text = value.replace(" ", "")

    match = re.search(
        r"(\d+)\(([＋+\-−ー]?\d+|前計不|計不)\)",
        text
    )

    if match:
        weight = match.group(1)
        change = match.group(2)

        change = (
            change
            .replace("＋", "+")
            .replace("−", "-")
            .replace("ー", "-")
        )

        return weight, change

    match = re.search(r"(\d+)", text)

    if match:
        return match.group(1), ""

    return "", ""


# ==========================================
# 出馬表取得
# ==========================================

response = requests.get(
    URL,
    headers=HEADERS,
    timeout=30
)

response.raise_for_status()

response.encoding = response.apparent_encoding

soup = BeautifulSoup(
    response.text,
    "html.parser"
)

horses = []

for row in soup.select(".HorseList"):

    horse_name = first_text(
        row,
        [
            ".HorseName a",
            ".HorseName"
        ]
    )

    if not horse_name:
        continue

    horse_number = first_text(
        row,
        [
            ".Umaban",
            ".Horse_Num"
        ]
    )

    sex_age = first_text(
        row,
        [
            ".Barei",
            ".Horse_Info_Detail"
        ]
    )

    carried_weight = first_text(
        row,
        [
            ".JockeyInfo .Weight",
            ".Weight",
            ".JockeyWeight"
        ]
    )

    jockey = first_text(
        row,
        [
            ".Jockey a",
            ".Jockey"
        ]
    )

    body_weight_raw = first_text(
        row,
        [
            ".Weight",
            ".HorseWeight",
            ".BodyWeight"
        ]
    )

    # 「55.0」など斤量を馬体重として誤認しない
    body_weight = ""
    body_weight_change = ""

    candidates = [
        clean_text(x)
        for x in row.select(
            ".Weight, .HorseWeight, .BodyWeight"
        )
    ]

    for candidate in candidates:
        if re.search(r"\d{3}\s*\(", candidate):
            body_weight, body_weight_change = (
                parse_body_weight(candidate)
            )
            break

    horses.append({
        "horse_number": horse_number,
        "horse_name": horse_name,
        "sex_age": sex_age,
        "carried_weight": normalize_weight(
            carried_weight
        ),
        "jockey": jockey,
        "body_weight": body_weight,
        "body_weight_change": body_weight_change
    })


# ==========================================
# 最低限の検証
# ==========================================

if len(horses) == 0:
    raise RuntimeError(
        "出走馬を取得できませんでした。"
        "HTML構造またはレースIDを確認してください。"
    )


# ==========================================
# JSON作成
# ==========================================

JST = timezone(timedelta(hours=9))

data = {
    "race_id": RACE_ID,
    "updated_at": datetime.now(JST).isoformat(),
    "source": "netkeiba",
    "source_url": URL,
    "horse_count": len(horses),
    "horses": horses
}

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


print(
    json.dumps(
        data,
        ensure_ascii=False,
        indent=2
    )
)
