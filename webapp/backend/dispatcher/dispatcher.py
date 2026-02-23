import asyncio
from typing import Optional, Dict, Any
from webapp.backend.database.db import fetch_hubs, fetch_idle_drones, fetch_top_queued_tasks, set_lamp_status, broadcast_drones_state
from webapp.backend.math.math import haversine_m, energy_required_pct, speed_mps
from webapp.backend.models.models import EnergyModel, DroneModel


active_missions: Dict[int, asyncio.Task] = {}   # drone_id -> task

async def try_assign_task(pool, drone_id: int, task_id: int) -> Optional[Dict[str, Any]]:
    """
    Возвращает {task_id, lamp_id} если назначили, иначе None.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            # 1) забираем задачу (только если queued и не назначена)
            task = await conn.fetchrow("""
                UPDATE tasks
                SET status='assigned', assigned_drone_id=$1, updated_at=now()
                WHERE id=$2 AND status='queued' AND assigned_drone_id IS NULL
                RETURNING id, lamp_id, hub_id
            """, drone_id, task_id)

            if not task:
                return None

            # 2) закрепляем дрона (только если idle)
            drone = await conn.fetchrow("""
                UPDATE drones
                SET status='assigned', current_task_id=$2, updated_at=now()
                WHERE id=$1 AND status='idle'
                RETURNING id
            """, drone_id, task_id)

            if not drone:
                # откатим задачу обратно
                await conn.execute("""
                    UPDATE tasks
                    SET status='queued', assigned_drone_id=NULL, updated_at=now()
                    WHERE id=$1
                """, task_id)
                return None

            return {"task_id": int(task["id"]), "lamp_id": task["lamp_id"], "hub_id": int(task["hub_id"])}

async def dispatch(pool, manager):
    hubs = await fetch_hubs(pool)
    drones = await fetch_idle_drones(pool)
    tasks = await fetch_top_queued_tasks(pool, limit=300)
    if not drones or not tasks:
        return

    for d in drones:
        drone_id = int(d["id"])
        if drone_id in active_missions:
            continue

        hub = hubs.get(int(d["hub_id"]))
        if not hub:
            continue

        # выбираем первую выполнимую задачу (по приоритету уже отсортированы)
        chosen = None
        for t in tasks:
            # считаем энергию: drone->lamp + lamp->hub
            dist_to = haversine_m(d["lat"], d["lon"], t["lamp_lat"], t["lamp_lon"])
            dist_back = haversine_m(t["lamp_lat"], t["lamp_lon"], hub["lat"], hub["lon"])
            need = energy_required_pct(dist_to, dist_back)

            if float(d["battery_percent"]) >= need:
                chosen = t
                break

        if not chosen:
            continue

        assigned = await try_assign_task(pool, drone_id=drone_id, task_id=int(chosen["task_id"]))
        if not assigned:
            continue

        # пушим статус
        await manager.broadcast({
            "type": "TASK_STATUS",
            "task_id": assigned["task_id"],
            "status": "assigned",
            "assigned_drone_id": drone_id
        })

        # меняем лампу -> IN_PROGRESS
        await set_lamp_status(pool, assigned["lamp_id"], "IN_PROGRESS")
        await manager.broadcast({"type": "LAMP_STATUS", "lamp_id": assigned["lamp_id"], "status": "IN_PROGRESS"})

        await broadcast_drones_state(pool, manager)

        # запускаем миссию
        active_missions[drone_id] = asyncio.create_task(
            run_mission(pool, manager, drone_id, assigned["task_id"], assigned["lamp_id"], assigned["hub_id"])
        )

async def run_mission(pool, manager, drone_id: int, task_id: int, lamp_id: str, hub_id: int):
    try:
        async with pool.acquire() as conn:
            drone = await conn.fetchrow("SELECT id, code, lat, lon, battery_percent FROM drones WHERE id=$1", drone_id)
            lamp = await conn.fetchrow("SELECT id, lat, lon FROM lamps WHERE id=$1", lamp_id)
            hub = await conn.fetchrow("SELECT id, lat, lon FROM hubs WHERE id=$1", hub_id)

        if not drone or not lamp or not hub:
            return

        code = drone["code"]
        batt = float(drone["battery_percent"])

        # переводим задачу и дрона в enroute
        async with pool.acquire() as conn:
            await conn.execute("UPDATE tasks SET status='enroute', updated_at=now() WHERE id=$1", task_id)
            await conn.execute("UPDATE drones SET status='enroute', updated_at=now() WHERE id=$1", drone_id)

        # линия маршрута hub->lamp->hub (для карты)
        await manager.broadcast({
            "type": "ROUTE_UPDATE",
            "drone_id": drone_id,
            "task_id": task_id,
            "polyline": [
                [hub["lat"], hub["lon"]],
                [lamp["lat"], lamp["lon"]],
                [hub["lat"], hub["lon"]],
            ]
        })

        await manager.broadcast({"type": "TASK_STATUS", "task_id": task_id, "status": "enroute", "assigned_drone_id": drone_id})
        await broadcast_drones_state(pool, manager)

        # полёт туда
        batt = await fly_segment(pool, manager, drone_id, code, batt, task_id, "to_lamp",
                                 drone["lat"], drone["lon"], lamp["lat"], lamp["lon"])

        # работа на лампе
        async with pool.acquire() as conn:
            await conn.execute("UPDATE tasks SET status='working', updated_at=now() WHERE id=$1", task_id)
            await conn.execute("UPDATE drones SET status='working', updated_at=now() WHERE id=$1", drone_id)
        await manager.broadcast({"type": "TASK_STATUS", "task_id": task_id, "status": "working", "assigned_drone_id": drone_id})
        await broadcast_drones_state(pool, manager)

        batt = max(0.0, batt - EnergyModel.WORK_COST)

        # тик во время работы (чтобы видно было батарею/статус)
        work_steps = max(1, int(DroneModel.WORK_TIME_SEC))
        for _ in range(work_steps):
            await asyncio.sleep(1)
            await manager.broadcast({
                "type": "DRONE_TICK",
                "drone_id": drone_id,
                "code": code,
                "lat": lamp["lat"],
                "lon": lamp["lon"],
                "battery_percent": round(batt, 2),
                "dist_remaining_m": 0,
                "phase": "working",
                "task_id": task_id
            })

        # лампа починена
        await set_lamp_status(pool, lamp_id, "FIXED")
        await manager.broadcast({"type": "LAMP_STATUS", "lamp_id": lamp_id, "status": "FIXED"})

        # возврат
        async with pool.acquire() as conn:
            await conn.execute("UPDATE tasks SET status='returning', updated_at=now() WHERE id=$1", task_id)
            await conn.execute("UPDATE drones SET status='returning', updated_at=now() WHERE id=$1", drone_id)
        await manager.broadcast({"type": "TASK_STATUS", "task_id": task_id, "status": "returning", "assigned_drone_id": drone_id})
        await broadcast_drones_state(pool, manager)

        batt = await fly_segment(pool, manager, drone_id, code, batt, task_id, "to_hub",
                                 lamp["lat"], lamp["lon"], hub["lat"], hub["lon"])

        # завершение
        async with pool.acquire() as conn:
            await conn.execute("UPDATE tasks SET status='done', updated_at=now() WHERE id=$1", task_id)
            await conn.execute("UPDATE drones SET status='charging', current_task_id=NULL, updated_at=now() WHERE id=$1", drone_id)

        await manager.broadcast({"type": "TASK_STATUS", "task_id": task_id, "status": "done", "assigned_drone_id": drone_id})
        await broadcast_drones_state(pool, manager)

        # зарядка до 100%
        batt = await charge_drone(pool, manager, drone_id, code, batt, hub["lat"], hub["lon"])

        async with pool.acquire() as conn:
            await conn.execute("UPDATE drones SET status='idle', updated_at=now() WHERE id=$1", drone_id)

        await broadcast_drones_state(pool, manager)

        # после завершения — пытаемся взять следующую задачу
        await dispatch(pool, manager)

    finally:
        active_missions.pop(drone_id, None)


async def fly_segment(pool, manager, drone_id: int, code: str, batt: float, task_id: int,
                      phase: str, lat0: float, lon0: float, lat1: float, lon1: float) -> float:
    dist_total = haversine_m(lat0, lon0, lat1, lon1)
    v = speed_mps()
    duration = max(1.0, dist_total / v)
    t0 = time.monotonic()

    last_lat, last_lon = lat0, lon0

    while True:
        elapsed = time.monotonic() - t0
        k = min(1.0, elapsed / duration)

        lat = lat0 + (lat1 - lat0) * k
        lon = lon0 + (lon1 - lon0) * k

        # пройденная дистанция за тик
        step = haversine_m(last_lat, last_lon, lat, lon)
        batt = max(0.0, batt - (step / 1000.0) * EnergyModel.ENERGY_PER_KM)

        dist_rem = haversine_m(lat, lon, lat1, lon1)

        # пишем в БД позицию и батарею
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE drones SET lat=$2, lon=$3, battery_percent=$4, updated_at=now() WHERE id=$1",
                drone_id, lat, lon, int(max(0, min(100, batt)))
            )

        await manager.broadcast({
            "type": "DRONE_TICK",
            "drone_id": drone_id,
            "code": code,
            "lat": lat,
            "lon": lon,
            "battery_percent": round(batt, 2),
            "dist_remaining_m": int(dist_rem),
            "phase": phase,
            "task_id": task_id
        })

        if k >= 1.0:
            break

        last_lat, last_lon = lat, lon
        await asyncio.sleep(1)

    return batt


async def charge_drone(pool, manager, drone_id: int, code: str, batt: float, lat: float, lon: float) -> float:
    # CHARGE_FULL_MIN: 0->100% за N минут => %/сек
    rate_per_sec = 100.0 / (60 * 60.0)
    while batt < 100.0:
        await asyncio.sleep(1)
        batt = min(100.0, batt + rate_per_sec)

        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE drones SET battery_percent=$2, lat=$3, lon=$4, updated_at=now() WHERE id=$1",
                drone_id, int(batt), lat, lon
            )

        await manager.broadcast({
            "type": "DRONE_TICK",
            "drone_id": drone_id,
            "code": code,
            "lat": lat,
            "lon": lon,
            "battery_percent": round(batt, 2),
            "dist_remaining_m": 0,
            "phase": "charging",
            "task_id": None
        })
    return batt