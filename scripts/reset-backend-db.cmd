@echo off
cd /d "%~dp0..\backend"
if exist barber_booking.db (
  ".venv\Scripts\python.exe" -c "from pathlib import Path; from datetime import datetime; p=Path('barber_booking.db'); p.rename(f'barber_booking.db.backup.{datetime.now().strftime(\"%%Y%%m%%d%%H%%M%%S\")}')"
)
".venv\Scripts\python.exe" -c "from app.main import app; print('database reset and seeded')"
