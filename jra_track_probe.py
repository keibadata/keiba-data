import re
import requests
from urllib.parse import urljoin


# =========================================================
# 設定
# =========================================================

BASE_URL = "https://www.jra.go.jp"
BABA_URL = "https://www.jra.go.jp/keiba/baba/index.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": BABA_URL,
}

TIMEOUT = 30


# =========================================================
# HTTP取得
# =========================================================

def get_text(url):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT
    )

    response.raise_for_status()

    if (
        not response.encoding
        or response.encoding.lower()
        in ["iso-8859-1", "ascii"]
    ):
        response.encoding = (
            response.apparent_encoding
            or "utf-8"
        )

    return response.text


# =========================================================
# JavaScript URL取得
# =========================================================

def extract_script_urls(html):

    scripts = re.findall(
        r'<script[^>]+src=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE
    )

    urls = []

    for src in scripts:

        full_url = urljoin(
            BABA_URL,
            src
        )

        if full_url not in urls:
            urls.append(full_url)

    return urls


# =========================================================
# キーワード周辺抽出
# =========================================================

def extract_all_contexts(
    text,
    keyword,
    before=1200,
    after=2500
):

    results = []

    pattern = re.compile(
        re.escape(keyword),
        flags=re.IGNORECASE
    )

    for match in pattern.finditer(text):

        start = max(
            0,
            match.start() - before
        )

        end = min(
            len(text),
            match.end() + after
        )

        value = text[start:end]

        if value not in results:
            results.append(value)

    return results


# =========================================================
# URL候補
# =========================================================

def extract_url_candidates(text):

    patterns = [
        r'https?://[^\s\'"<>]+',

        r'["\'][^"\']*moisture[^"\']*["\']',

        r'["\'][^"\']*water[^"\']*["\']',

        r'["\'][^"\']*baba[^"\']*["\']',

        r'["\'][^"\']+\.(?:json|php|html|xml|csv)'
        r'(?:\?[^"\']*)?["\']',

        r'url\s*:\s*[^,\n]+',

        r'fetch\s*\([^;]{0,2000}',

        r'\$\.ajax\s*\([^;]{0,3000}',

        r'\$\.getJSON\s*\([^;]{0,2000}',

        r'\$\.get\s*\([^;]{0,2000}',
    ]

    results = []

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            text,
            flags=re.IGNORECASE
        ):

            value = match.group(0).strip()

            if value not in results:
                results.append(value)

    return results


# =========================================================
# 関数名候補抽出
# =========================================================

def extract_function_names(text):

    names = []

    patterns = [
        r'function\s+([A-Za-z0-9_$]+)\s*\(',
        r'([A-Za-z0-9_$]+)\s*=\s*function\s*\(',
    ]

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            text
        ):

            name = match.group(1)

            lower = name.lower()

            if any(
                word in lower
                for word in [
                    "moist",
                    "water",
                    "baba",
                    "condition",
                    "track",
                    "data"
                ]
            ):

                if name not in names:
                    names.append(name)

    return names


# =========================================================
# 通信処理だけ抽出
# =========================================================

def extract_network_blocks(text):

    patterns = [
        r'\$\.ajax\s*\([^;]{0,5000}',
        r'\$\.getJSON\s*\([^;]{0,4000}',
        r'\$\.get\s*\([^;]{0,4000}',
        r'\$\.post\s*\([^;]{0,4000}',
        r'fetch\s*\([^;]{0,4000}',
        r'XMLHttpRequest[^;]{0,4000}',
    ]

    results = []

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            text,
            flags=re.IGNORECASE
        ):

            value = match.group(0)

            if value not in results:
                results.append(value)

    return results


# =========================================================
# HTML側の含水率関連記述
# =========================================================

def probe_html(html):

    print()
    print("===== HTML MOISTURE RELATED CODE =====")

    keywords = [
        "moisture",
        "含水",
        "含水率",
        "ゴール前",
        "4コーナー",
        "ダート",
        "芝"
    ]

    found = False

    for keyword in keywords:

        contexts = extract_all_contexts(
            html,
            keyword,
            before=800,
            after=1600
        )

        if not contexts:
            continue

        found = True

        print()
        print("----------------------------------------")
        print("HTML KEYWORD:", keyword)
        print("COUNT:", len(contexts))
        print("----------------------------------------")

        for number, context in enumerate(
            contexts[:5],
            start=1
        ):

            print()
            print(
                f"[HTML {keyword} #{number}]"
            )

            print(context)

    if not found:
        print("HTML MOISTURE DATA NOT FOUND")


# =========================================================
# 実行
# =========================================================

print("========================================")
print("JRA MOISTURE NETWORK PROBE")
print("========================================")
print("PAGE:", BABA_URL)


try:

    html = get_text(
        BABA_URL
    )

