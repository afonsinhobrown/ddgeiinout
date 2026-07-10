@echo off
echo ==========================================
echo   STAE - Executar Servidor Local
echo ==========================================
echo.
echo 1. Verificando dependencias...
python -m pip install flask reportlab openpyxl psycopg2-binary
echo.
echo 2. Iniciando servidor...
python app.py
echo.
pause
