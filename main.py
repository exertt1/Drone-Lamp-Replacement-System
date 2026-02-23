import os
import asyncpg
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from webapp.backend.config.config import init_config
from webapp.backend.logger.logger import init_logger
from webapp.backend.models.models import ConnectionManager
from webapp.backend.database.db import (
    fetch_queue,
    add_task_to_queue,
    cancel_task_by_lamp,
    update_queue_order,
    fetch_lamps_in_bbox,
)

# config/logger ДО lifespan
config = init_config()
logger = init_logger()

YANDEX_KEY = os.getenv("YANDEX_MAPS_API_KEY", "") or getattr(config, "yandex_maps_api_key", "")
DATABASE_URL = os.getenv("DATABASE_URL", "") or getattr(config, "database_url", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL не задан (ни в env, ни в config.database_url)")
    app.state.db_pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=2, max_size=20)
    try:
        yield
    finally:
        await app.state.db_pool.close()


app = FastAPI(lifespan=lifespan)
manager = ConnectionManager()

drone_state = {
    "id": "Alpha-7",
    "mode": "IDLE",
    "battery": 85,
    "online": True
}


async def lamp_exists(pool: asyncpg.Pool, lamp_id: str) -> bool:
    async with pool.acquire() as conn:
        v = await conn.fetchval("SELECT 1 FROM lamps WHERE id=$1", lamp_id)
        return bool(v)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    pool: asyncpg.Pool = ws.app.state.db_pool

    # сразу отдаём текущую очередь
    await ws.send_json({"type": "QUEUE_UPDATE", "queue": await fetch_queue(pool)})

    try:
        while True:
            msg = await ws.receive_json()
            action = msg.get("action")

            if action == "GET_QUEUE":
                await ws.send_json({"type": "QUEUE_UPDATE", "queue": await fetch_queue(pool)})
                continue

            if action == "GET_LAMPS":
                bbox = msg.get("bbox") or {}
                try:
                    lat_min = float(bbox.get("lat_min"))
                    lat_max = float(bbox.get("lat_max"))
                    lon_min = float(bbox.get("lon_min"))
                    lon_max = float(bbox.get("lon_max"))
                except (TypeError, ValueError):
                    await ws.send_json({"type": "LAMPS_UPDATE", "lamps": []})
                    continue

                limit = int(msg.get("limit", 1500))
                lamps = await fetch_lamps_in_bbox(pool, lat_min, lat_max, lon_min, lon_max, limit)
                await ws.send_json({"type": "LAMPS_UPDATE", "lamps": lamps})
                continue

            if action == "ADD_TO_PLAN":
                lamp_id = msg["lamp_id"]
                pr_type = msg.get("type", "medium")  # low/medium/high

                # ✅ главное: проверяем наличие лампы, иначе не создаём задачу
                if not await lamp_exists(pool, lamp_id):
                    await ws.send_json({"type": "ERROR", "code": "LAMP_NOT_FOUND", "lamp_id": lamp_id})
                    continue

                await add_task_to_queue(pool, lamp_id=lamp_id, hub_id=1, pr_type=pr_type)

                queue = await fetch_queue(pool)
                await manager.broadcast({"type": "QUEUE_UPDATE", "queue": queue})

                await manager.broadcast({
                    "type": "LAMP_STATUS",
                    "lamp_id": lamp_id,
                    "status": ("URGENT" if pr_type == "high" else "PLAN")
                })
                continue

            if action == "REMOVE_FROM_PLAN":
                lamp_id = msg.get("lamp_id")
                if lamp_id:
                    await cancel_task_by_lamp(pool, lamp_id)

                queue = await fetch_queue(pool)
                await manager.broadcast({"type": "QUEUE_UPDATE", "queue": queue})

                if lamp_id:
                    await manager.broadcast({"type": "LAMP_STATUS", "lamp_id": lamp_id, "status": "OK"})
                continue

            if action == "UPDATE_QUEUE_ORDER":
                new_order = msg.get("new_order", [])
                await update_queue_order(pool, new_order)

                queue = await fetch_queue(pool)
                await manager.broadcast({"type": "QUEUE_UPDATE", "queue": queue})
                continue

            # (опционально) меню страниц
            page = msg.get("page")
            if page and page != "Карта ламп":
                queue_len = len(await fetch_queue(pool))
                html_content = f"""
                <div class="drone-card" style="border:1px solid #00c6ff;padding:20px;border-radius:20px;background:rgba(0,198,255,0.05);">
                  <h3 style="margin:0;"><i class="fas fa-info-circle"></i> Раздел: {page}</h3>
                  <p style="margin-top:10px;color:#8892b5;">Задач в очереди: <b>{queue_len}</b></p>
                </div>
                """
                await ws.send_json({"type": "PAGE_DATA", "html": html_content})

    except WebSocketDisconnect:
        manager.disconnect(ws)


@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = Path(__file__).parent / "webapp" / "frontend" / "index.html"
    if not html_path.exists():
        # если у тебя другой путь — оставь как было в проекте
        html_path = Path("webapp/frontend/index.html")

    html = html_path.read_text(encoding="utf-8")
    html = html.replace("__YANDEX_KEY__", YANDEX_KEY)
    return HTMLResponse(content=html)