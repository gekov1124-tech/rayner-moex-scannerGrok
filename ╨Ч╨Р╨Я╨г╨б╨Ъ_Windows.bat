@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo  Rayner x MOEX Scanner
echo ========================================
echo.

if not exist "venv\Scripts\activate.bat" (
    echo [1/3] Создаю окружение Python...
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo ОШИБКА: Python не найден.
        echo Скачайте Python с https://www.python.org/downloads/
        echo При установке поставьте галочку "Add Python to PATH"
        pause
        exit /b 1
    )
    call venv\Scripts\activate.bat
    echo [2/3] Устанавливаю библиотеки (1-3 минуты)...
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

echo [3/3] Сканирую рынок MOEX...
echo.
python main.py --universe sample --source moex --no-news
echo.
echo Готово. Файл setups_today.csv можно открыть в Excel.
echo.
pause
