from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pathlib import Path
from webapp.backend.config.config import init_config
from webapp.backend.logger.logger import init_logger
import json

app = FastAPI()

config = init_config()

logger = init_logger()

current_queue = [
    {"id": "L-0872", "loc": "пр. Мира, 24", "status": "Срочно", "type": "high"},
    {"id": "L-2317", "loc": "ул. Ленина, 5", "status": "План", "type": "medium"},
    {"id": "L-0934", "loc": "ул. Гагарина, 12", "status": "Срочно", "type": "high"},
    {"id": "L-3512", "loc": "пл. Победы, 1", "status": "План", "type": "low"}
]


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    global current_queue
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            # 1. Логика очереди
            if msg.get("action") == "ADD_TO_PLAN":
                new_id = msg["lamp_id"]
                current_queue.insert(0, {"id": new_id, "loc": "Новый объект", "status": "План", "type": "medium"})
                print(f"Добавлена задача: {new_id}")

            if msg.get("action") == "UPDATE_QUEUE_ORDER":
                print(f"Новый порядок ID: {msg.get('new_order')}")

            # 2. Логика навигации
            page = msg.get("page")
            if page:
                if page != "Карта ламп":
                    # Генерируем контент для других страниц
                    html_content = f"""
                        <div class="drone-card" style="border: 1px solid #00c6ff; padding: 20px; border-radius: 20px; background: rgba(0,198,255,0.05);">
                            <h3><i class="fas fa-info-circle"></i> Раздел: {page}</h3>
                            <p style="margin-top: 15px; color: #8892b5;">Данные синхронизированы с сервером. Текущих активных событий: {len(current_queue)}</p>
                            <button class="btn" style="margin-top: 20px;">Отозвать на базу</button>
                        </div>
                    """
                    await websocket.send_json({"type": "PAGE_DATA", "html": html_content})

    except WebSocketDisconnect:
        print("Клиент отключился")


@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = Path(__file__).parent.parent / "frontend" / "index.html"
    if not html_path.exists():
        html_path = Path("webapp/frontend/index.html")
    return HTMLResponse(content=html_path.read_text(encoding='utf-8'))
