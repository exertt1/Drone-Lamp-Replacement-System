# Drone Lamp Replacement System 🛸💡
> Ранний прототип backend’а для системы автоматизированной замены уличных ламп/картриджей с помощью БПЛА.  
> Сейчас в репозитории: **FastAPI + WebSocket “эхо”** (техническая заготовка под телеметрию/управление).

<p align="left">
  <img alt="Python" src="https://img.shields.io/badge/python-3.12%2B-blue">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-websocket-009688">
  <img alt="Status" src="https://img.shields.io/badge/status-prototype-orange">
</p>

---

## О проекте
Идея: дроны обслуживают уличные светильники (замена картриджа/лампы), а софт отвечает за:
- приём телеметрии и событий,
- диспетчеризацию задач (миссии на замену),
- учёт состояния светильников/картриджей,
- (в будущем) визуализацию “цифрового двойника”.

**Важно:** текущая версия — не “готовая система”, а стартовая точка: минимальный сервер и WebSocket-канал.

---

## Содержимое репозитория

.
├─ webapp/
│  ├─ main.py            # FastAPI + WebSocket прототип
│  └─ requirements.txt   # зависимости
└─ .gitignore            # .env / .venv
---

## Быстрый старт 🚀

### 1) Требования
- Python **3.10+** (рекомендуется)
- pip / venv

### 2) Установка
```bash
cd webapp

python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows (PowerShell):
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt

uvicorn main:app --reload --host 0.0.0.0 --port 8000