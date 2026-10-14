import json
import re
from datetime import datetime, timezone


INPUT_FILE = "history_pedigree.json"
OUTPUT_FILE = "history_pedigree.json"


def normalize_ancestor_name(name):
    if not name:
        return ""

    name = " ".join(str(name).split())

    # 例:
    # "シンボリクリスエス 1999 黒鹿毛"
    # "Sunday Silence 1986"
    #
    # 末尾に付いている4桁の生年以降を除去。
    name = re.sub(
        r"\s+(18|19|20)\d{2}(?:\s+.*)?$",
        "",
        name
    )

    return name.strip()


def main():

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        data = json.load(f)

    changed = 0
    total = 0
    examples = []

    for horse in data.get("horses", []):

        for ancestor in horse.get(
            "ancestors",
            []
        ):

            total += 1

            old_name = ancestor.get(
                "ancestor_name",
                ""
            )

            new_name = normalize_ancestor_name(
                old_name
            )

            if old_name != new_name:

                changed += 1

                if len(examples) < 20:
                    examples.append({
                        "before": old_name,
                        "after": new_name
                    })

                ancestor[
                    "ancestor_name"
                ] = new_name

    data[
        "normalized_at"
    ] = datetime.now(
        timezone.utc
    ).isoformat()

    data[
        "normalization"
    ] = {
        "total_ancestor_rows": total,
        "changed_ancestor_rows": changed,
        "rule":
            "末尾の4桁生年以降の付加情報を祖先名から除去。ancestor_idは変更しない。"
    }

    with open(
        OUTPUT_FILE,
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
        "========================"
    )

    print(
        "祖先行数:",
        total
    )

    print(
        "正規化:",
        changed
    )

    print(
        "----- 変換例 -----"
    )

    for example in examples:
        print(
            example["before"],
            "=>",
            example["after"]
        )

    print(
        "history_pedigree.json 更新完了"
    )


if __name__ == "__main__":
    main()
