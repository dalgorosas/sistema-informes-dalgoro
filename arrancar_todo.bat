@echo off
REM Ventana 1: Uvicorn
start "Uvicorn Server" cmd /c "cd /d D:\Onedrive\DALGORO.SAS\GENERADOR_INFORMES && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
REM Ventana 2: LocalXpose
start "LocalXpose Tunnel" cmd /c "cd /d D:\loclx-windows-amd64 && loclx tunnel http --to 8000"
