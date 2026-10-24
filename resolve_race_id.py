import argparse
import re
import sys

import requests
from bs4 import BeautifulSoup


TRACK_CODES = {
    "札幌": "01",
    "函館": "02",
    "福島": "03",
    "新潟": "04",
    "東京": "05",
    "中山": "06",
    "中京": "07",
    "京都": "08",
    "阪神": "09",
    "小倉": "10",
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/141.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


def normalize_date(value):
    value = str(value or "").strip()

    match = re.fullmatch(
        r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})",
        value,
    )

    if not match:
        raise ValueError(
            "date must be YYYY-MM-DD"
        )

    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))

    return (
        f"{year:04d}-"
        f"{month:02d}-"
        f"{day:02d}"
    )


def normalize_track(value):
    value = str(value or "").strip()

    if value not in TRACK_CODES:
        raise ValueError(
            f"unsupported track: {value}"
        )

    return value


def normalize_race_number(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(
            "race number must be integer"
        )

    if not 1 <= number <= 12:
        raise ValueError(
            "race number must be 1-12"
        )

    return number


def fetch_html(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    if not response.encoding:
        response.encoding = (
            response.apparent_encoding
            or "utf-8"
        )

    return response.text


def collect_race_ids(html):
    ids = set()

    patterns = [
        r"race_id=(\d{12})",
        r"race_id%3D(\d{12})",
        r"/race/(\d{12})",
        r"race_id[\"']?\s*[:=]\s*[\"'](\d{12})",
    ]

    for pattern in patterns:
        for match in re.findall(
            pattern,
            html,
            flags=re.IGNORECASE,
        ):
            ids.add(str(match))

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    for element in soup.find_all(True):
        for attr in (
            "href",
            "data-race-id",
            "data-race_id",
            "value",
        ):
            value = element.get(attr)

            if not value:
                continue

            for match in re.findall(
                r"\d{12}",
                str(value),
            ):
                ids.add(match)

    return sorted(ids)


def filter_target(
    race_ids,
    date,
    track,
    race_number,
):
    year = date[:4]
    track_code = TRACK_CODES[track]
    race_suffix = f"{race_number:02d}"

    prefix = year + track_code

    candidates = [
        race_id
        for race_id in race_ids
        if (
            len(race_id) == 12
            and race_id.startswith(prefix)
            and race_id.endswith(race_suffix)
        )
    ]

    return sorted(set(candidates))


def verify_candidate(
    race_id,
    date,
    track,
    race_number,
):
    url = (
        "https://race.netkeiba.com/"
        "race/shutuba.html?"
        f"race_id={race_id}"
    )

    try:
        html = fetch_html(url)
    except Exception:
        return False

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    text = soup.get_text(
        " ",
        strip=True,
    )

    # 競馬場
    if track not in text:
        title = (
            soup.title.get_text(
                " ",
                strip=True,
            )
            if soup.title
            else ""
        )

        if track not in title:
            return False

    # レース番号
    race_patterns = [
        rf"\b{race_number}R\b",
        rf"{race_number}\s*R",
    ]

    race_number_found = any(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        for pattern in race_patterns
    )

    if not race_number_found:
        # race_id末尾でも確認
        if not race_id.endswith(
            f"{race_number:02d}"
        ):
            return False

    # 日付
    y, m, d = date.split("-")

    date_patterns = [
        rf"{y}年\s*{int(m)}月\s*{int(d)}日",
        rf"{y}/{int(m)}/{int(d)}",
        rf"{y}-{m}-{d}",
        rf"{y}\.{int(m)}\.{int(d)}",
    ]

    date_found = any(
        re.search(
            pattern,
            text,
        )
        for pattern in date_patterns
    )

    if not date_found:
        metadata = " ".join(
            [
                str(
                    soup.title.get_text(
                        " ",
                        strip=True,
                    )
                    if soup.title
                    else ""
                ),
                str(
                    soup.find(
                        "meta",
                        attrs={
                            "name": "description"
                        },
                    ).get("content", "")
                    if soup.find(
                        "meta",
                        attrs={
                            "name": "description"
                        },
                    )
                    else ""
                ),
            ]
        )

        date_found = any(
            re.search(
                pattern,
                metadata,
            )
            for pattern in date_patterns
        )

    return date_found


def resolve_from_race_list(
    date,
    track,
    race_number,
):
    ymd = date.replace("-", "")

    urls = [
        (
            "https://race.netkeiba.com/"
            "top/race_list.html?"
            f"kaisai_date={ymd}"
        ),
        (
            "https://race.netkeiba.com/"
            "top/race_list_sub.html?"
            f"kaisai_date={ymd}"
        ),
    ]

    all_ids = set()

    for url in urls:
        print(
            "checking race list:",
            url,
        )

        try:
            html = fetch_html(url)
        except Exception as exc:
            print(
                "race list fetch failed:",
                repr(exc),
            )
            continue

        ids = collect_race_ids(html)

        print(
            "race ids found:",
            len(ids),
        )

        all_ids.update(ids)

    candidates = filter_target(
        sorted(all_ids),
        date,
        track,
        race_number,
    )

    print(
        "filtered candidates:",
        candidates,
    )

    verified = []

    for race_id in candidates:
        if verify_candidate(
            race_id,
            date,
            track,
            race_number,
        ):
            verified.append(race_id)

    return verified


def resolve_by_candidate_probe(
    date,
    track,
    race_number,
):
    """
    race_listから取れない場合の安全なフォールバック。

    JRA race_id:
      YYYY + 場コード + 開催回2桁
      + 開催日目2桁 + R2桁

    開催回 01-12
    開催日目 01-12 を候補生成し、
    実ページの日付・競馬場を照合する。
    """

    year = date[:4]
    track_code = TRACK_CODES[track]

    verified = []

    for meeting in range(1, 13):
        for day_no in range(1, 13):
            race_id = (
                year
                + track_code
                + f"{meeting:02d}"
                + f"{day_no:02d}"
                + f"{race_number:02d}"
            )

            if verify_candidate(
                race_id,
                date,
                track,
                race_number,
            ):
                verified.append(
                    race_id
                )

                print(
                    "verified candidate:",
                    race_id,
                )

    return sorted(
        set(verified)
    )


def resolve_race_id(
    date,
    track,
    race_number,
):
    date = normalize_date(date)
    track = normalize_track(track)
    race_number = normalize_race_number(
        race_number
    )

    print("========================================")
    print("RACE ID RESOLVER")
    print("========================================")
    print("date:", date)
    print("track:", track)
    print("race_number:", race_number)

    candidates = resolve_from_race_list(
        date,
        track,
        race_number,
    )

    if len(candidates) == 1:
        return candidates[0]

    if len(candidates) > 1:
        raise RuntimeError(
            "multiple verified Race IDs: "
            + ", ".join(candidates)
        )

    print()
    print(
        "race list did not resolve uniquely."
    )
    print(
        "starting verified candidate probe..."
    )

    candidates = resolve_by_candidate_probe(
        date,
        track,
        race_number,
    )

    if len(candidates) == 1:
        return candidates[0]

    if not candidates:
        raise RuntimeError(
            f"Race ID not found: "
            f"{date} {track} {race_number}R"
        )

    raise RuntimeError(
        "multiple verified Race IDs: "
        + ", ".join(candidates)
    )


def save_race_id(
    race_id,
    path,
):
    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:
        f.write(
            race_id + "\n"
        )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--date",
        required=True,
    )

    parser.add_argument(
        "--track",
        required=True,
    )

    parser.add_argument(
        "--race-number",
        required=True,
        type=int,
    )

    parser.add_argument(
        "--output",
        default="race_id.txt",
    )

    args = parser.parse_args()

    race_id = resolve_race_id(
        args.date,
        args.track,
        args.race_number,
    )

    if not re.fullmatch(
        r"\d{12}",
        race_id,
    ):
        raise RuntimeError(
            "resolved Race ID is invalid"
        )

    save_race_id(
        race_id,
        args.output,
    )

    print()
    print("========================================")
    print("RACE ID RESOLVED")
    print("========================================")
    print("Race ID:", race_id)
    print("output:", args.output)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            "ERROR:",
            exc,
            file=sys.stderr,
        )
        raise
