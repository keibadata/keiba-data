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
RACE_ID = os.environ.get("RACE_ID", DEFAULT_RACE_ID).strip()

if not re.fullmatch(r"\d{12}", RACE_ID):
    raise ValueError("RACE_IDは12桁の数字で指定してください。")

URL = f"https://race.netkeiba.com/race/shutuba.html?race_id={RACE_ID}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# ==========================================
# HTML取得
# ==========================================

response = requests.get(URL, headers=HEADERS, timeout=30)
response.raise_for_status()

response.encoding = response.apparent_encoding
soup = BeautifulSoup(response.text, "html.parser")

horses = []

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
            text = clean_text(element)
            if text:
                return text
    return ""


def extract_horse_id(row):
    link = row.select_one('a[href*="/horse/"]')

    if not link:
        return ""

    href = link.get("href", "")

    patterns = [
        r"/horse/(\d+)",
        r"horse_id=(\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, href)
        if match:
            return match.group(1)

    return ""


def extract_horse_name(row):
    selectors = [
        ".HorseName a",
        ".HorseInfo .HorseName a",
        'a[href*="/horse/"]',
    ]

    name = first_text(row, selectors)

    # 「○○のデータベース」を除去
    name = re.sub(r"のデータベース$", "", name).strip()

    return name


def extract_number(row):
    selectors = [
        ".Umaban",
        ".Horse_Num",
        ".Num",
        "td.Umaban",
    ]

    text = first_text(row, selectors)

    match = re.search(r"\d+", text)

    if match:
        return match.group()

    # classが取れない場合、行の先頭付近から探す
    cells = row.find_all(["td", "div"])

    for cell in cells[:5]:
        value = clean_text(cell)

        if re.fullmatch(r"\d{1,2}", value):
            number = int(value)

            if 1 <= number <= 18:
                return str(number)

    return ""


def extract_sex_age(row):
    selectors = [
        ".Barei",
        ".HorseInfo .Barei",
        ".SexAge",
    ]

    text = first_text(row, selectors)

    match = re.search(r"[牡牝セ騸]\s*\d+", text)

    if match:
        return re.sub(r"\s+", "", match.group())

    # 行全体から保険で検索
    row_text = clean_text(row)
    match = re.search(r"[牡牝セ騸]\s*\d+", row_text)

    if match:
        return re.sub(r"\s+", "", match.group())

    return ""


def extract_jockey_and_weight(row):
    jockey = ""
    carried_weight = ""

    jockey_selectors = [
        ".Jockey a",
        ".Jockey",
        'a[href*="/jockey/"]',
    ]

    jockey_text = first_text(row, jockey_selectors)

    # 例:
    # 浜中 55.0
    # C.ルメール 55.0
    weight_match = re.search(r"(\d{2}(?:\.\d)?)", jockey_text)

    if weight_match:
        carried_weight = weight_match.group(1)
        jockey = jockey_text[:weight_match.start()].strip()
    else:
        jockey = jockey_text.strip()

    # 斤量専用classがあればそちらを優先
    weight_selectors = [
        ".Weight",
        ".Kinryo",
        ".BurdenWeight",
    ]

    weight_text = first_text(row, weight_selectors)

    weight_match2 = re.search(r"\d{2}(?:\.\d)?", weight_text)

    if weight_match2:
        carried_weight = weight_match2.group()

    return jockey, carried_weight


def extract_body_weight(row):
    selectors = [
        ".Weight",
        ".HorseWeight",
        ".BodyWeight",
    ]

    candidates = []

    for selector in selectors:
        for element in row.select(selector):
            text = clean_text(element)

            if re.search(r"\d{3}\s*\([+\-−]?\d+\)", text):
                candidates.append(text)

    row_text = clean_text(row)

    if not candidates:
        match = re.search(
            r"(\d{3})\s*\(([+\-−]?\d+)\)",
            row_text
        )

        if match:
            weight = match.group(1)
            change = match.group(2).replace("−", "-")

            if not change.startswith(("+", "-")):
                if change != "0":
                    change = "+" + change

            return weight, change

    for text in candidates:
        match = re.search(
            r"(\d{3})\s*\(([+\-−]?\d+)\)",
            text
        )

        if match:
            weight = match.group(1)
            change = match.group(2).replace("−", "-")

            if not change.startswith(("+", "-")):
                if change != "0":
                    change = "+" + change

            return weight, change

    return "", ""


# ==========================================
# 出走馬解析
# ==========================================

rows = soup.select(".HorseList")

for row in rows:

    horse_name = extract_horse_name(row)

    if not horse_name:
        continue

    horse_id = extract_horse_id(row)
    horse_number = extract_number(row)
    sex_age = extract_sex_age(row)

    jockey, carried_weight = extract_jockey_and_weight(row)

    body_weight, body_weight_change = extract_body_weight(row)

    horses.append({
        "horse_number": horse_number,
        "horse_id": horse_id,
        "horse_name": horse_name,
        "sex_age": sex_age,
        "carried_weight": carried_weight,
        "jockey": jockey,
        "body_weight": body_weight,
        "body_weight_change": body_weight_change,
    })

# ==========================================
# 最低限の取得チェック
# ==========================================

if not horses:
    raise RuntimeError(
        "出走馬を取得できませんでした。HTML構造またはレースIDを確認してください。"
    )

# 馬番が取れている馬を優先して並べる
def horse_sort_key(horse):
    number = horse["horse_number"]

    if number.isdigit():
        return int(number)

    return 999


horses.sort(key=horse_sort_key)

# ==========================================
# JSON出力
# ==========================================

JST = timezone(timedelta(hours=9))

data = {
    "race_id": RACE_ID,
    "updated_at": datetime.now(JST).isoformat(),
    "source": "netkeiba",
    "source_url": URL,
    "horse_count": len(horses),
    "horses": horses,
}

with open("race.json", "w", encoding="utf-8") as f:
    json.dump(
        data,
        f,
        ensure_ascii=False,
        indent=2
    )

print(json.dumps(data, ensure_ascii=False, indent=2))

# ==========================================
# 確認表示
# ==========================================

print("\n--- CHECK ---")
print(f"race_id: {RACE_ID}")
print(f"horse_count: {len(horses)}")

for horse in horses:
    print(
        horse["horse_number"],
        horse["horse_name"],
        horse["sex_age"],
        horse["carried_weight"],
        horse["jockey"],
        horse["body_weight"],
        horse["body_weight_change"],
    )
