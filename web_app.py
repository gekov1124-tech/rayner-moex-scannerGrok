#!/usr/bin/env python3
"""
Rayner × MOEX — Web UI + background session monitor + charts.
"""

from __future__ import annotations
import html
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from flask import Flask, Response, jsonify, request

from main import load_config, run_scan
from monitor.worker import monitor
from monitor.session import session_status, now_msk

app = Flask(__name__)

_scan_lock = threading.Lock()
_last_result_html: Optional[str] = None
_last_time: Optional[str] = None
_last_count: int = 0
_last_setups_json: List[dict] = []
_scanning: bool = False

# TradingView continuous symbols for popular FORTS roots
TV_FUT_MAP = {
    "Si": "MOEX:SI1!",
    "RI": "MOEX:RI1!",
    "RTS": "MOEX:RI1!",
    "MX": "MOEX:MX1!",
    "MIX": "MOEX:MX1!",
    "BR": "MOEX:BR1!",
    "GD": "MOEX:GD1!",
    "GOLD": "MOEX:GD1!",
    "NG": "MOEX:NG1!",
    "Eu": "MOEX:EU1!",
    "ED": "MOEX:ED1!",
    "SR": "MOEX:SR1!",
    "SBRF": "MOEX:SR1!",
    "GZ": "MOEX:GZ1!",
    "GAZR": "MOEX:GZ1!",
    "LK": "MOEX:LK1!",
    "LKOH": "MOEX:LK1!",
}


def _tv_symbol(ticker: str) -> str:
    """Map MOEX ticker / FORTS SECID to TradingView symbol."""
    t = (ticker or "").upper()
    # Pure share
    if t.isalpha() and len(t) <= 5:
        return f"MOEX:{t}"
    # Futures SECID like SiU6, BRQ6, SRU6
    for root, sym in TV_FUT_MAP.items():
        if t.startswith(root.upper()) or t.startswith(root):
            return sym
    # letter prefix before digit
    import re
    m = re.match(r"^([A-Za-z]+)", ticker or "")
    if m:
        root = m.group(1)
        if root in TV_FUT_MAP:
            return TV_FUT_MAP[root]
        if len(root) <= 5:
            return f"MOEX:{root}"
    return f"MOEX:{ticker}"


PAGE_CSS = """
:root { --bg:#0f1419; --card:#1a2332; --text:#e7ecf3; --muted:#94a3b8; --acc:#3b82f6; --ok:#4ade80; --warn:#fbbf24; }
* { box-sizing: border-box; }
body { font-family: system-ui, -apple-system, sans-serif; max-width: 1100px; margin: 0 auto;
       padding: 20px 16px 48px; background: var(--bg); color: var(--text); }
h1 { font-size: 1.35rem; margin: 0 0 8px; }
h2 { font-size: 1.1rem; margin: 0 0 12px; }
.card { background: var(--card); border-radius: 12px; padding: 18px 20px; margin: 14px 0; }
.btn { display: inline-block; background: var(--acc); color: #fff; border: none;
       padding: 11px 20px; border-radius: 8px; font-size: 15px; cursor: pointer;
       text-decoration: none; margin: 4px 6px 4px 0; }
.btn:hover { filter: brightness(1.08); }
.btn.secondary { background: #334155; }
.btn:disabled { background: #475569; cursor: wait; }
.muted { color: var(--muted); font-size: 0.9rem; }
.ok { color: var(--ok); }
.warn { color: var(--warn); }
table { width: 100%; border-collapse: collapse; font-size: 13px; background: #111827; }
th, td { border: 1px solid #334155; padding: 7px 8px; }
th { background: #1e293b; text-align: left; }
a { color: #93c5fd; }
.badge { display:inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px;
         background: #334155; margin-right: 6px; }
.badge.open { background: #14532d; color: #86efac; }
.badge.closed { background: #44403c; color: #fcd34d; }
#tv_chart { height: 520px; width: 100%; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 720px) { .grid { grid-template-columns: 1fr; } }
pre { background: #0b1220; padding: 12px; overflow: auto; font-size: 12px;
      border-radius: 8px; max-height: 280px; }
"""


