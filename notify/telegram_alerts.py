"""
Telegram alerts for MOEX scanner setups.
Requires env vars:
  TELEGRAM_BOT_TOKEN  — token from @BotFather
  TELEGRAM_CHAT_ID    — your chat / channel / group id
"""

from __future__ import annotations
from typing import List, Optional
import os
import requests
from strategies.base import Setup


def _get_credentials() -> tuple[Optional[str], Optional[str]]:
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TG_BOT_TOKEN") or ""
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TG_CHAT_ID") or ""
    return (token.strip() or None), (chat_id.strip() or None)


def is_telegram_configured() -> bool:
    token, chat_id = _get_credentials()
    return bool(token and chat_id)


def _escape_md(text: str) -> str:
    """Minimal escape for Telegram MarkdownV2 / HTML — we use HTML parse mode."""
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
    for i, s in enumerate(setups[:15], 1):
        direction = "🟢 LONG" if s.direction == "long" else "🔴 SHORT"
        news = ""
        if s.news_summary and s.news_summary not in ("Нет свежих новостей", "No recent news found"):
            news = f"\n   📰 {_escape_md(s.news_summary[:120])}"
        targets = getattr(s, "scale_plan", "") or ""
        if not targets and getattr(s, "targets", None):
            from strategies.base import format_targets_ru
            targets = format_targets_ru(s.targets, s.exit_rule)
        tgt_line = f"\n   🎯 {_escape_md(targets[:120])}" if targets else ""
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
    token = token or _get_credentials()[0]
    chat_id = chat_id or _get_credentials()[1]
    if not token or not chat_id:
        print("[telegram] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы — пропуск")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # Telegram limit ~4096 chars
    if len(text) > 4000:
        text = text[:3900] + "\n\n… (обрезано)"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_preview,
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 200 and r.json().get("ok"):
            print("[telegram] Алерт отправлен ✓")
            return True
        print(f"[telegram] Ошибка API: {r.status_code} {r.text[:200]}")
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
