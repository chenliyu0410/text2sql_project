"""PowerQuery TW command-line and local web server entry point."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from serving.presentation import enrich_query_data
from serving.runtime import build_runtime


def _text_table(columns: list[str], rows: list[list[object]], *, maximum: int = 20) -> str:
    shown = rows[:maximum]
    values = [["" if value is None else str(value) for value in row] for row in shown]
    widths = [
        min(32, max([len(column), *(len(row[index]) for row in values)]))
        for index, column in enumerate(columns)
    ]

    def line(parts: list[str]) -> str:
        return " | ".join(
            part[: widths[index]].ljust(widths[index]) for index, part in enumerate(parts)
        )

    output = [line(columns), "-+-".join("-" * width for width in widths)]
    output.extend(line(row) for row in values)
    if len(rows) > maximum:
        output.append(f"… 共 {len(rows)} 筆，終端只顯示前 {maximum} 筆。")
    return "\n".join(output)


def _print_response(response: dict[str, Any], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return int(not response["success"])
    if not response["success"]:
        print(f"[{response.get('error_code', 'ERROR')}] {response.get('error', '查詢失敗')}")
        for suggestion in response.get("suggestions", []):
            print(f"- {suggestion}")
        return 2
    data = response["data"]
    print(data["explanation"])
    for disclosure in data.get("disclosures", []):
        print(f"注意：{disclosure['reason']}")
    if data["rows"]:
        print(_text_table(data["columns"], data["rows"]))
    else:
        print("（無符合資料）")
    print(f"SQL: {data['sql']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="*", help="要查詢的中文問題")
    parser.add_argument("--json", action="store_true", help="輸出 JSON envelope")
    parser.add_argument("--serve", action="store_true", help="啟動本機 Web 服務")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.serve:
        import uvicorn

        uvicorn.run("serving.app:app", host=args.host, port=args.port, reload=False)
        return 0

    question = " ".join(args.question).strip()
    if not question:
        question = input("請輸入電力資料問題：").strip()
    if not question:
        parser.error("問題不可為空。")
    runtime = build_runtime()
    response = runtime.pipeline.query(question).to_dict()
    if response["success"] and isinstance(response.get("data"), dict):
        response["data"] = enrich_query_data(response["data"])
    return _print_response(response, as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
