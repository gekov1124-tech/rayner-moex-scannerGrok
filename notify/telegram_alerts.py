"""
Telegram alerts for MOEX scanner setups.
Requires env vars:
  TELEGRAM_BOT_TOKEN  — token from @BotFather
  TELEGRAM_CHAT_ID    — your chat / channel / group id
"""

from __future__ import annotations
from typing import List, Optional, Tuple
import os
import requests
from strategies.base import Setup


def _clean(s: str) -> str:
    """Strip whitespace and accidental quotes from Railway env values."""
    if not s:
        return ""
    s = s.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    return s


def _get_credentials() -> Tuple[Optional[str], Optional[str]]:
    token = _clean(os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TG_BOT_TOKEN") or "")
    chat_id = _clean(os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TG_CHAT_ID") or "")
    return (token or None), (chat_id or None)


def is_telegram_configured() -> bool:
    token, chat_id = _get_credentials()
    return bool(token and chat_id)


def telegram_status() -> dict:
    token, chat_id = _get_credentials()
    return {
        "configured": bool(token and chat_id),
        "token_set": bool(token),
        "token_prefix": (token[:8] + "…") if token and len(token) > 8 else (token or ""),
        "chat_id_set": bool(chat_id),
        "chat_id_preview": (chat_id[:4] + "…" + chat_id[-3:]) if chat_id and len(chat_id) > 7 else (chat_id or ""),
    }


def _escape_md(text: str) -> str:
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_setups_message(setups: List[Setup], title: str = "MOEX Scanner") -> str:
    if not setups:
        return f"<b>{_escape_md(title)}</b>\n\nСэтапов не найдено."

    lines = [
        f"<b>🔔 {_escape_md(title)}</b>",
        f"Найдено сэтапов: <b>{len(setups)}</b>",
        "",
    ]
    for i, s in enumerate(setups[:12], 1):
        direction = "🟢 LONG" if s.direction == "long" else "🔴 SHORT"
        news = ""
        if s.news_summary and s.news_summary not in ("Нет свежих новостей", "No recent news found"):
            news = f"\n   📰 {_escape_md(s.news_summary[:100])}"
        targets = getattr(s, "scale_plan", "") or ""
        if not targets and getattr(s, "targets", None):
            from strategies.base import format_targets_ru
            targets = format_targets_ru(s.targets, s.exit_rule)
        tgt_line = f"\n   🎯 {_escape_md(targets[:110])}" if targets else ""
        lines.append(
            f"<b>{i}. {s.ticker}</b> · {s.strategy}\n"
            f"   {direction}  Entry: <code>{s.entry}</code>  Stop: <code>{s.stop}</code>\n"
            f"   Shares: {s.suggested_shares}  Risk: {s.risk_amount:.0f}  Score: {s.score:.1f}\n"
            f"   {_escape_md((s.reason or '')[:90])}"
            f"{tgt_line}"
            f"{news}"
        )
        lines.append("")

    lines.append("<i>Образовательный алерт. Не инвестиционная рекомендация.</i>")
    return "\n".join(lines)


def send_telegram_message(
    text: str,
    token: Optional[str] = None,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML",
    disable_preview: bool = True,
) -> bool:
    token = _clean(token or "") or _get_credentials()[0]
    chat_id = _clean(chat_id or "") or _get_credentials()[1]
    if not token or not chat_id:
        print("[telegram] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы — пропуск")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    if len(text) > 4000:
        text = text[:3900] + "\n\n… (обрезано)"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_preview,
    }
    try:
        r = requests.post(url, json=payload, timeout=20)
        body = {}
        try:
            body = r.json()
        except Exception:
            pass
        if r.status_code == 200 and body.get("ok"):
            print("[telegram] Алерт отправлен ✓")
            return True
        # Detailed diagnostics for Railway logs
        desc = body.get("description") or r.text[:300]
        print(f"[telegram] Ошибка API: HTTP {r.status_code} · {desc}")
        if "chat not found" in str(desc).lower():
            print("[telegram] Подсказка: неверный CHAT_ID или бот не добавлен в чат. Напишите боту /start")
        if "unauthorized" in str(desc).lower():
            print("[telegram] Подсказка: неверный TELEGRAM_BOT_TOKEN")
        return False
    except Exception as e:
        print(f"[telegram] Ошибка отправки: {e}")
        return False


def send_setups_alert(
    setups: List[Setup],
    title: str = "Rayner × MOEX Scanner",
    token: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> bool:
    msg = format_setups_message(setups, title=title)
    return send_telegram_message(msg, token=token, chat_id=chat_id)


def send_test_message() -> dict:
    """Send a short test message; returns diagnostic dict."""
    st = telegram_status()
    if not st["configured"]:
        return {**st, "sent": False, "error": "Токен или CHAT_ID не заданы в Variables"}
    ok = send_telegram_message(
        "<b>✅ Тест Rayner × MOEX Scanner</b>\n\n"
        "Если вы видите это сообщение — Telegram настроен правильно.\n"
        f"Время теста: {__import__('datetime').datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC"
    )
    return {**st, "sent": ok, "error": None if ok else "API отклонил сообщение — смотрите логи [telegram]"}
