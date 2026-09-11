@echo off
cd /d "%~dp0site"
start "" http://localhost:8000/
python -m http.server 8000
