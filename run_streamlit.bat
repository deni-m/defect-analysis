@echo off
setlocal

set "VENV_ACTIVATE=.venv\Scripts\activate.bat"

if not exist "%VENV_ACTIVATE%" (
  echo Virtual environment not found at %VENV_ACTIVATE%
  echo Create it first with: python -m venv .venv
  exit /b 1
)

call "%VENV_ACTIVATE%"
streamlit run src\qa_bugs\ui\app.py
