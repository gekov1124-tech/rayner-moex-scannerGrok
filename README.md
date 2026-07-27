# Rayner Teo × MOEX Scanner (Московская биржа)

**Образовательный инструмент.** Не является финансовой рекомендацией.  
Торговля сопряжена с риском потери капитала.

## Что умеет

1. Сканирует акции **Московской биржи** (TQBR / голубые фишки / IMOEX).
2. Ищет сэтапы по философии **Rayner Teo** + совместимым rules-based системам.
3. **Подключение дополнительных стратегий** через папку `plugins/` (registry).
4. Новостной фильтр (RSS + keywords на русском).
5. Готов к деплою **GitHub → Railway** (Cron после закрытия сессии).

### Источники данных
- **MOEX ISS** (основной, бесплатно, без ключа) — `iss.moex.com`
- **Finam** (опционально) — `pip install finam-export`, флаг `--source finam`

### Стратегии (все rules-based + тренд-фильтр)

| Стратегия | Описание |
|-----------|----------|
| RaynerBB_MeanRev | SMA200 + BB(20, 2.5) + limit 3% |
| ConnorsRSI2 | SMA200 + RSI(2) < 10 |
| TrendBreakout_200High | Новый 200-дневный high close + 6×ATR |
| Donchian20 | Break 20-day high (Turtle-style) |
| EMA_Pullback | Pullback к EMA20/50 в аптренде |

## Быстрый старт

```bash
pip install -r requirements.txt
python main.py --universe sample --source moex --no-news
python main.py --list-strategies
python main.py --universe blue --source moex
```

## Подключение дополнительных стратегий

1. Создайте файл `plugins/my_strategy.py` (пример уже есть).
2. Класс должен:
   - Наследоваться от `Strategy`
   - Иметь декоратор `@register("Имя")`
   - Реализовывать `generate_setups(ticker, df, equity) → List[Setup]`
3. Добавьте имя в `config.yaml` → `strategies:` или запустите:
   ```bash
   python main.py --strategies RaynerBB_MeanRev MyCustom
   ```

**Требования совместимости с философией Rayner Teo:**
- Объективные правила (бэктестируемые)
- Фильтр тренда (SMA200 / структура HH-HL)
- Risk management (1% или fixed capital %, ATR-стоп)
- Не чистый контртренд без фильтра

## Деплой GitHub + Railway

См. подробный гайд: **[DEPLOY.md](DEPLOY.md)**

Кратко:
1. Push в GitHub.
2. Railway → New Project → Deploy from GitHub.
3. Settings → Cron Schedule: `0 16 * * 1-5` (после закрытия MOEX).
4. Start Command: `python main.py --universe blue --source moex`
5. Логи покажут сэтапы. Процесс должен завершаться (exit).

## Структура

```
rayner_scanner/
├── main.py
├── config.yaml
├── DEPLOY.md
├── Dockerfile / railway.toml / Procfile
├── data/          # moex_fetcher, universe, news
├── strategies/    # base + registry + 5 систем
├── plugins/       # ваши дополнительные стратегии
├── filters/ risk/ utils/ output/
```



## Новостные источники

- Google News RU (поиск по тикеру / названию компании)
- RBC
- Interfax
- Finam
- Smart-Lab
- Kommersant
- Vedomosti
- Yahoo RSS
- Finnhub (если задан API-ключ)

Фильтр отсекает сильный негатив и high-impact события (отчётность, санкции, иски и т.д.).

## Telegram-алерты

1. Создайте бота у @BotFather → TOKEN
2. Узнайте CHAT_ID через getUpdates
3. Задайте env:
   ```bash
   export TELEGRAM_BOT_TOKEN="..."
   export TELEGRAM_CHAT_ID="..."
   ```
4. При сканировании бот пришлёт сэтапы (тикер, стратегия, entry/stop, score, краткие новости).

В Railway те же переменные в Settings → Variables.



## Multi-Timeframe (Rayner Teo)

По методологии Rayner Teo анализ идёт на **нескольких таймфреймах**:

### Factor of 4–6
- Higher TF ≈ Entry TF × 4…6
- Для сканера: **Weekly (HTF)** + **Daily (entry TF)**

### Роли таймфреймов
| Таймфрейм | Роль |
|-----------|------|
| **Weekly** | Market Structure / тренд (SMA40 ≈ 200 daily), Area of Value |
| **Daily**  | Break of Structure, точный вход, стоп по структуре |

### Стратегия `Rayner_BOS_MTF`
**Основной режим (как у Rayner):**
1. **HTF = Daily** — тренд (SMA200 + structure), Area of Value (support)
2. **LTF = H4** — реальные 4-часовые свечи с MOEX (1H → resample 4H)
3. На H4: структура HH+HL → **Break of Structure** (пробой swing high)
4. Стоп под H4 structure low (более точный, уже daily-стопа)
5. Score выше при confluence + бонус за H4

**Fallback** (если H4 недоступны): Weekly HTF + Daily LTF.

Это прямая реализация видео Rayner *Break of Structure Trading Strategy* и курса *Multiple Timeframe Secrets*.

Остальные стратегии по-прежнему на Daily + SMA200.

## Дисклеймер

Это образовательный код на основе публичных концепций Rayner Teo и классических quant-систем.  
Не используйте для реальной торговли без собственных тестов и риск-менеджмента.  
Прошлые результаты не гарантируют будущих. Данные MOEX/Finam могут иметь задержки и ошибки.

---
Сделано командой Grok (xAI) + Harper, Benjamin, Lucas.
