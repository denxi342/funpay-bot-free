@echo off
echo Установка зависимостей...
py -m pip install -r requirements.txt
echo.
echo Запуск бота...
py main.py
pause
