# 🚀 Как запустить сканер Rayner × MOEX

Инструкция для человека **без опыта программирования**.

Программа сама ищет торговые идеи на Московской бирже по правилам Rayner Teo
(тренд + структура цены + риск). Она **не торгует за вас** — только показывает сэтапы.

---

## Способ 1. Самый простой — через сайт Railway (рекомендуется)

Railway сам запускает программу по расписанию и может присылать результаты в Telegram.

### Шаг 1. Заведите аккаунты (бесплатно)

1. **GitHub** — https://github.com  
   Нажмите Sign up → зарегистрируйтесь.

2. **Railway** — https://railway.app  
   Войдите через GitHub (кнопка Login with GitHub).

3. **Telegram-бот** (чтобы получать сэтапы в телефон):
   - Откройте Telegram → найдите **@BotFather**
   - Напишите `/newbot`
   - Придумайте имя (например `My Moex Scanner`) и username (например `my_moex_scanner_bot`)
   - BotFather пришлёт **TOKEN** — сохраните его (выглядит как `123456:ABC-DEF...`)
   - Напишите своему новому боту любое сообщение (например «привет»)
   - Откройте в браузере ссылку (подставьте свой TOKEN):
     ```
     https://api.telegram.org/botВАШ_TOKEN/getUpdates
     ```
   - Найдите цифры `"chat":{"id": 123456789}` — это ваш **CHAT_ID**. Сохраните.

### Шаг 2. Загрузите файлы на GitHub

1. На GitHub нажмите **New repository**
2. Имя: `rayner-moex-scanner` (или любое)
3. Поставьте галочку **Add a README file** → Create repository
4. Нажмите **Add file → Upload files**
5. Перетащите **все файлы и папки** из архива `rayner_moex_scanner.zip`  
   (или загрузите папку целиком)
6. Внизу нажмите **Commit changes**

### Шаг 3. Подключите к Railway

1. Зайдите на https://railway.app
2. **New Project → Deploy from GitHub repo**
3. Выберите репозиторий `rayner-moex-scanner`
4. Railway сам найдёт Dockerfile и соберёт проект

### Шаг 4. Настройте переменные

В проекте Railway откройте вкладку **Variables** и добавьте:

| Переменная | Значение |
|------------|----------|
| `TELEGRAM_BOT_TOKEN` | токен от BotFather |
| `TELEGRAM_CHAT_ID` | ваш chat id |

### Шаг 5. Расписание (чтобы сканировало каждый день)

1. В Railway откройте сервис → **Settings**
2. Найдите **Cron Schedule** (или добавьте через railway.toml)
3. Пример: `30 15 * * 1-5` — каждый будний день в 15:30 UTC  
   (примерно после закрытия MOEX)

Готово. Каждый день бот будет присылать список сэтапов в Telegram.

---

## Способ 2. Запуск на своём компьютере (Windows)

### Что нужно установить один раз

1. **Python 3.11+**  
   Скачайте с https://www.python.org/downloads/  
   ⚠️ При установке поставьте галочку **“Add Python to PATH”**

2. Распакуйте архив `rayner_moex_scanner.zip` в папку, например:
   ```
   C:\rayner_scanner\
   ```

### Запуск

1. Откройте папку `C:\rayner_scanner\`
2. В адресной строке проводника напишите `cmd` и нажмите Enter  
   (откроется чёрное окно в этой папке)
3. Введите по очереди:

```text
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py --universe sample --source moex --no-news
```

Первый запуск скачает данные с Московской биржи (1–2 минуты).

### Что вы увидите

Таблицу со сэтапами:

- **Ticker** — акция (SBER, GAZP…)
- **Strategy** — какая система нашла идею
- **Entry / Stop** — примерная цена входа и стопа
- **Score** — оценка силы сэтапа
- **Reason** — почему сработал

Файл `setups_today.csv` сохранится в той же папке — его можно открыть в Excel.

### Чтобы получать результаты в Telegram с компьютера

Перед запуском в том же чёрном окне:

```text
set TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
set TELEGRAM_CHAT_ID=123456789
python main.py --universe sample --source moex
```

---

## Способ 3. Mac / Linux

```bash
cd ~/rayner_scanner
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py --universe sample --source moex --no-news
```

---

## Полезные команды

| Команда | Что делает |
|---------|------------|
| `python main.py --universe sample --source moex --no-news` | Быстрый скан 25 акций без новостей |
| `python main.py --universe blue --source moex` | Голубые фишки + новости |
| `python main.py --strategies Rayner_BOS_MTF` | Только Break of Structure (Daily+H4) |
| `python main.py --list-strategies` | Список всех стратегий |

---

## Что внутри архива (главное)

```
rayner_scanner/
├── START_HERE.md      ← эта инструкция
├── main.py            ← запуск программы
├── config.yaml        ← настройки (капитал, стратегии, новости)
├── requirements.txt   ← библиотеки Python
├── Dockerfile         ← для Railway
├── railway.toml       ← расписание на Railway
├── data/              ← загрузка цен MOEX + новости + структура
├── strategies/        ← торговые системы (включая Rayner_BOS_MTF)
├── notify/            ← Telegram-алерты
├── filters/           ← фильтр новостей
├── plugins/           ← сюда можно добавлять свои стратегии
└── output/            ← сохранение CSV
```

---

## Важно (дисклеймер)

- Это **образовательный** инструмент.
- Не является индивидуальной инвестиционной рекомендацией.
- Прошлые результаты не гарантируют будущую прибыль.
- Всегда считайте свой риск. Не входите в сделки только потому, что их нашёл сканер.

---

## Если что-то не работает

1. **“python не найден”** — Python не добавлен в PATH, переустановите с галочкой.
2. **Долго грузит H4** — первый раз нормально (качает часовые свечи). Дальше берёт из кэша.
3. **Telegram молчит** — проверьте TOKEN и CHAT_ID, напишите боту /start.
4. **Нет сэтапов** — рынок может не давать сигналов по правилам; это нормально.

Вопросы по настройке — перечитайте этот файл и `DEPLOY.md`.
