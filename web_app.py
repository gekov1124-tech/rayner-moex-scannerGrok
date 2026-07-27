#!/usr/bin/env python3
"""
Web UI for Rayner × MOEX Scanner.
Open the Railway URL in browser → press "Сканировать" → see results.
Also used for healthchecks and manual triggers.
"""

from __future__ import annotations
import html
import os
import threading
from datetime import datetime, timezone
from typing import Optional

from flask import Flask, request, redirect, url_for

from main import run_scan, load_config

app = Flask(__name__)

# Prevent parallel heavy scans
_scan_lock = threading.Lock()
_last_result: Optional[str] = None
_last_time: Optional[str] = None
_last_count: int = 0
_scanning: bool = False


def _setups_to_html_table(setups) -> str:
    if not setups:
        return "<p><b>Сэтапов не найдено</b> (по текущим правилам рынка).</p>"
    rows = []
    for s in setups:
        rows.append(
            "<tr>"
            f"<td><b>{html.escape(str(s.ticker))}</b></td>"
            f"<td>{html.escape(str(s.strategy))}</td>"
            f"<td>{html.escape(str(s.direction))}</td>"
            f"<td>{s.entry}</td>"
            f"<td>{s.stop}</td>"
            f"<td>{s.suggested_shares}</td>"
            f"<td>{s.score}</td>"
            f"<td style='text-align:left;max-width:360px'>{html.escape((s.reason or '')[:180])}</td>"
            "</tr>"
        )
    return (
        "<table border='1' cellpadding='6' cellspacing='0' "
        "style='border-collapse:collapse;width:100%;font-size:14px'>"
        "<thead><tr>"
        "<th>Ticker</th><th>Strategy</th><th>Dir</th>"
        "<th>Entry</th><th>Stop</th><th>Shares</th><th>Score</th><th>Reason</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


PAGE_CSS = """
body { font-family: system-ui, sans-serif; max-width: 960px; margin: 24px auto; padding: 0 16px;
       background: #0f1419; color: #e7ecf3; }
h1 { font-size: 1.4rem; }
.card { background: #1a2332; border-radius: 12px; padding: 20px; margin: 16px 0; }
.btn { display: inline-block; background: #3b82f6; color: #fff; border: none;
       padding: 12px 24px; border-radius: 8px; font-size: 16px; cursor: pointer;
       text-decoration: none; }
.btn:hover { background: #2563eb; }
.btn:disabled, .btn.disabled { background: #475569; cursor: wait; }
.muted { color: #94a3b8; font-size: 0.9rem; }
table { background: #111827; }
th { background: #1e293b; }
td, th { border-color: #334155 !important; }
a { color: #93c5fd; }
pre { background: #0b1220; padding: 12px; overflow: auto; font-size: 12px;
      border-radius: 8px; max-height: 320px; }
.ok { color: #4ade80; }
.warn { color: #fbbf24; }
"""


def _layout(body: str, title: str = "Rayner × MOEX Scanner") -> str:
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{html.escape(title)}</title>
  <style>{PAGE_CSS}</style>
</head>
<body>
  <h1>🔔 Rayner × MOEX Scanner</h1>
  <p class="muted">Образовательный сканер. Не является инвестиционной рекомендацией.</p>
  {body}
</body>
</html>"""


@app.get("/")
def index():
    global _last_result, _last_time, _last_count, _scanning
    status = (
        f"<p class='warn'>⏳ Сканирование уже идёт… обновите страницу через 1–2 минуты.</p>"
        if _scanning
        else ""
    )
    last = ""
    if _last_time:
        last = (
            f"<div class='card'><p class='ok'>Последний скан: {_last_time} "
            f"(сэтапов: {_last_count})</p>"
            f"{_last_result or ''}</div>"
        )
    body = f"""
    <div class="card">
      <p>Нажмите кнопку, чтобы <b>запустить скан сейчас</b>.</p>
      <p class="muted">Обычно занимает 1–3 минуты (данные MOEX + H4).</p>
      {status}
      <form method="post" action="/scan">
        <button class="btn" type="submit" {"disabled" if _scanning else ""}>
          ▶ Сканировать рынок
        </button>
      </form>
      <p class="muted" style="margin-top:12px">
        Быстрый скан без новостей · universe=sample<br/>
        <a href="/scan?quick=1">GET /scan?quick=1</a> ·
        <a href="/health">/health</a>
      </p>
    </div>
    {last}
    """
    return _layout(body)


@app.route("/scan", methods=["GET", "POST"])
def scan():
    global _last_result, _last_time, _last_count, _scanning

    if _scanning:
        return _layout(
            "<div class='card'><p class='warn'>Сканирование уже выполняется. "
            "Подождите и обновите <a href='/'>главную</a>.</p></div>"
        )

    quick = request.args.get("quick") == "1" or request.method == "POST"
    # POST or any /scan triggers full scan; quick skips news
    no_news = request.args.get("news") != "1"

    if not _scan_lock.acquire(blocking=False):
        return _layout(
            "<div class='card'><p class='warn'>Уже идёт другой скан.</p>"
            "<p><a href='/'>← Назад</a></p></div>"
        )

    _scanning = True
    try:
        setups, log = run_scan(
            universe=os.getenv("SCAN_UNIVERSE", "sample"),
            source="moex",
            no_news=no_news,
            max_setups=int(os.getenv("SCAN_MAX_SETUPS", "20")),
            send_telegram=True,
        )
        table = _setups_to_html_table(setups)
        _last_result = table + f"<details><summary>Лог</summary><pre>{html.escape(log)}</pre></details>"
        _last_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        _last_count = len(setups)
        body = f"""
        <div class="card">
          <p class="ok">✓ Готово · {_last_time} · найдено: <b>{_last_count}</b></p>
          <p><a href="/">← На главную</a></p>
          {table}
          <details style="margin-top:16px"><summary>Полный лог</summary>
          <pre>{html.escape(log)}</pre></details>
        </div>
        """
        return _layout(body, title=f"Скан: {_last_count} сэтапов")
    except Exception as e:
        body = f"""
        <div class="card">
          <p class="warn">Ошибка скана: {html.escape(str(e))}</p>
          <p><a href="/">← Назад</a></p>
        </div>
        """
        return _layout(body), 500
    finally:
        _scanning = False
        _scan_lock.release()


@app.get("/health")
def health():
    return {"status": "ok", "service": "rayner-moex-scanner", "scanning": _scanning}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
