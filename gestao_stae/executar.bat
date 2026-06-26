@echo off
echo ==========================================
echo   STAE - Executar Servidor Local
echo ==========================================
echo.
echo 1. Verificando dependencias...
"C:\Users\Acer\AppData\Local\Programs\Python\Python312\python.exe" -m pip install flask reportlab psycopg2-binary
echo.
echo 2. Iniciando servidor...
"C:\Users\Acer\AppData\Local\Programs\Python\Python312\python.exe" app.py
echo.
pause
