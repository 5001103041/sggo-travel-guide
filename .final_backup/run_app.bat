@echo off
chcp 65001 >nul
title SGGo! Travel Guide - May Chu & Website
echo ====================================================================
echo                 SGGO! TRAVEL GUIDE - DANG KHOI DONG
echo ====================================================================
echo.

cd /d "%~dp0"

echo [1/2] Dang tu dong mo website tren trinh duyet...
start "" http://127.0.0.1:8000

echo [2/2] Dang chay May chu Backend (FastAPI & SQLite) tai cong 8000...
echo.
echo ====================================================================
echo  * TRINH DUYET DA DUOC MO TAI: http://127.0.0.1:8000
echo  * Cua so den nay la MAY CHU giup CSDL SQLite va AI hoat dong.
echo  * Ban chi can THU NHO [ - ] cua so nay xuong de luot web.
echo  * KHI NAO DUNG XONG: Bam nut [ X ] mau do de tat may chu.
echo ====================================================================
echo.

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
