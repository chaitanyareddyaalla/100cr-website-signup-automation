@echo off
title 100CR Referral Automation - Device Runner
cd /d "%~dp0"
echo ==========================================================
echo  100CR Multi-Referral Fast 1000 Automation (Device Runner)
echo ==========================================================
echo Running on your local device Indian residential/mobile IP.
echo Bypasses Cloudflare datacenter blocks with 0 retries and fast queueing.
echo.
.\.venv\Scripts\python.exe scripts\run_1000_batch.py %*
pause
