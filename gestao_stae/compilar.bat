@echo off
echo ==========================================
echo   STAE - Instalador e Compilador
echo ==========================================
echo.
echo 1. Instalando dependencias (Flask, ReportLab, PyInstaller)...
pip install flask reportlab pyinstaller
echo.
echo 2. Compilando o executavel (isso pode levar alguns minutos)...
pyinstaller --onefile --windowed --name "Gestao_STAE_Circulacao" app.py
echo.
echo ==========================================
echo   CONCLUIDO!
echo   O ficheiro "Gestao_STAE_Circulacao.exe" esta na pasta "dist".
echo ==========================================
pause