def _layout(body: str, title: str = "Rayner × MOEX") -> str:
    return f"""<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(title)}</title>
<style>{PAGE_CSS}</style>
</head><body>
{body}
</body></html>"""


def _setups_table(setups: list, with_chart_links: bool = True) -> str:
    if not setups:
        return "<p><b>Сэтапов нет</b> — по текущим правилам сигналов не найдено.</p>"
    rows = []
    for s in setups:
        chart = ""
        if with_chart_links:
            chart = f"<a href='/chart/{html.escape(s.ticker)}'>📊 график</a>"
        direction = "🟢 LONG" if s.direction == "long" else "🔴 SHORT"
        plan = getattr(s, "scale_plan", "") or ""
        if not plan and getattr(s, "targets", None):
            from strategies.base import format_targets_ru
            plan = format_targets_ru(s.targets, s.exit_rule)
        rows.append(
            "<tr>"
            f"<td><b>{html.escape(str(s.ticker))}</b><br/>{chart}</td>"
            f"<td>{html.escape(str(s.strategy))}</td>"
            f"<td>{direction}</td>"
            f"<td>{s.entry}</td>"
            f"<td>{s.stop}</td>"
            f"<td>{s.suggested_shares}</td>"
            f"<td>{s.score:.1f}</td>"
            f"<td style='text-align:left;max-width:260px'>{html.escape((s.reason or '')[:120])}"
            f"<div style='color:#86efac;font-size:11px;margin-top:4px'>{html.escape((getattr(s,'value_zone_label','') or '')[:80])}</div></td>"
            f"<td style='text-align:left;max-width:240px;font-size:12px'>{html.escape(plan[:150])}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Тикер</th><th>Стратегия</th><th>Напр.</th>"
        "<th>Entry</th><th>Stop</th><th>Lots/Shares</th><th>Score</th><th>Причина</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )



@app.get("/test_telegram")
@app.route("/test_telegram", methods=["GET", "POST"])
def test_telegram():
    """One-click Telegram connectivity check."""
    from notify.telegram_alerts import send_test_message
    result = send_test_message()
    if result.get("sent"):
        body = f"""
        <div class="card">
          <p class="ok">✅ Тестовое сообщение отправлено в Telegram.</p>
          <p class="muted">chat_id: {html.escape(str(result.get('chat_id_preview')))} ·
             token: {html.escape(str(result.get('token_prefix')))}</p>
          <p><a class="btn" href="/">← На главную</a></p>
        </div>
        """
    else:
        body = f"""
        <div class="card">
          <p class="warn">❌ Telegram не отправил сообщение.</p>
          <p>{html.escape(str(result.get('error') or 'Смотрите логи Railway: строки [telegram]'))}</p>
          <p class="muted">token_set={result.get('token_set')} · chat_id_set={result.get('chat_id_set')}</p>
          <p class="muted">1) Проверьте Variables · 2) Напишите боту /start ·
             3) Для группы CHAT_ID часто с минусом (−100…)</p>
          <p><a class="btn" href="/">← На главную</a></p>
        </div>
        """
    return _layout(body, title="Тест Telegram")


@app.get("/")
def index():
    st = monitor.status()
    badge = (
        "<span class='badge open'>● Сессия открыта</span>"
        if st.get("session_open")
        else "<span class='badge closed'>○ Сессия закрыта</span>"
    )
    mon = (
        f"<span class='badge open'>монитор ON · каждые {st.get('interval_minutes')} мин</span>"
        if st.get("monitor_enabled") and st.get("monitor_running")
        else "<span class='badge closed'>монитор OFF</span>"
    )
    setups = monitor.last_setups or []
    table = _setups_table(setups) if setups else (
        _last_result_html or "<p class='muted'>Ещё не было скана. Нажмите кнопку ниже.</p>"
    )
    if setups:
        table = _setups_table(setups)

    body = f"""
    <h1>🔔 Rayner × MOEX Scanner</h1>
    <p class="muted">Мониторинг с открытия · Telegram при новых сигналах · графики в браузере</p>

    <div class="card">
      <div>{badge} {mon}</div>
      <p class="muted" style="margin-top:10px">
        МСК сейчас: <b>{html.escape(str(st.get('msk_now')))}</b><br/>
        Окно сессии: {html.escape(str(st.get('session_start')))}–{html.escape(str(st.get('session_end')))} ·
        Universe: <b>{html.escape(str(st.get('universe')))}</b><br/>
        Последний скан: {html.escape(str(st.get('last_scan_at') or '—'))} ·
        сэтапов: {st.get('last_scan_count', 0)} · новых: {st.get('last_new_count', 0)}
        {" · <span class='warn'>err: " + html.escape(str(st.get('last_error'))) + "</span>" if st.get("last_error") else ""}
      </p>
      <form method="post" action="/scan" style="margin-top:12px">
        <button class="btn" type="submit" {"disabled" if _scanning else ""}>
          ▶ Сканировать сейчас
        </button>
        <a class="btn secondary" href="/status">Статус JSON</a>
        <a class="btn secondary" href="/charts">Все графики</a>
        <a class="btn secondary" href="/journal">📒 Журнал</a>
        <a class="btn secondary" href="/test_telegram">Тест Telegram</a>
      </form>
      <p class="muted">В торговые часы монитор сам сканирует и шлёт <b>только новые</b> сэтапы в Telegram.</p>
    </div>

    <div class="card">
      <h2>Последние сэтапы</h2>
      {table}
    </div>

    <p class="muted">Образовательный инструмент. Не является инвестиционной рекомендацией.</p>
    """
    return _layout(body)


def _run_scan_background(force_telegram_all: bool = True):
    """Heavy scan in background thread — avoids Railway HTTP timeout."""
    global _scanning, _last_result_html, _last_time, _last_count, _last_setups_json
    try:
        print("[scan] background scan started")
        result = monitor.run_once(force=True, send_telegram=True)
        setups = result.get("setups") or []
        _last_count = len(setups)
        _last_time = result.get("at") or now_msk().strftime("%Y-%m-%d %H:%M:%S")
        _last_result_html = _setups_table(setups)
        _last_setups_json = [s.to_dict() for s in setups]

        # Manual / forced: always send FULL snapshot so user sees something in TG
        if force_telegram_all:
            try:
                from notify.telegram_alerts import (
                    send_setups_alert,
                    send_telegram_message,
                    is_telegram_configured,
                )
                if is_telegram_configured():
                    if setups:
                        ok = send_setups_alert(
                            setups,
                            title=f"Ручной скан MOEX ({_last_time})",
                        )
                        print(f"[scan] manual Telegram full snapshot sent={ok} n={len(setups)}")
                    else:
                        ok = send_telegram_message(
                            f"<b>Ручной скан MOEX ({_last_time})</b>\n\n"
                            "Сэтапов по текущим правилам не найдено."
                        )
                        print(f"[scan] manual Telegram empty notice sent={ok}")
                else:
                    print("[scan] Telegram не настроен — пропуск отправки")
            except Exception as e:
                print(f"[scan] manual TG error: {e}")

        if result.get("error"):
            print(f"[scan] finished with error: {result['error']}")
        else:
            print(f"[scan] finished total={result.get('total')} new={result.get('new')}")
    except Exception as e:
        print(f"[scan] background exception: {e}")
        import traceback
        traceback.print_exc()
        monitor.last_error = str(e)
    finally:
        _scanning = False
        try:
            _scan_lock.release()
        except Exception:
            pass


@app.route("/scan", methods=["GET", "POST"])
def scan():
    global _scanning

    if _scanning:
        return _layout(
            "<div class='card'>"
            "<p class='warn'>⏳ Скан уже идёт (1–3 мин).</p>"
            "<p>Страница обновится сама. Или <a href='/'>откройте главную</a>.</p>"
            "<meta http-equiv='refresh' content='15;url=/' />"
            "</div>"
        )

    if not _scan_lock.acquire(blocking=False):
        return _layout(
            "<div class='card'><p class='warn'>Занят другой скан.</p>"
            "<p><a href='/'>← Назад</a></p></div>"
        )

    _scanning = True
    # Always force full Telegram snapshot for button/API trigger
    th = threading.Thread(
        target=_run_scan_background,
        kwargs={"force_telegram_all": True},
        name="manual-scan",
        daemon=True,
    )
    th.start()

    body = """
    <div class="card">
      <p class="ok">⏳ Скан запущен в фоне</p>
      <p>Обычно 1–3 минуты (акции + фьючерсы + H4). Не закрывайте сервис.</p>
      <p>После завершения сэтапы появятся на главной, полный список уйдёт в Telegram.</p>
      <p class="muted">Страница обновится через 20 сек…</p>
      <p><a class="btn" href="/">← На главную</a>
         <a class="btn secondary" href="/test_telegram">Тест Telegram</a></p>
      <meta http-equiv="refresh" content="20;url=/" />
    </div>
    """
    return _layout(body, title="Скан запущен")



@app.get("/api/aov/<ticker>")
def api_aov(ticker: str):
    """Area of Value levels for chart overlays."""
    from data.moex_fetcher import fetch_ohlcv
    from data.universe import classify_instrument
    from data.structure import compute_area_of_value
    ticker = ticker.strip()
    fut = {ticker} if classify_instrument(ticker) == "futures" else set()
    try:
        data = fetch_ohlcv(
            [ticker], source="moex", lookback_days=250, use_cache=True, futures_tickers=fut
        )
        df = data.get(ticker)
        aov = compute_area_of_value(df) if df is not None else {}
        # merge setup targets if any
        for s in monitor.last_setups or []:
            if s.ticker == ticker:
                aov["entry"] = s.entry
                aov["stop"] = s.stop
                aov["targets"] = getattr(s, "targets", []) or []
                aov["scale_plan"] = getattr(s, "scale_plan", "") or ""
                aov["reason"] = s.reason or ""
                aov["value_zone_label"] = getattr(s, "value_zone_label", "") or aov.get("zone_label")
                if getattr(s, "aov_levels", None):
                    aov["levels"] = s.aov_levels
                break
        return jsonify(aov)
    except Exception as e:
        return jsonify({"error": str(e), "levels": []}), 500


@app.get("/chart/<ticker>")
def chart(ticker: str):
    ticker = ticker.strip()
    tv = _tv_symbol(ticker)
    # Find setup levels if any
    entry = stop = None
    reason = ""
    scale_plan = ""
    aov_label = ""
    zone_low = zone_high = None
    target_lines_js = ""
    for s in monitor.last_setups or []:
        if s.ticker == ticker:
            entry, stop = s.entry, s.stop
            reason = s.reason or ""
            scale_plan = getattr(s, "scale_plan", "") or ""
            aov_label = getattr(s, "value_zone_label", "") or ""
            zone_low = getattr(s, "value_zone_low", None) or None
            zone_high = getattr(s, "value_zone_high", None) or None
            if zone_low == 0:
                zone_low = None
            if zone_high == 0:
                zone_high = None
            colors = ["#22c55e", "#14b8a6", "#a3e635"]
            tjs = []
            for i, tg in enumerate(getattr(s, "targets", None) or []):
                c = colors[i % len(colors)]
                lab = tg.get("label", f"TP{i+1}")
                tjs.append(
                    f"series.createPriceLine({{ price: {tg['price']}, color: '{c}', "
                    f"lineWidth: 1, lineStyle: 2, title: '{lab}' }});"
                )
            target_lines_js = "\n      ".join(tjs)
            break

    zone_html = ""
    if aov_label or (zone_low and zone_high):
        zone_html = (
            f"<p>🟩 <b>Зона ценности:</b> {html.escape(aov_label or '')}"
            + (f" · {zone_low} – {zone_high}" if zone_low and zone_high else "")
            + "</p>"
        )

    body = f"""
    <h1>📊 {html.escape(ticker)}</h1>
    <p class="muted">TradingView · символ <code>{html.escape(tv)}</code>
       · <a href="/">← назад</a></p>
    <div class="card">
      {"<p>Entry: <b>"+str(entry)+"</b> · Stop: <b>"+str(stop)+"</b></p>" if entry is not None else ""}
      {"<p class='muted'>"+html.escape(reason[:200])+"</p>" if reason else ""}
      {zone_html}
      {"<p>🎯 <b>Цели:</b> "+html.escape(scale_plan[:220])+"</p>" if scale_plan else ""}
      <div id="tv_chart"></div>
    </div>
    <div class="card">
      <h2>Наши свечи (MOEX ISS) + зона ценности</h2>
      <div id="lw_chart" style="height:480px;width:100%"></div>
      <p class="muted">Зона ценности (AoV) + топ-2 Support/Resist по силе касаний, S/R flip, круглые числа, SMA200/EMA50, Entry/Stop/TP.</p>
      <p class="muted" id="aov_legend"></p>
    </div>
    <script src="https://s3.tradingview.com/tv.js"></script>
    <script>
    new TradingView.widget({{
      "container_id": "tv_chart",
      "symbol": "{tv}",
      "interval": "60",
      "timezone": "Europe/Moscow",
      "theme": "dark",
      "style": "1",
      "locale": "ru",
      "toolbar_bg": "#1a2332",
      "enable_publishing": false,
      "hide_side_toolbar": false,
      "allow_symbol_change": true,
      "height": 520,
      "width": "100%"
    }});
    </script>
    <script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
    <script>
    (async function() {{
      const r = await fetch('/api/candles/{html.escape(ticker)}?interval=24');
      const data = await r.json();
      if (!data.candles || !data.candles.length) {{
        document.getElementById('lw_chart').innerHTML = '<p class="muted">Нет данных ISS для тикера</p>';
        return;
      }}
      let aov = {{}};
      try {{
        const ar = await fetch('/api/aov/{html.escape(ticker)}');
        aov = await ar.json();
      }} catch (e) {{}}
      const el = document.getElementById('lw_chart');
      const chart = LightweightCharts.createChart(el, {{
        layout: {{ background: {{ color: '#111827' }}, textColor: '#e7ecf3' }},
        grid: {{ vertLines: {{ color: '#1f2937' }}, horzLines: {{ color: '#1f2937' }} }},
        width: el.clientWidth,
        height: 480,
      }});
      const series = chart.addCandlestickSeries({{
        upColor: '#22c55e', downColor: '#ef4444', borderVisible: false,
        wickUpColor: '#22c55e', wickDownColor: '#ef4444'
      }});
      series.setData(data.candles);

      // Area of Value band (two boundary lines)
      const zLo = aov.zone_low, zHi = aov.zone_high;
      if (zLo && zHi) {{
        series.createPriceLine({{ price: zLo, color: '#22c55e', lineWidth: 2, lineStyle: 0, title: 'AoV низ' }});
        series.createPriceLine({{ price: zHi, color: '#22c55e', lineWidth: 2, lineStyle: 0, title: 'AoV верх' }});
        // midpoint marker
        series.createPriceLine({{
          price: (zLo + zHi) / 2, color: 'rgba(34,197,94,0.35)', lineWidth: 8, lineStyle: 0, title: 'Зона ценности'
        }});
      }}
      // Other AoV levels (EMA, SMA, swings)
      const styleMap = {{0: 0, 1: 1, 2: 2}};
      (aov.levels || []).forEach(lv => {{
        if (zLo && zHi && (lv.title === 'AoV↓' || lv.title === 'AoV↑')) return;
        series.createPriceLine({{
          price: lv.price,
          color: lv.color || '#94a3b8',
          lineWidth: 1,
          lineStyle: styleMap[lv.style] !== undefined ? styleMap[lv.style] : 1,
          title: lv.title || ''
        }});
      }});

      {f"series.createPriceLine({{ price: {entry}, color: '#3b82f6', lineWidth: 2, title: 'Entry' }});" if entry is not None else ""}
      {f"series.createPriceLine({{ price: {stop}, color: '#f59e0b', lineWidth: 2, title: 'Stop' }});" if stop is not None else ""}
      {target_lines_js}

      const leg = document.getElementById('aov_legend');
      if (leg) {{
        leg.textContent = (aov.zone_label || aov.value_zone_label || '')
          + (aov.ema20 ? ` · EMA20=${{aov.ema20}}` : '')
          + (aov.ema50 ? ` · EMA50=${{aov.ema50}}` : '')
          + (aov.sma200 ? ` · SMA200=${{aov.sma200}}` : '');
      }}
      chart.timeScale().fitContent();
      window.addEventListener('resize', () => chart.applyOptions({{ width: el.clientWidth }}));
    }})();
    </script>
    """
    return _layout(body, title=f"График {ticker}")


@app.get("/charts")
def charts_index():
    setups = monitor.last_setups or []
    tickers = []
    seen = set()
    for s in setups:
        if s.ticker not in seen:
            tickers.append(s.ticker)
            seen.add(s.ticker)
    if not tickers:
        # default popular
        tickers = ["SBER", "GAZP", "SiU6", "MXU6", "BRQ6", "GDU6"]

    cards = []
    for t in tickers[:12]:
        cards.append(
            f"<div class='card' style='margin:0'>"
            f"<b>{html.escape(t)}</b><br/>"
            f"<a href='/chart/{html.escape(t)}'>Открыть график →</a></div>"
        )
    body = f"""
    <h1>Графики</h1>
    <p class="muted"><a href="/">← на главную</a></p>
    <div class="grid">{''.join(cards)}</div>
    <div class="card" style="margin-top:16px">
      <form action="/chart/SBER" method="get" onsubmit="location.href='/chart/'+this.t.value; return false;">
        <label class="muted">Тикер:&nbsp;</label>
        <input name="t" id="t" value="SBER" style="padding:8px;border-radius:6px;border:1px solid #334155;background:#0b1220;color:#fff"/>
        <button class="btn" type="submit">Открыть</button>
      </form>
    </div>
    """
    return _layout(body, title="Графики")


@app.get("/api/candles/<ticker>")
def api_candles(ticker: str):
    """OHLCV JSON for Lightweight Charts."""
    from data.moex_fetcher import fetch_ohlcv
    from data.universe import classify_instrument

    interval = request.args.get("interval", "24")
    lookback = int(request.args.get("days", "180"))
    fut = {ticker} if classify_instrument(ticker) == "futures" else set()
    try:
        data = fetch_ohlcv(
            [ticker],
            source="moex",
            lookback_days=lookback,
            use_cache=True,
            futures_tickers=fut,
        )
        df = data.get(ticker)
        if df is None or df.empty:
            return jsonify({"ticker": ticker, "candles": []})
        candles = []
        for ts, row in df.iterrows():
            try:
                t = int(ts.timestamp())
            except Exception:
                continue
            candles.append(
                {
                    "time": t,
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                }
            )
        return jsonify({"ticker": ticker, "candles": candles})
    except Exception as e:
        return jsonify({"error": str(e), "candles": []}), 500


@app.get("/api/setups")
def api_setups():
    setups = monitor.last_setups or []
    return jsonify([s.to_dict() for s in setups])


@app.get("/status")
@app.get("/health")
def status():
    st = monitor.status()
    st["scanning"] = _scanning
    st["service"] = "rayner-moex-scanner"
    st["status"] = "ok"
    try:
        from notify.telegram_alerts import telegram_status
        st["telegram"] = telegram_status()
    except Exception as e:
        st["telegram"] = {"error": str(e)}
    return jsonify(st)



@app.get("/journal")
def journal_page():
    from journal.store import JournalStore
    from journal.analyze import analyze_journal, format_report_text
    store = JournalStore()
    report = analyze_journal(store)
    open_rows = ""
    for tr in store.open_trades():
        open_rows += (
            f"<tr><td>{html.escape(tr.ticker)}</td><td>{html.escape(tr.strategy)}</td>"
            f"<td>{tr.entry_price}</td><td>{tr.stop}</td>"
            f"<td>{tr.mtm_pnl:.0f}</td>"
            f"<td><a href='/chart/{html.escape(tr.ticker)}'>📊</a></td></tr>"
        )
    closed_rows = ""
    for tr in reversed(store.closed_trades()[-30:]):
        closed_rows += (
            f"<tr><td>{html.escape(tr.ticker)}</td><td>{html.escape(tr.strategy)}</td>"
            f"<td>{tr.pnl:.0f}</td><td>{tr.pnl_pct*100:.1f}%</td>"
            f"<td>{html.escape(tr.exit_reason)}</td><td>{tr.bars_held}</td></tr>"
        )
    lessons = "".join(f"<li>{html.escape(x)}</li>" for x in report.get("lessons") or [])
    s = report.get("summary") or {}
    body = f"""
    <h1>📒 Журнал виртуальных сделок</h1>
    <p class="muted"><a href="/">← на главную</a> · <a href="/api/journal">JSON</a></p>
    <div class="card">
      <p>Открытых: <b>{report.get('open_count',0)}</b> ·
         Закрытых: <b>{report.get('closed_count',0)}</b> ·
         MTM открытых: <b>{report.get('open_mtm_pnl',0)}</b></p>
      <p class="muted">Win={s.get('win_rate','—')}% · Total PnL={s.get('total_pnl','—')} ·
         PF={s.get('profit_factor','—')}</p>
    </div>
    <div class="card">
      <h2>Уроки для обучения</h2>
      <ul>{lessons or '<li>Пока мало данных</li>'}</ul>
    </div>
    <div class="card">
      <h2>Открытые</h2>
      <table><thead><tr><th>Тикер</th><th>Стратегия</th><th>Entry</th><th>Stop</th><th>MTM</th><th></th></tr></thead>
      <tbody>{open_rows or '<tr><td colspan=6>Нет открытых</td></tr>'}</tbody></table>
    </div>
    <div class="card">
      <h2>Последние закрытые</h2>
      <table><thead><tr><th>Тикер</th><th>Стратегия</th><th>PnL</th><th>%</th><th>Выход</th><th>Дни</th></tr></thead>
      <tbody>{closed_rows or '<tr><td colspan=6>Нет закрытых</td></tr>'}</tbody></table>
    </div>
    """
    return _layout(body, title="Журнал")


@app.get("/api/journal")
def api_journal():
    from journal.store import JournalStore
    from journal.analyze import analyze_journal
    store = JournalStore()
    return jsonify({
        "open": [t.to_dict() for t in store.open_trades()],
        "closed": [t.to_dict() for t in store.closed_trades()[-100:]],
        "analysis": analyze_journal(store),
    })


def _bootstrap_monitor():
    cfg = load_config()
    monitor.configure_from_cfg(cfg)
    try:
        from notify.telegram_alerts import telegram_status
        st = telegram_status()
        print(f"[telegram] при старте: configured={st['configured']} "
              f"token={st['token_set']} chat_id={st['chat_id_set']} "
              f"preview={st.get('chat_id_preview')}")
    except Exception as e:
        print(f"[telegram] status error: {e}")
    # env overrides
    if os.getenv("MONITOR_ENABLED", "").lower() in ("0", "false", "no"):
        monitor.enabled = False
    if os.getenv("SCAN_UNIVERSE"):
        monitor.universe = os.getenv("SCAN_UNIVERSE")
    if os.getenv("MONITOR_INTERVAL_MIN"):
        monitor.interval_minutes = int(os.getenv("MONITOR_INTERVAL_MIN"))
    if monitor.enabled:
        monitor.start()


_bootstrap_monitor()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
