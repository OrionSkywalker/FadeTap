@echo off
cd /d "%~dp0.."
start "BarberBooking API" cmd /k scripts\start-backend.cmd
start "BarberBooking Web" cmd /k scripts\start-frontend.cmd
