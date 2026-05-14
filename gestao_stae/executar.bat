@echo off
echo ==========================================
echo   STAE - Executar Servidor Local
echo ==========================================
echo.
echo 1. Verificando dependencias...
pip install flask reportlab
echo.
echo 2. Iniciando servidor...
python app.py
echo.
pause
