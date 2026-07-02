@echo off
echo ==========================================
echo   STAE - Executar Servidor Local
echo ==========================================
echo.
echo 1. Verificando dependencias...
py -m pip install flask reportlab openpyxl
echo.
echo 2. Iniciando servidor...
py app.py
echo.
pause
