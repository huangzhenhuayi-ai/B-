#!/usr/bin/env python3
"""Local web dashboard for Bilibili hotword snapshots."""

from __future__ import annotations

import argparse
import json
import sqlite3
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import bili_hotwords


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>B站热词榜看板</title>
  <style>
    :root {
      --bg: #f5f7fb;
      --surface: #ffffff;
      --ink: #142033;
      --muted: #65758b;
      --line: #dce3ec;
      --blue: #00a1d6;
      --pink: #f25d8e;
      --green: #18a058;
      --amber: #b7791f;
      --shadow: 0 10px 30px rgba(20, 32, 51, 0.08);
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; }
    body {
      font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
      background: var(--bg);
      color: var(--ink);
      letter-spacing: 0;
    }
    button, select, input {
      font: inherit;
    }
    button {
      border: 1px solid var(--line);
      border-radius: 7px;
      min-height: 36px;
      padding: 0 13px;
      color: var(--ink);
      background: var(--surface);
      cursor: pointer;
    }
    button:hover { border-color: #aab8c8; }
    button.primary {
      border-color: var(--blue);
      color: #ffffff;
      background: var(--blue);
    }
    button:disabled {
      cursor: wait;
      opacity: 0.64;
    }
    select {
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 0 10px;
      background: var(--surface);
      color: var(--ink);
    }
    .shell {
      width: min(1280px, calc(100% - 28px));
      margin: 0 auto;
      padding: 18px 0 34px;
    }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 14px 0 18px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 11px;
      min-width: 0;
    }
    .mark {
      width: 34px;
      height: 34px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      color: #ffffff;
      font-weight: 800;
      background: linear-gradient(135deg, var(--blue), var(--pink));
      flex: 0 0 auto;
    }
    h1 {
      margin: 0;
      font-size: 21px;
      line-height: 1.2;
    }
    .stamp {
      color: var(--muted);
      font-size: 12px;
      margin-top: 4px;
    }
    .controls {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      flex-wrap: wrap;
      gap: 9px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 14px;
    }
    .metric {
      grid-column: span 3;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px 15px;
      box-shadow: var(--shadow);
      min-height: 94px;
    }
    .metric .label {
      color: var(--muted);
      font-size: 12px;
    }
    .metric .value {
      margin-top: 10px;
      font-size: 28px;
      line-height: 1;
      font-weight: 750;
      white-space: nowrap;
    }
    .metric .sub {
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
      min-height: 16px;
    }
    .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      min-width: 0;
    }
    .panel-head {
      height: 52px;
      padding: 0 15px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .panel-title {
      font-size: 14px;
      font-weight: 750;
    }
    .panel-note {
      color: var(--muted);
      font-size: 12px;
    }
    .bars { grid-column: span 5; }
    .trend { grid-column: span 7; }
    .table-panel { grid-column: span 12; }
    .chart-body {
      height: 360px;
      padding: 14px 15px;
    }
    .bar-list {
      display: grid;
      grid-auto-rows: minmax(30px, auto);
      gap: 8px;
    }
    .bar-row {
      display: grid;
      grid-template-columns: 34px minmax(110px, 1fr) 92px;
      gap: 10px;
      align-items: center;
      min-height: 30px;
    }
    .bar-rank {
      color: var(--pink);
      font-weight: 800;
      text-align: right;
    }
    .bar-track {
      height: 10px;
      background: #e8eef5;
      border-radius: 999px;
      overflow: hidden;
      position: relative;
    }
    .bar-fill {
      height: 100%;
      min-width: 2px;
      background: linear-gradient(90deg, var(--blue), var(--pink));
      border-radius: 999px;
    }
    .bar-name {
      font-size: 13px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      margin-bottom: 5px;
    }
    .bar-value {
      text-align: right;
      color: var(--muted);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }
    .trend svg {
      width: 100%;
      height: 100%;
      display: block;
    }
    .axis {
      stroke: #c8d2df;
      stroke-width: 1;
    }
    .line {
      fill: none;
      stroke: var(--blue);
      stroke-width: 3;
      stroke-linejoin: round;
      stroke-linecap: round;
    }
    .area {
      fill: rgba(0, 161, 214, 0.12);
    }
    .dot {
      fill: var(--pink);
      stroke: #ffffff;
      stroke-width: 2;
    }
    .empty {
      height: 100%;
      display: grid;
      place-items: center;
      color: var(--muted);
      font-size: 14px;
      text-align: center;
    }
    .table-scroll {
      overflow-x: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 1050px;
    }
    th, td {
      padding: 11px 13px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      white-space: nowrap;
      font-size: 13px;
      vertical-align: middle;
    }
    th {
      color: #334155;
      background: #f7f9fc;
      font-weight: 700;
    }
    tr:last-child td { border-bottom: 0; }
    .rank {
      color: var(--pink);
      font-weight: 800;
      font-size: 16px;
    }
    .keyword {
      max-width: 260px;
      white-space: normal;
      font-weight: 700;
      line-height: 1.35;
    }
    .muted { color: var(--muted); }
    .good { color: var(--green); font-weight: 700; }
    .warn { color: var(--amber); font-weight: 700; }
    .mini {
      width: 130px;
      height: 28px;
    }
    .mini polyline {
      fill: none;
      stroke: var(--blue);
      stroke-width: 2.3;
      stroke-linecap: round;
      stroke-linejoin: round;
    }
    .toast {
      position: fixed;
      right: 18px;
      bottom: 18px;
      width: min(380px, calc(100% - 36px));
      padding: 13px 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      background: var(--surface);
      color: var(--ink);
      transform: translateY(120%);
      opacity: 0;
      transition: transform 160ms ease, opacity 160ms ease;
      z-index: 20;
      font-size: 13px;
      line-height: 1.5;
    }
    .toast.show {
      transform: translateY(0);
      opacity: 1;
    }
    @media (max-width: 980px) {
      .metric { grid-column: span 6; }
      .bars, .trend { grid-column: span 12; }
      .chart-body { height: 330px; }
    }
    @media (max-width: 700px) {
      .shell { width: min(100% - 18px, 1280px); padding-top: 8px; }
      .topbar { align-items: flex-start; flex-direction: column; }
      .controls { width: 100%; justify-content: flex-start; }
      .controls > * { flex: 1 1 auto; }
      button, select { min-width: 0; }
      .metric { grid-column: span 12; }
      .metric .value { font-size: 24px; }
      .panel-head { align-items: flex-start; flex-direction: column; height: auto; padding: 12px 13px; }
      .chart-body { height: 300px; padding: 12px; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="brand">
        <div class="mark">B</div>
        <div>
          <h1>B站热词榜看板</h1>
          <div class="stamp" id="stamp">-</div>
        </div>
      </div>
      <div class="controls">
        <select id="dateSelect" aria-label="日期"></select>
        <select id="topSelect" aria-label="展示条数">
          <option value="20">Top 20</option>
          <option value="50" selected>Top 50</option>
          <option value="100">Top 100</option>
        </select>
        <button id="refreshBtn">刷新</button>
        <button id="collectBtn" class="primary">采集</button>
      </div>
    </header>

    <section class="grid" aria-label="指标">
      <div class="metric">
        <div class="label">关键词</div>
        <div class="value" id="metricKeywords">-</div>
        <div class="sub" id="metricKeywordsSub">-</div>
      </div>
      <div class="metric">
        <div class="label">采集快照</div>
        <div class="value" id="metricSnapshots">-</div>
        <div class="sub" id="metricSnapshotsSub">-</div>
      </div>
      <div class="metric">
        <div class="label">最高热度</div>
        <div class="value" id="metricHeat">-</div>
        <div class="sub" id="metricHeatSub">-</div>
      </div>
      <div class="metric">
        <div class="label">榜首</div>
        <div class="value" id="metricTop">-</div>
        <div class="sub" id="metricTopSub">-</div>
      </div>
    </section>

    <section class="grid" style="margin-top:14px" aria-label="图表">
      <div class="panel bars">
        <div class="panel-head">
          <div class="panel-title">最高热度排行</div>
          <div class="panel-note" id="barsNote">-</div>
        </div>
        <div class="chart-body" id="barsChart"></div>
      </div>
      <div class="panel trend">
        <div class="panel-head">
          <div class="panel-title">榜首热度趋势</div>
          <div class="panel-note" id="trendNote">-</div>
        </div>
        <div class="chart-body" id="trendChart"></div>
      </div>
    </section>

    <section class="grid" style="margin-top:14px" aria-label="榜单">
      <div class="panel table-panel">
        <div class="panel-head">
          <div class="panel-title">每日榜单</div>
          <div class="panel-note" id="tableNote">-</div>
        </div>
        <div class="table-scroll">
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
                <th>首次出现</th>
                <th>最后出现</th>
                <th>层级</th>
                <th>趋势</th>
              </tr>
            </thead>
            <tbody id="tableBody"></tbody>
          </table>
        </div>
      </div>
    </section>
  </div>
  <div class="toast" id="toast"></div>

  <script>
    const state = {
      date: "",
      top: 50,
      rows: [],
      snapshotCount: 0,
      loading: false
    };

    const $ = (id) => document.getElementById(id);
    const number = (value) => Number(value || 0).toLocaleString("zh-CN");

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[ch]));
    }

    function shortTime(value) {
      if (!value) return "-";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return String(value).slice(11, 16) || String(value);
      return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
    }

    function showToast(message) {
      const toast = $("toast");
      toast.textContent = message;
      toast.classList.add("show");
      window.clearTimeout(showToast.timer);
      showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 3200);
    }

    function setBusy(isBusy) {
      state.loading = isBusy;
      $("collectBtn").disabled = isBusy;
      $("refreshBtn").disabled = isBusy;
      $("collectBtn").textContent = isBusy ? "采集中" : "采集";
    }

    async function api(path, options) {
      const response = await fetch(path, options);
      const payload = await response.json();
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.error || `HTTP ${response.status}`);
      }
      return payload;
    }

    async function loadDates() {
      const payload = await api("/api/dates");
      const select = $("dateSelect");
      select.innerHTML = "";
      const dates = payload.dates.length ? payload.dates : [payload.today];
      for (const date of dates) {
        const option = document.createElement("option");
        option.value = date;
        option.textContent = date;
        select.appendChild(option);
      }
      state.date = payload.latest_date || payload.today;
      select.value = state.date;
    }

    async function loadSummary() {
      const params = new URLSearchParams({ date: state.date, top: String(state.top) });
      const payload = await api(`/api/summary?${params}`);
      state.rows = payload.rows;
      state.snapshotCount = payload.snapshot_count;
      render(payload);
    }

    function render(payload) {
      const rows = payload.rows || [];
      const top = rows[0];
      $("stamp").textContent = `${payload.date} · ${payload.generated_at}`;
      $("metricKeywords").textContent = number(payload.keyword_count);
      $("metricKeywordsSub").textContent = rows.length ? `展示 ${number(rows.length)} 条` : "-";
      $("metricSnapshots").textContent = number(payload.snapshot_count);
      $("metricSnapshotsSub").textContent = payload.first_snapshot && payload.last_snapshot
        ? `${shortTime(payload.first_snapshot)} - ${shortTime(payload.last_snapshot)}`
        : "-";
      $("metricHeat").textContent = top ? number(top.max_heat_score) : "-";
      $("metricHeatSub").textContent = top ? top.keyword : "-";
      $("metricTop").textContent = top ? `#${top.best_rank}` : "-";
      $("metricTopSub").textContent = top ? top.keyword : "-";
      $("barsNote").textContent = rows.length ? `${rows.length} 条` : "-";
      $("trendNote").textContent = top ? top.keyword : "-";
      $("tableNote").textContent = rows.length ? `${payload.date}` : "-";

      renderBars(rows.slice(0, 12));
      renderTrend(top);
      renderTable(rows);
    }

    function renderBars(rows) {
      const root = $("barsChart");
      if (!rows.length) {
        root.innerHTML = '<div class="empty">暂无数据</div>';
        return;
      }
      const max = Math.max(...rows.map((row) => row.max_heat_score || 0), 1);
      root.innerHTML = `<div class="bar-list">${
        rows.map((row, index) => {
          const width = Math.max(2, Math.round((row.max_heat_score || 0) / max * 100));
          return `<div class="bar-row">
            <div class="bar-rank">${index + 1}</div>
            <div>
              <div class="bar-name" title="${escapeHtml(row.keyword)}">${escapeHtml(row.keyword)}</div>
              <div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div>
            </div>
            <div class="bar-value">${number(row.max_heat_score)}</div>
          </div>`;
        }).join("")
      }</div>`;
    }

    function scalePoints(points, width, height, pad) {
      const values = points.map((point) => Number(point.heat_score || 0));
      const min = Math.min(...values);
      const max = Math.max(...values);
      const span = Math.max(max - min, 1);
      return points.map((point, index) => {
        const x = points.length === 1
          ? width / 2
          : pad + index * (width - pad * 2) / (points.length - 1);
        const y = height - pad - ((Number(point.heat_score || 0) - min) / span) * (height - pad * 2);
        return { x, y, heat: Number(point.heat_score || 0), time: point.fetched_at };
      });
    }

    function renderTrend(row) {
      const root = $("trendChart");
      const points = row?.points || [];
      if (!points.length) {
        root.innerHTML = '<div class="empty">暂无数据</div>';
        return;
      }
      const width = 720;
      const height = 300;
      const pad = 34;
      const scaled = scalePoints(points, width, height, pad);
      const line = scaled.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
      const area = `${pad},${height - pad} ${line} ${width - pad},${height - pad}`;
      const labels = scaled.filter((_, index) => {
        if (scaled.length <= 4) return true;
        return index === 0 || index === scaled.length - 1 || index === Math.floor((scaled.length - 1) / 2);
      });
      root.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="trend">
        <line class="axis" x1="${pad}" y1="${height - pad}" x2="${width - pad}" y2="${height - pad}"></line>
        <line class="axis" x1="${pad}" y1="${pad}" x2="${pad}" y2="${height - pad}"></line>
        ${scaled.length > 1 ? `<polygon class="area" points="${area}"></polygon><polyline class="line" points="${line}"></polyline>` : ""}
        ${scaled.map((point) => `<circle class="dot" cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="4">
          <title>${shortTime(point.time)} · ${number(point.heat)}</title>
        </circle>`).join("")}
        ${labels.map((point) => `<text x="${point.x.toFixed(1)}" y="${height - 8}" text-anchor="middle" fill="#65758b" font-size="12">${shortTime(point.time)}</text>`).join("")}
      </svg>`;
    }

    function miniSpark(points) {
      if (!points?.length) return '<span class="muted">-</span>';
      const width = 130;
      const height = 28;
      const pad = 3;
      const scaled = scalePoints(points, width, height, pad);
      const line = scaled.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
      return `<svg class="mini" viewBox="0 0 ${width} ${height}" aria-hidden="true"><polyline points="${line}"></polyline></svg>`;
    }

    function renderTable(rows) {
      const body = $("tableBody");
      if (!rows.length) {
        body.innerHTML = '<tr><td colspan="11" class="muted">暂无数据</td></tr>';
        return;
      }
      body.innerHTML = rows.map((row, index) => `<tr>
        <td class="rank">${index + 1}</td>
        <td><div class="keyword">${escapeHtml(row.keyword)}</div></td>
        <td>${number(row.max_heat_score)}</td>
        <td>${number(row.avg_heat_score)}</td>
        <td>${number(row.samples)}</td>
        <td>#${row.best_rank}</td>
        <td>#${row.latest_rank}</td>
        <td>${shortTime(row.first_seen)}</td>
        <td>${shortTime(row.last_seen)}</td>
        <td class="${row.heat_layer === "S" ? "warn" : "good"}">${escapeHtml(row.heat_layer || "-")}</td>
        <td>${miniSpark(row.points)}</td>
      </tr>`).join("");
    }

    async function refresh() {
      try {
        setBusy(true);
        await loadSummary();
      } catch (error) {
        showToast(error.message);
      } finally {
        setBusy(false);
      }
    }

    async function collectNow() {
      try {
        setBusy(true);
        const payload = await api("/api/collect", { method: "POST" });
        showToast(`已采集 ${payload.item_count} 条，run_id=${payload.run_id}`);
        await loadDates();
        await loadSummary();
      } catch (error) {
        showToast(error.message);
      } finally {
        setBusy(false);
      }
    }

    $("dateSelect").addEventListener("change", async (event) => {
      state.date = event.target.value;
      await refresh();
    });
    $("topSelect").addEventListener("change", async (event) => {
      state.top = Number(event.target.value);
      await refresh();
    });
    $("refreshBtn").addEventListener("click", refresh);
    $("collectBtn").addEventListener("click", collectNow);

    (async function start() {
      try {
        setBusy(true);
        await loadDates();
        await loadSummary();
      } catch (error) {
        showToast(error.message);
      } finally {
        setBusy(false);
      }
    })();
  </script>
</body>
</html>
"""


class DashboardServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler_class: type[BaseHTTPRequestHandler],
        db_path: Path,
        report_dir: Path,
    ) -> None:
        super().__init__(server_address, request_handler_class)
        self.db_path = db_path
        self.report_dir = report_dir


class Handler(BaseHTTPRequestHandler):
    server: DashboardServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self.send_html(INDEX_HTML)
            elif parsed.path == "/api/dates":
                self.send_json(self.get_dates())
            elif parsed.path == "/api/summary":
                query = parse_qs(parsed.query)
                date = query.get("date", [bili_hotwords.now_hk().date().isoformat()])[0]
                top = max(1, min(200, int(query.get("top", ["50"])[0])))
                self.send_json(self.get_summary(date, top))
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/collect":
                run_id = bili_hotwords.collect_once(self.server.db_path, limit=50, timeout=6.0)
                report_date = bili_hotwords.now_hk().date().isoformat()
                bili_hotwords.build_report(self.server.db_path, self.server.report_dir, report_date, 50)
                with bili_hotwords.open_db(self.server.db_path) as conn:
                    item_count = conn.execute(
                        "SELECT item_count FROM fetch_runs WHERE id = ?",
                        (run_id,),
                    ).fetchone()[0]
                self.send_json({"ok": True, "run_id": run_id, "item_count": item_count})
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def send_html(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def get_dates(self) -> dict[str, Any]:
        today = bili_hotwords.now_hk().date().isoformat()
        if not self.server.db_path.exists():
            return {"ok": True, "today": today, "latest_date": today, "dates": []}

        with bili_hotwords.open_db(self.server.db_path) as conn:
            rows = conn.execute(
                "SELECT DISTINCT fetched_date FROM fetch_runs ORDER BY fetched_date DESC"
            ).fetchall()
        dates = [row[0] for row in rows]
        return {
            "ok": True,
            "today": today,
            "latest_date": dates[0] if dates else today,
            "dates": dates,
        }

    def get_summary(self, date: str, top: int) -> dict[str, Any]:
        with bili_hotwords.open_db(self.server.db_path) as conn:
            raw_rows = bili_hotwords.load_day_rows(conn, date)
            snapshot_count = conn.execute(
                "SELECT COUNT(*) FROM fetch_runs WHERE fetched_date = ?",
                (date,),
            ).fetchone()[0]

        summaries = bili_hotwords.summarize_rows(raw_rows)
        visible = [serialize_summary(row) for row in summaries[:top]]
        first_snapshot = min([row["fetched_at"] for row in raw_rows], default="")
        last_snapshot = max([row["fetched_at"] for row in raw_rows], default="")
        return {
            "ok": True,
            "date": date,
            "generated_at": bili_hotwords.now_hk().strftime("%Y-%m-%d %H:%M:%S"),
            "snapshot_count": int(snapshot_count),
            "keyword_count": len(summaries),
            "first_snapshot": first_snapshot,
            "last_snapshot": last_snapshot,
            "rows": visible,
        }


def serialize_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "keyword": row["keyword"],
        "show_name": row["show_name"],
        "daily_score": int(row["daily_score"]),
        "max_heat_score": int(row["max_heat_score"]),
        "avg_heat_score": int(row["avg_heat_score"]),
        "samples": int(row["samples"]),
        "best_rank": int(row["best_rank"]),
        "latest_rank": int(row["latest_rank"]),
        "latest_heat_score": int(row["latest_heat_score"]),
        "first_seen": row["first_seen"],
        "last_seen": row["last_seen"],
        "heat_layer": row["heat_layer"],
        "points": [
            {"fetched_at": point[0], "heat_score": int(point[1]), "rank": int(point[2])}
            for point in row["points"]
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Bilibili hotword dashboard.")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host. Default: {DEFAULT_HOST}")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port. Default: {DEFAULT_PORT}")
    parser.add_argument("--db", type=Path, default=bili_hotwords.DEFAULT_DB, help="SQLite database path.")
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=bili_hotwords.DEFAULT_REPORT_DIR,
        help="Report output directory.",
    )
    parser.add_argument("--open", action="store_true", help="Open the dashboard in the default browser.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    server = DashboardServer((args.host, args.port), Handler, args.db, args.report_dir)
    url = f"http://{args.host}:{args.port}/"
    print(f"Dashboard: {url}")
    if args.open:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
