import re
import requests
from urllib.parse import urljoin


# ============================================================
# 設定
# ============================================================

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


# ============================================================
# HTTP
# ============================================================

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


# ============================================================
# JavaScript一覧取得
# ============================================================

def get_script_urls(html):

    sources = re.findall(
        r'<script[^>]+src=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE
    )

    urls = []

    for source in sources:

        url = urljoin(
            BABA_URL,
            source
        )

        if url not in urls:
            urls.append(url)

    return urls


# ============================================================
# JavaScript関数を丸ごと抽出
# ============================================================

def extract_function(
    javascript,
    function_name
):

    pattern = re.compile(
        rf"function\s+"
        rf"{re.escape(function_name)}"
        rf"\s*\([^)]*\)\s*\{{"
    )

    match = pattern.search(
        javascript
    )

    if not match:
        return ""


    brace_start = javascript.find(
        "{",
        match.start()
    )

    if brace_start == -1:
        return ""


    depth = 0

    in_single = False
    in_double = False
    in_template = False

    escaped = False


    for index in range(
        brace_start,
        len(javascript)
    ):

        char = javascript[index]


        if escaped:

            escaped = False

            continue


        if char == "\\":

            escaped = True

            continue


        if (
            char == "'"
            and not in_double
            and not in_template
        ):

            in_single = not in_single

            continue


        if (
            char == '"'
            and not in_single
            and not in_template
        ):

            in_double = not in_double

            continue


        if (
            char == "`"
            and not in_single
            and not in_double
        ):

            in_template = not in_template

            continue


        if (
            in_single
            or in_double
            or in_template
        ):

            continue


        if char == "{":

            depth += 1


        elif char == "}":

            depth -= 1


            if depth == 0:

                return javascript[
                    match.start():
                    index + 1
                ]


    return ""


# ============================================================
# URL・通信部分抽出
# ============================================================

def extract_network_info(
    function_text
):

    results = []


    patterns = [

        r"url\s*:\s*[^,\n]+",

        r"\$\.ajax\s*\([^;]{0,5000}",

        r"\$\.getJSON\s*\([^;]{0,5000}",

        r"\$\.get\s*\([^;]{0,5000}",

        r"fetch\s*\([^;]{0,5000}",

        r"""["'][^"']+\.(?:html|json|xml|php|csv)(?:\?[^"']*)?["']""",

    ]


    for pattern in patterns:

        for match in re.finditer(
            pattern,
            function_text,
            flags=re.IGNORECASE
        ):

            value = match.group(0).strip()

            if value not in results:
                results.append(value)


    return results


# ============================================================
# 実行
# ============================================================

print()
print(
    "========================================"
)

print(
    "JRA GET_MOIST_DATA PROBE"
)

print(
    "========================================"
)

print(
    "PAGE:",
    BABA_URL
)


# ============================================================
# index.html
# ============================================================

try:

    html = get_text(
        BABA_URL
    )

except Exception as exc:

    raise SystemExit(
        "ERROR: JRA page fetch failed: "
        + str(exc)
    )


script_urls = get_script_urls(
    html
)


print(
    "JS FILE COUNT:",
    len(script_urls)
)


# ============================================================
# get_moist_data()探索
# ============================================================

found = False


for script_url in script_urls:

    try:

        javascript = get_text(
            script_url
        )

    except Exception:

        continue


    if "get_moist_data" not in javascript:

        continue


    function_text = extract_function(
        javascript,
        "get_moist_data"
    )


    if not function_text:

        continue


    found = True


    print()
    print(
        "========================================"
    )

    print(
        "FOUND get_moist_data()"
    )

    print(
        "JS:",
        script_url
    )

    print(
        "========================================"
    )


    # --------------------------------------------------------
    # 関数全文
    # --------------------------------------------------------

    print()

    print(
        "===== FUNCTION START ====="
    )

    print(
        function_text
    )

    print(
        "===== FUNCTION END ====="
    )


    # --------------------------------------------------------
    # 通信情報
    # --------------------------------------------------------

    network_info = extract_network_info(
        function_text
    )


    print()

    print(
        "===== NETWORK INFO ====="
    )


    if network_info:

        for number, value in enumerate(
            network_info,
            start=1
        ):

            print()

            print(
                "NETWORK",
                number
            )

            print(
                value
            )

    else:

        print(
            "NETWORK INFO NOT FOUND"
        )


    break


# ============================================================
# 見つからなかった場合
# ============================================================

if not found:

    print()

    print(
        "ERROR: get_moist_data() NOT FOUND"
    )


print()

print(
    "========================================"
)

print(
    "PROBE FINISHED"
)

print(
    "========================================"
)
