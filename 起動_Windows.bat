@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv ".venv"
  if errorlevel 1 ( echo Python 3.10以降をインストールしてください & pause & exit /b 1 )
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 ( echo 必要なライブラリをインストールできませんでした。 & pause & exit /b 1 )
".venv\Scripts\python.exe" -m streamlit run app.py
pause
