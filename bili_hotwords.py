#!/usr/bin/env python3
"""Collect and report Bilibili hot search keywords."""

from __future__ import annotations

import argparse
import csv
import html
import json
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BASE_DIR / "data" / "bili_hotwords.sqlite3"
DEFAULT_REPORT_DIR = BASE_DIR / "reports"
HK_TZ = timezone(timedelta(hours=8), "Asia/Hong_Kong")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Accept": "application/json,text/plain,*/*",
}

ENDPOINTS = (
    (
        "search_square",
        "https://api.bilibili.com/x/web-interface/search/square?limit={limit}",
    ),
    (
        "main_hotword",
        "https://s.search.bilibili.com/main/hotword?mid=0&ps={limit}&jsonp=jsonp",
    ),
)


@dataclass
class FetchResult:
    endpoint_name: str
    endpoint_url: str
    status_code: int
    payload: dict[str, Any]
    items: list[dict[str, Any]]


def now_hk() -> datetime:
    return datetime.now(HK_TZ)


def parse_json_text(text: str) -> dict[str, Any]:
    body = text.strip().lstrip("\ufeff")
    if body.endswith(";"):
        body = body[:-1].strip()

    # Some JSONP variants wrap the JSON in callback(...).
    first_brace = body.find("{")
    last_brace = body.rfind("}")
    if first_brace > 0 and last_brace > first_brace:
        body = body[first_brace : last_brace + 1]

    value = json.loads(body)
    if not isinstance(value, dict):
        raise ValueError("response JSON is not an object")
    return value


def http_get_json_with_urllib(url: str, timeout: float) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        raw = response.read().decode("utf-8", errors="replace")
    return status, parse_json_text(raw)


def http_get_json_with_curl(url: str, timeout: float) -> tuple[int, dict[str, Any]]:
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        raise RuntimeError("curl is not available")

    command = [
        curl,
        "-L",
        "--silent",
        "--show-error",
        "--max-time",
        str(max(1.0, timeout)),
        "-A",
        HEADERS["User-Agent"],
        "-H",
        f"Referer: {HEADERS['Referer']}",
        "-H",
        f"Accept: {HEADERS['Accept']}",
        "-w",
        "\n__HTTP_STATUS__:%{http_code}",
        url,
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"curl failed with exit code {completed.returncode}: {message}")

    marker = "\n__HTTP_STATUS__:"
    if marker not in completed.stdout:
        raise RuntimeError("curl response did not include HTTP status")
    raw, status_text = completed.stdout.rsplit(marker, 1)
    status_code = as_int(status_text.strip(), 0)
    if status_code >= 400 or status_code == 0:
        raise RuntimeError(f"curl returned HTTP status {status_code}")
    return status_code, parse_json_text(raw)


def http_get_json(url: str, timeout: float) -> tuple[int, dict[str, Any]]:
    try:
        return http_get_json_with_urllib(url, timeout)
    except (urllib.error.URLError, TimeoutError, OSError):
        return http_get_json_with_curl(url, timeout)


def extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("code") not in (None, 0):
        raise RuntimeError(f"API returned code={payload.get('code')}: {payload.get('message')}")

    data = payload.get("data")
    if isinstance(data, dict):
        trending = data.get("trending")
        if isinstance(trending, dict) and isinstance(trending.get("list"), list):
            return [item for item in trending["list"] if isinstance(item, dict)]

    hot_list = payload.get("list")
    if isinstance(hot_list, list):
        return [item for item in hot_list if isinstance(item, dict)]

    raise RuntimeError("API response did not contain a hotword list")


def fetch_hotwords(limit: int, timeout: float) -> FetchResult:
    errors: list[str] = []

    for endpoint_name, template in ENDPOINTS:
        url = template.format(limit=limit)
        try:
            status_code, payload = http_get_json(url, timeout)
            items = extract_items(payload)
            if items:
                return FetchResult(endpoint_name, url, status_code, payload, items)
            errors.append(f"{endpoint_name}: empty list")
        except (urllib.error.URLError, TimeoutError, ValueError, RuntimeError) as exc:
            errors.append(f"{endpoint_name}: {exc}")

    raise RuntimeError("all Bilibili endpoints failed: " + " | ".join(errors))


def as_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS fetch_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at TEXT NOT NULL,
            fetched_date TEXT NOT NULL,
            endpoint_name TEXT NOT NULL,
            endpoint_url TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            item_count INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS hotword_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            fetched_at TEXT NOT NULL,
            fetched_date TEXT NOT NULL,
            rank INTEGER NOT NULL,
            keyword TEXT NOT NULL,
            show_name TEXT NOT NULL,
            heat_score INTEGER NOT NULL,
            heat_layer TEXT NOT NULL,
            hot_id INTEGER,
            word_type INTEGER,
            goto_type INTEGER,
            icon TEXT,
            raw_json TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES fetch_runs(id)
        );

        CREATE INDEX IF NOT EXISTS idx_hotword_date
            ON hotword_snapshots(fetched_date, rank);
        CREATE INDEX IF NOT EXISTS idx_hotword_keyword_date
            ON hotword_snapshots(keyword, fetched_date);
        CREATE INDEX IF NOT EXISTS idx_hotword_heat
            ON hotword_snapshots(fetched_date, heat_score DESC);
        """
    )


def save_fetch(conn: sqlite3.Connection, result: FetchResult, fetched_at: datetime) -> int:
    fetched_at_text = fetched_at.isoformat(timespec="seconds")
    fetched_date = fetched_at.date().isoformat()
    created_at = now_hk().isoformat(timespec="seconds")

    cur = conn.execute(
        """
        INSERT INTO fetch_runs (
            fetched_at, fetched_date, endpoint_name, endpoint_url,
            status_code, item_count, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fetched_at_text,
            fetched_date,
            result.endpoint_name,
            result.endpoint_url,
            result.status_code,
            len(result.items),
            created_at,
        ),
    )
    run_id = int(cur.lastrowid)

    rows = []
    for index, item in enumerate(result.items, start=1):
        keyword = as_text(item.get("keyword") or item.get("show_name")).strip()
        if not keyword:
            continue
        show_name = as_text(item.get("show_name") or keyword).strip()
        rows.append(
            (
                run_id,
                fetched_at_text,
                fetched_date,
                as_int(item.get("pos") or item.get("rank") or item.get("id"), index),
                keyword,
                show_name,
                as_int(item.get("heat_score") or item.get("score"), 0),
                as_text(item.get("heat_layer")),
                as_int(item.get("hot_id"), 0) or None,
                as_int(item.get("word_type"), 0) or None,
                as_int(item.get("goto_type"), 0) or None,
                as_text(item.get("icon")),
                json.dumps(item, ensure_ascii=False, separators=(",", ":")),
            )
        )

    conn.executemany(
        """
        INSERT INTO hotword_snapshots (
            run_id, fetched_at, fetched_date, rank, keyword, show_name,
            heat_score, heat_layer, hot_id, word_type, goto_type, icon, raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return run_id


def collect_once(db_path: Path, limit: int, timeout: float) -> int:
    fetched_at = now_hk()
    result = fetch_hotwords(limit=limit, timeout=timeout)
    with open_db(db_path) as conn:
        run_id = save_fetch(conn, result, fetched_at)

    top = result.items[0] if result.items else {}
    print(
        f"Collected {len(result.items)} keywords from {result.endpoint_name}; "
        f"top='{top.get('keyword', '')}', heat={top.get('heat_score', top.get('score', ''))}; "
        f"run_id={run_id}"
    )
    return run_id


def resolve_report_date(value: str | None) -> str:
    if not value or value == "today":
        return now_hk().date().isoformat()
    if value == "yesterday":
        return (now_hk().date() - timedelta(days=1)).isoformat()
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be today, yesterday, or YYYY-MM-DD") from exc
    return value


def load_day_rows(conn: sqlite3.Connection, report_date: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            fetched_at, rank, keyword, show_name, heat_score, heat_layer,
            hot_id, word_type, icon
        FROM hotword_snapshots
        WHERE fetched_date = ?
        ORDER BY fetched_at ASC, rank ASC
        """,
        (report_date,),
    ).fetchall()


def summarize_rows(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}

    for row in rows:
        keyword = row["keyword"]
        stat = grouped.setdefault(
            keyword,
            {
                "keyword": keyword,
                "show_name": row["show_name"] or keyword,
                "samples": 0,
                "sum_heat": 0,
                "max_heat_score": 0,
                "avg_heat_score": 0,
                "best_rank": 9999,
                "first_seen": row["fetched_at"],
                "last_seen": row["fetched_at"],
                "latest_rank": row["rank"],
                "latest_heat_score": row["heat_score"],
                "heat_layer": row["heat_layer"],
                "points": [],
            },
        )

        heat = int(row["heat_score"] or 0)
        rank = int(row["rank"] or 9999)
        stat["samples"] += 1
        stat["sum_heat"] += heat
        stat["max_heat_score"] = max(stat["max_heat_score"], heat)
        stat["best_rank"] = min(stat["best_rank"], rank)
        stat["first_seen"] = min(stat["first_seen"], row["fetched_at"])
        stat["last_seen"] = max(stat["last_seen"], row["fetched_at"])

        if row["fetched_at"] >= stat["last_seen"]:
            stat["latest_rank"] = rank
            stat["latest_heat_score"] = heat
            stat["heat_layer"] = row["heat_layer"]

        stat["points"].append((row["fetched_at"], heat, rank))

    summaries = []
    for stat in grouped.values():
        samples = max(int(stat["samples"]), 1)
        stat["avg_heat_score"] = round(stat["sum_heat"] / samples)
        # Transparent daily ordering: peak heat dominates, persistence breaks ties.
        stat["daily_score"] = (
            int(stat["max_heat_score"]) * 100
            + int(stat["avg_heat_score"]) * 10
            + int(stat["samples"]) * 1000
            + max(0, 100 - int(stat["best_rank"]))
        )
        summaries.append(stat)

    summaries.sort(
        key=lambda item: (
            -int(item["daily_score"]),
            -int(item["max_heat_score"]),
            -int(item["samples"]),
            int(item["best_rank"]),
            item["keyword"],
        )
    )
    return summaries


def format_number(value: int | float) -> str:
    return f"{int(value):,}"


def short_time(iso_text: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_text)
    except ValueError:
        return iso_text
    return dt.strftime("%H:%M")


def sparkline(points: list[tuple[str, int, int]], width: int = 150, height: int = 34) -> str:
    if not points:
        return '<span class="muted">-</span>'

    values = [max(0, int(point[1])) for point in points]
    if len(values) == 1:
        x = width // 2
        y = height // 2
        return (
            f'<svg class="spark" viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="single data point"><circle cx="{x}" cy="{y}" r="3"/></svg>'
        )

    v_min = min(values)
    v_max = max(values)
    span = max(v_max - v_min, 1)
    coords = []
    for index, value in enumerate(values):
        x = round(index * (width - 6) / (len(values) - 1) + 3, 2)
        y = round(height - 4 - ((value - v_min) / span) * (height - 8), 2)
        coords.append(f"{x},{y}")
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="heat trend"><polyline points="{" ".join(coords)}"/></svg>'
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "rank",
        "keyword",
        "show_name",
        "daily_score",
        "max_heat_score",
        "avg_heat_score",
        "samples",
        "best_rank",
        "latest_rank",
        "latest_heat_score",
        "first_seen",
        "last_seen",
        "heat_layer",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for rank, row in enumerate(rows, start=1):
            writer.writerow(
                {
                    "rank": rank,
                    "keyword": row["keyword"],
                    "show_name": row["show_name"],
                    "daily_score": row["daily_score"],
                    "max_heat_score": row["max_heat_score"],
                    "avg_heat_score": row["avg_heat_score"],
                    "samples": row["samples"],
                    "best_rank": row["best_rank"],
                    "latest_rank": row["latest_rank"],
                    "latest_heat_score": row["latest_heat_score"],
                    "first_seen": row["first_seen"],
                    "last_seen": row["last_seen"],
                    "heat_layer": row["heat_layer"],
                }
            )


def write_html_report(
    path: Path,
    report_date: str,
    rows: list[dict[str, Any]],
    snapshot_count: int,
    top_n: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    visible_rows = rows[:top_n]
    generated_at = now_hk().strftime("%Y-%m-%d %H:%M:%S %Z")
    max_heat = max([int(row["max_heat_score"]) for row in visible_rows] or [1])

    table_rows = []
    for rank, row in enumerate(visible_rows, start=1):
        bar = max(4, round(int(row["max_heat_score"]) / max_heat * 100, 2))
        keyword = html.escape(row["keyword"])
        show_name = html.escape(row["show_name"])
        layer = html.escape(str(row["heat_layer"] or ""))
        table_rows.append(
            f"""
            <tr>
              <td class="rank">{rank}</td>
              <td>
                <div class="keyword">{keyword}</div>
                <div class="sub">{show_name}</div>
              </td>
              <td>
                <div class="heat">{format_number(row["max_heat_score"])}</div>
                <div class="bar"><span style="width:{bar}%"></span></div>
              </td>
              <td>{format_number(row["avg_heat_score"])}</td>
              <td>{row["samples"]}</td>
              <td>#{row["best_rank"]}</td>
              <td>#{row["latest_rank"]}</td>
              <td>{short_time(row["first_seen"])} - {short_time(row["last_seen"])}</td>
              <td class="layer">{layer}</td>
              <td>{sparkline(row["points"])}</td>
            </tr>
            """
        )

    empty_state = ""
    if not visible_rows:
        empty_state = '<p class="empty">No snapshots were found for this date.</p>'

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>B站热词榜 {html.escape(report_date)}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #18202a;
      --muted: #647184;
      --line: #dde3ea;
      --panel: #f8fafc;
      --brand: #00a1d6;
      --brand-2: #f25d8e;
      --good: #18a058;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
      color: var(--ink);
      background: #ffffff;
    }}
    header {{
      border-bottom: 1px solid var(--line);
      background: linear-gradient(90deg, #f7fbff 0%, #fff6fa 100%);
    }}
    .wrap {{
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
    }}
    .hero {{
      padding: 28px 0 24px;
    }}
    h1 {{
      margin: 0;
      font-size: 30px;
      letter-spacing: 0;
    }}
    .meta {{
      margin-top: 10px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.7;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin: 22px 0;
    }}
    .stat {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px 16px;
      background: var(--panel);
    }}
    .stat b {{
      display: block;
      font-size: 24px;
      margin-bottom: 4px;
    }}
    .stat span {{
      color: var(--muted);
      font-size: 13px;
    }}
    main {{
      padding-bottom: 40px;
    }}
    .table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 980px;
      background: #ffffff;
    }}
    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: middle;
      font-size: 14px;
      white-space: nowrap;
    }}
    th {{
      background: #f4f7fa;
      color: #334155;
      font-weight: 650;
    }}
    tr:last-child td {{
      border-bottom: 0;
    }}
    .rank {{
      width: 56px;
      color: var(--brand-2);
      font-weight: 750;
      font-size: 18px;
    }}
    .keyword {{
      font-weight: 700;
      white-space: normal;
      min-width: 180px;
    }}
    .sub {{
      color: var(--muted);
      font-size: 12px;
      margin-top: 4px;
      white-space: normal;
    }}
    .heat {{
      font-weight: 700;
      color: #0f172a;
    }}
    .bar {{
      width: 130px;
      height: 6px;
      border-radius: 999px;
      background: #e8eef5;
      margin-top: 7px;
      overflow: hidden;
    }}
    .bar span {{
      display: block;
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--brand), var(--brand-2));
    }}
    .layer {{
      color: var(--good);
      font-weight: 700;
    }}
    .spark {{
      width: 150px;
      height: 34px;
      fill: none;
      stroke: var(--brand);
      stroke-width: 2.5;
      stroke-linecap: round;
      stroke-linejoin: round;
    }}
    .spark circle {{
      fill: var(--brand);
      stroke: none;
    }}
    .muted, .empty {{
      color: var(--muted);
    }}
    footer {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.7;
      padding: 18px 0;
    }}
    @media (max-width: 720px) {{
      .wrap {{ width: min(100% - 20px, 1180px); }}
      h1 {{ font-size: 24px; }}
      .stats {{ grid-template-columns: 1fr; }}
      th, td {{ padding: 10px 12px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap hero">
      <h1>B站热词榜</h1>
      <div class="meta">
        报告日期：{html.escape(report_date)}<br>
        生成时间：{html.escape(generated_at)}
      </div>
    </div>
  </header>
  <main class="wrap">
    <section class="stats" aria-label="summary">
      <div class="stat"><b>{len(rows)}</b><span>当日出现关键词</span></div>
      <div class="stat"><b>{snapshot_count}</b><span>采集快照</span></div>
      <div class="stat"><b>{len(visible_rows)}</b><span>报告展示条数</span></div>
    </section>
    {empty_state}
    <section class="table-wrap" aria-label="hotword table">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>关键词</th>
            <th>最高热度</th>
            <th>平均热度</th>
            <th>上榜次数</th>
            <th>最高排名</th>
            <th>最新排名</th>
            <th>出现时间</th>
            <th>层级</th>
            <th>趋势</th>
          </tr>
        </thead>
        <tbody>
          {"".join(table_rows)}
        </tbody>
      </table>
    </section>
  </main>
  <footer class="wrap">
    数据来自 B 站公开网页接口快照；每日榜由本地采集记录汇总生成。请保持低频采集，并遵守目标网站规则。
  </footer>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def build_report(db_path: Path, output_dir: Path, report_date: str, top_n: int) -> tuple[Path, Path]:
    with open_db(db_path) as conn:
        rows = load_day_rows(conn, report_date)
        snapshot_count = conn.execute(
            "SELECT COUNT(*) FROM fetch_runs WHERE fetched_date = ?",
            (report_date,),
        ).fetchone()[0]

    summaries = summarize_rows(rows)
    csv_path = output_dir / f"bili_hotwords_{report_date}.csv"
    html_path = output_dir / f"bili_hotwords_{report_date}.html"
    write_csv(csv_path, summaries)
    write_html_report(html_path, report_date, summaries, int(snapshot_count), top_n)
    print(f"Wrote CSV:  {csv_path}")
    print(f"Wrote HTML: {html_path}")
    return csv_path, html_path


def command_collect(args: argparse.Namespace) -> int:
    collect_once(args.db, args.limit, args.timeout)
    return 0


def command_report(args: argparse.Namespace) -> int:
    report_date = resolve_report_date(args.date)
    build_report(args.db, args.output_dir, report_date, args.top)
    return 0


def command_loop(args: argparse.Namespace) -> int:
    interval_seconds = max(60, int(args.interval_minutes * 60))
    run_count = 0
    while True:
        run_count += 1
        try:
            collect_once(args.db, args.limit, args.timeout)
            if args.report:
                build_report(args.db, args.output_dir, now_hk().date().isoformat(), args.top)
        except Exception as exc:  # Keep long-running collection alive.
            print(f"[{now_hk().isoformat(timespec='seconds')}] collection failed: {exc}", file=sys.stderr)

        if args.runs and run_count >= args.runs:
            break
        time.sleep(interval_seconds)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect Bilibili hot search keywords and build daily reports."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=f"SQLite database path. Default: {DEFAULT_DB}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="Fetch one hotword snapshot.")
    collect.add_argument("--limit", type=int, default=100, help="Requested keyword count.")
    collect.add_argument("--timeout", type=float, default=6.0, help="HTTP timeout in seconds.")
    collect.set_defaults(func=command_collect)

    report = subparsers.add_parser("report", help="Build a daily CSV and HTML report.")
    report.add_argument("--date", default="today", help="today, yesterday, or YYYY-MM-DD.")
    report.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help=f"Report output directory. Default: {DEFAULT_REPORT_DIR}",
    )
    report.add_argument("--top", type=int, default=50, help="Rows shown in the HTML report.")
    report.set_defaults(func=command_report)

    loop = subparsers.add_parser("loop", help="Collect repeatedly in the foreground.")
    loop.add_argument("--limit", type=int, default=100, help="Requested keyword count.")
    loop.add_argument("--timeout", type=float, default=6.0, help="HTTP timeout in seconds.")
    loop.add_argument(
        "--interval-minutes",
        type=float,
        default=10.0,
        help="Collection interval. Minimum effective value is 1 minute.",
    )
    loop.add_argument("--runs", type=int, default=0, help="Stop after N runs; 0 means forever.")
    loop.add_argument("--report", action="store_true", help="Rebuild today's report after each run.")
    loop.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help=f"Report output directory. Default: {DEFAULT_REPORT_DIR}",
    )
    loop.add_argument("--top", type=int, default=50, help="Rows shown in the HTML report.")
    loop.set_defaults(func=command_loop)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