except Exception as exc:

    raise SystemExit(
        "ERROR: JRA馬場ページ取得失敗: "
        + str(exc)
    )


print(
    "INDEX SIZE:",
    len(html)
)


# =========================================================
# HTML本体確認
# =========================================================

probe_html(html)


# =========================================================
# JS一覧
# =========================================================

script_urls = extract_script_urls(
    html
)


print()
print("===== JAVASCRIPT FILES =====")
print(
    "COUNT:",
    len(script_urls)
)


for index, url in enumerate(
    script_urls,
    start=1
):

    print(
        f"{index}: {url}"
    )


# =========================================================
# JS探索
# =========================================================

search_keywords = [
    "moisture",
    "含水",
    "含水率",
    "water",
    "ゴール前",
    "4コーナー",
    "baba",
]


matched_scripts = 0


for script_number, script_url in enumerate(
    script_urls,
    start=1
):

    try:

        javascript = get_text(
            script_url
        )

    except Exception as exc:

        print()
        print(
            "JS ERROR:",
            script_url,
            exc
        )

        continue


    matched_keywords = []

    for keyword in search_keywords:

        if re.search(
            re.escape(keyword),
            javascript,
            flags=re.IGNORECASE
        ):

            matched_keywords.append(
                keyword
            )


    # 含水関連が無ければ、
    # URL/通信候補だけ確認
    url_candidates = extract_url_candidates(
        javascript
    )

    moisture_url_candidates = []

    for value in url_candidates:

        lower = value.lower()

        if any(
            word in lower
            for word in [
                "moist",
                "water",
                "baba",
                "condition"
            ]
        ):
            moisture_url_candidates.append(
                value
            )


    if (
        not matched_keywords
        and not moisture_url_candidates
    ):
        continue


    matched_scripts += 1


    print()
    print("========================================")
    print(
        "MATCHED JS #",
        matched_scripts
    )
    print(
        "SCRIPT NUMBER:",
        script_number
    )
    print(
        "URL:",
        script_url
    )
    print(
        "SIZE:",
        len(javascript)
    )
    print(
        "KEYWORDS:",
        matched_keywords
    )
    print("========================================")


    # =====================================================
    # 含水率関連コード
    # =====================================================

    print()
    print("===== MOISTURE RELATED CODE =====")


    related_found = False


    for keyword in search_keywords:

        contexts = extract_all_contexts(
            javascript,
            keyword,
            before=1800,
            after=4000
        )

        if not contexts:
            continue


        related_found = True


        print()
        print("----------------------------------------")
        print(
            "KEYWORD:",
            keyword
        )
        print(
            "MATCH COUNT:",
            len(contexts)
        )
        print("----------------------------------------")


        for number, context in enumerate(
            contexts[:8],
            start=1
        ):

            print()
            print(
                f"[{keyword} CONTEXT #{number}]"
            )

            print(context)


    if not related_found:

        print(
            "MOISTURE RELATED CODE NOT FOUND"
        )


    # =====================================================
    # 関数候補
    # =====================================================

    print()
    print("===== RELATED FUNCTION NAMES =====")


    function_names = extract_function_names(
        javascript
    )


    if function_names:

        for name in function_names:

            print(name)

    else:

        print(
            "RELATED FUNCTION NOT FOUND"
        )


    # =====================================================
    # URL候補
    # =====================================================

    print()
    print("===== MOISTURE URL CANDIDATES =====")


    if moisture_url_candidates:

        for number, candidate in enumerate(
            moisture_url_candidates,
            start=1
        ):

            print()
            print(
                f"URL CANDIDATE #{number}"
            )

            print(candidate)

    else:

        print(
            "MOISTURE URL CANDIDATE NOT FOUND"
        )


    # =====================================================
    # 通信処理
    # =====================================================

    print()
    print("===== NETWORK BLOCKS =====")


    network_blocks = extract_network_blocks(
        javascript
    )


    relevant_network_blocks = []


    for block in network_blocks:

        lower = block.lower()

        if any(
            word in lower
            for word in [
                "moist",
                "water",
                "baba",
                "condition",
                "json",
                "xml",
                "csv"
            ]
        ):

            relevant_network_blocks.append(
                block
            )


    if relevant_network_blocks:

        for number, block in enumerate(
            relevant_network_blocks,
            start=1
        ):

            print()
            print(
                f"NETWORK #{number}"
            )

            print(block)

    else:

        print(
            "RELEVANT NETWORK BLOCK NOT FOUND"
        )


# =========================================================
# 終了
# =========================================================

print()
print("========================================")
print(
    "MATCHED SCRIPT COUNT:",
    matched_scripts
)
print(
    "JRA MOISTURE NETWORK PROBE FINISHED"
)
print("========================================")
