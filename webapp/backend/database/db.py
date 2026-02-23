import asyncpg
from webapp.backend.models.models import EnergyModel
from typing import Dict

ACTIVE_TASK_STATUSES = ("queued", "assigned", "enroute", "working", "returning")
PRIORITY_MAP = {"low": 1, "medium": 2, "high": 3}


async def fetch_queue(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
              t.id        AS task_id,
              t.lamp_id   AS lamp_id,
              t.status    AS task_status,
              p.priority  AS priority,
              l.lat       AS lat,
              l.lon       AS lon
            FROM tasks t
            JOIN lamps l ON l.id = t.lamp_id
            JOIN priorities p ON p.id = t.priority_id
            WHERE t.status IN ('queued','assigned','enroute','working','returning')
            ORDER BY t.sort_rank DESC, t.created_at DESC
            """
        )

    out = []
    for r in rows:
        out.append({
            "task_id": r["task_id"],
            "id": r["lamp_id"],  # UI ждёт id лампы
            "loc": f"Kazan ({r['lat']:.5f}, {r['lon']:.5f})",
            "status": "Срочно" if r["priority"] == "high" else "План",
            "type": r["priority"],          # low/medium/high
            "task_status": r["task_status"] # queued/assigned/...
        })
    return out


async def add_task_to_queue(pool: asyncpg.Pool, lamp_id: str, hub_id: int = 1, pr_type: str = "medium"):
    pr_id = PRIORITY_MAP.get(pr_type, 2)

    async with pool.acquire() as conn:
        async with conn.transaction():
            # 1) создаём задачу, но не даём сделать 2 активные на одну лампу
            task_id = await conn.fetchval(
                f"""
                INSERT INTO tasks(lamp_id, hub_id, priority_id, status, sort_rank)
                VALUES ($1,$2,$3,'queued', EXTRACT(EPOCH FROM now())::bigint)
                ON CONFLICT (lamp_id)
                WHERE status IN {ACTIVE_TASK_STATUSES}
                DO NOTHING
                RETURNING id
                """,
                lamp_id, hub_id, pr_id
            )

            # 2) обновим статус лампы для карты
            # если high -> URGENT, иначе PLAN
            new_lamp_status = "URGENT" if pr_type == "high" else "PLAN"
            await conn.execute(
                "UPDATE lamps SET status=$2, updated_at=now() WHERE id=$1",
                lamp_id, new_lamp_status
            )

            return {"created": task_id is not None, "task_id": task_id}


async def cancel_task_by_lamp(pool: asyncpg.Pool, lamp_id: str):
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE tasks
                SET status='canceled', updated_at=now()
                WHERE lamp_id=$1 AND status IN ('queued','assigned','enroute','working','returning')
                """,
                lamp_id
            )

            # если активных задач больше нет — вернём лампу в OK
            active = await conn.fetchval(
                """
                SELECT 1 FROM tasks
                WHERE lamp_id=$1 AND status IN ('queued','assigned','enroute','working','returning')
                LIMIT 1
                """,
                lamp_id
            )
            if not active:
                await conn.execute(
                    "UPDATE lamps SET status='OK', updated_at=now() WHERE id=$1",
                    lamp_id
                )


async def update_queue_order(pool: asyncpg.Pool, lamp_ids: list[str]):
    if not lamp_ids:
        return

    base = 10_000_000_000
    async with pool.acquire() as conn:
        async with conn.transaction():
            for i, lamp_id in enumerate(lamp_ids):
                await conn.execute(
                    """
                    UPDATE tasks
                    SET sort_rank=$2, updated_at=now()
                    WHERE lamp_id=$1 AND status='queued'
                    """,
                    lamp_id, base - i
                )


async def fetch_lamps_in_bbox(pool: asyncpg.Pool, lat_min: float, lat_max: float, lon_min: float, lon_max: float, limit: int = 1500):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, lat, lon, status
            FROM lamps
            WHERE lat BETWEEN $1 AND $2
              AND lon BETWEEN $3 AND $4
            LIMIT $5
            """,
            lat_min, lat_max, lon_min, lon_max, limit
        )
    # фронт ждёт {id, lat, lon, status}
    return [{"id": r["id"], "lat": r["lat"], "lon": r["lon"], "status": r["status"]} for r in rows]

async def fetch_hubs(pool) -> Dict[int, Dict[str, float]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, lat, lon FROM hubs")
    return {r["id"]: {"lat": r["lat"], "lon": r["lon"]} for r in rows}

async def fetch_idle_drones(pool):
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT id, code, hub_id, lat, lon, battery_percent, status, current_task_id
            FROM drones
            WHERE status='idle' AND battery_percent >= $1
            ORDER BY battery_percent DESC
        """, int(EnergyModel.MIN_PCT))

async def fetch_top_queued_tasks(pool, limit: int = 200):
    async with pool.acquire() as conn:
        return await conn.fetch(f"""
            SELECT
              t.id AS task_id,
              t.lamp_id,
              t.hub_id,
              p.priority AS priority,
              p.id AS priority_id,
              l.lat AS lamp_lat,
              l.lon AS lamp_lon
            FROM tasks t
            JOIN priorities p ON p.id = t.priority_id
            JOIN lamps l ON l.id = t.lamp_id
            WHERE t.status='queued'
            ORDER BY t.priority_id DESC, t.sort_rank DESC, t.created_at DESC
            LIMIT {limit}
        """)

async def broadcast_drones_state(pool, manager):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, code, lat, lon, battery_percent, status, current_task_id
            FROM drones
            ORDER BY id
        """)
    drones = [{
        "id": r["id"],
        "code": r["code"],
        "lat": r["lat"],
        "lon": r["lon"],
        "battery_percent": r["battery_percent"],
        "status": r["status"],
        "current_task_id": r["current_task_id"],
    } for r in rows]
    await manager.broadcast({"type": "DRONES_STATE", "drones": drones})

async def set_lamp_status(pool, lamp_id: str, status: str):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE lamps SET status=$2, updated_at=now() WHERE id=$1",
            lamp_id, status
        )