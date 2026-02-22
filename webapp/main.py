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

    # при подключении сразу отправляем текущую очередь
    await websocket.send_json({"type": "QUEUE_UPDATE", "queue": current_queue})

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            action = msg.get("action")

            if action == "GET_QUEUE":
                await websocket.send_json({"type": "QUEUE_UPDATE", "queue": current_queue})
                continue

            elif action == "ADD_TO_PLAN":
                new_id = msg["lamp_id"]
                loc = msg.get("loc", "Новый объект")
                status = msg.get("status", "План")
                task_type = msg.get("type", "medium")

                # анти-дубли
                if not any(x["id"] == new_id for x in current_queue):
                    current_queue.insert(0, {"id": new_id, "loc": loc, "status": status, "type": task_type})

                await websocket.send_json({"type": "QUEUE_UPDATE", "queue": current_queue})
                continue

            elif action == "UPDATE_QUEUE_ORDER":
                new_order = msg.get("new_order", [])

                # применяем порядок на сервере
                id_to_item = {x["id"]: x for x in current_queue}
                current_queue = [id_to_item[i] for i in new_order if i in id_to_item]

                await websocket.send_json({"type": "QUEUE_UPDATE", "queue": current_queue})
                continue

            elif msg.get("action") == "REMOVE_FROM_PLAN":
                lamp_id = msg.get("lamp_id")
                if lamp_id:
                    current_queue[:] = [x for x in current_queue if x["id"] != lamp_id]
                    await websocket.send_json({"type": "QUEUE_UPDATE", "queue": current_queue})

            # навигация: отдаем HTML для разделов (кроме карты)
            page = msg.get("page")
            if page and page != "Карта ламп":
                html_content = f"""
                <div class="drone-card" style="border: 1px solid #00c6ff; padding: 20px; border-radius: 20px; background: rgba(0,198,255,0.05);">
                    <h3 style="margin:0;"><i class="fas fa-info-circle"></i> Раздел: {page}</h3>
                    <p style="margin-top: 12px; color: #8892b5;">
                        Данные синхронизированы с сервером.
                        Текущих задач в очереди: <b>{len(current_queue)}</b>
                    </p>

                    <div style="margin-top: 14px; display:flex; gap:10px; flex-wrap:wrap;">
                        <button class="btn" onclick="socket.send(JSON.stringify({{action:'GET_QUEUE'}}))">
                            Обновить очередь
                        </button>
                        <button class="btn" onclick="socket.send(JSON.stringify({{action:'ADD_TO_PLAN', lamp_id:'L-'+Math.floor(1000+Math.random()*9000), loc:'Добавлено из раздела: {page}', status:'План', type:'medium'}}))">
                            Добавить тестовую задачу
                        </button>
                    </div>
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
