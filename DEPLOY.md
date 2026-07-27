# Деплой на Railway + GitHub (MOEX Scanner)

## 1. Подготовка репозитория

```bash
cd rayner_scanner
git init
git add .
git commit -m "Rayner Teo MOEX Scanner"
# Создайте репозиторий на GitHub и запушьте
git remote add origin https://github.com/YOUR_USER/rayner-moex-scanner.git
git push -u origin main
```

## 2. Railway

1. Зайдите на [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**.
2. Выберите репозиторий.
3. Railway подхватит `Dockerfile` (или Nixpacks).
4. В **Settings → Service**:
   - **Start Command**: `python main.py --universe blue --source moex`
   - **Cron Schedule** (рекомендуется): `0 16 * * 1-5`  
     (16:00 UTC ≈ 19:00 МСК — после закрытия основной сессии MOEX)
5. (Опционально) Variables:
   - `FINNHUB_API_KEY` — если хотите больше новостей
6. Deploy.

## 3. Как это работает

- Railway Cron запускает контейнер по расписанию.
- `main.py` сканирует рынок, пишет в stdout (логи) и сохраняет `setups_today.csv`.
- После завершения процесс **должен завершиться** (exit 0) — иначе следующий cron пропустится.
- Результаты смотрите в **Deployments → Logs**.

## 4. Альтернатива: on-demand API

Можно добавить FastAPI endpoint `/scan` и вызывать его вручную или через внешний cron (GitHub Actions, cron-job.org).

## 5. Добавление стратегий без пересборки ядра

1. Создайте файл `plugins/my_strategy.py` (см. пример в папке).
2. Класс с декоратором `@register("MyName")`, наследник `Strategy`.
3. Добавьте имя в `config.yaml` → `strategies:` или передайте `--strategies MyName`.
4. Push в GitHub → Railway автоматически задеплоит.

**Требования совместимости с философией Rayner Teo:**
- Rules-based (можно бэктестить)
- Предпочтительно фильтр тренда (SMA200 / структура рынка)
- Чёткие entry / exit / stop
- Risk management (1% или fixed capital %, ATR)
- Не чистый контртренд без фильтра

## 6. Локальный тест перед деплоем

```bash
pip install -r requirements.txt
python main.py --universe sample --source moex --no-news
python main.py --list-strategies
```

---

## Telegram-алерты

1. Создайте бота через [@BotFather](https://t.me/BotFather) → получите `TOKEN`.
2. Узнайте свой `CHAT_ID`:
   - напишите боту любое сообщение
   - откройте `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - найдите `"chat":{"id": ...}`
3. В Railway → Variables добавьте:
   ```
   TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
   TELEGRAM_CHAT_ID=123456789
   ```
4. При каждом сканировании (cron или ручной запуск) бот пришлёт список сэтапов.

Локально:
```bash
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
python main.py --universe sample --source moex
```

Отключить алерты: в `config.yaml` → `telegram.enabled: false` или не задавать env.
