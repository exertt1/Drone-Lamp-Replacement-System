import asyncio
from fastapi.types import BaseModel
from fastapi import WebSocket
from typing import Dict, Any, List, ClassVar
from enum import Enum

ACTIVE_STATUSES = ("queued", "assigned", "enroute", "working", "returning")
PRIORITY_MAP = {"low": 1, "medium": 2, "high": 3}


class DroneModes(BaseModel):
    IDLE: ClassVar[str] = "IDLE"
    ASSIGNED: ClassVar[str] = "ASSIGNED"
    ENROUTE_TO_LAMP: ClassVar[str] = "ENROUTE_TO_LAMP"
    WORKING: ClassVar[str]= "WORKING "
    RETURNING: ClassVar[str] = "RETURNING"
    CHARGING: ClassVar[str] = "CHARGING"
    ERROR: ClassVar[str] = "ERROR"

class LampStatus(BaseModel):
    OK: ClassVar[str] = "OK"
    PLAN: ClassVar[str] = "PLAN"
    URGENT: ClassVar[str] = "URGENT"
    IN_PROGRESS: ClassVar[str] = "IN_PROGRESS"
    FIXED: ClassVar[str] = "FIXED"

    lamp_id: str
    status: str


class TasksStatus(BaseModel):
    QUEUED: ClassVar[str] = "QUEUED"
    ASSIGNED: ClassVar[str] = "ASSIGNED"
    ENROUTE: ClassVar[str] = "ENROUTE"
    WORKING: ClassVar[str] = "WORKING"
    DONE: ClassVar[str] = "DONE"
    FAILED: ClassVar[str] = "FAILED"
    RETURNING: ClassVar[str] = "RETURNING"

class Lamp(BaseModel):
    id: int
    # lat: str
    # lon: str
    loc: str
    state: str
    status: str

class Drone(BaseModel):
    FULL_CHARGING_TIME: ClassVar[str] = 60

    id: int
    code: str
    hub_id: int
    speed: float
    lat: float
    lon: float
    battery_percent: int
    mode: str
    connection: dict
    current_task_id: int
    attempts: int

    async def charging(self):
        charging_time = (100 - self.charge) / (100 / self.FULL_CHARGING_TIME)
        self.mode = DroneModes.CHARGING
        await asyncio.sleep(charging_time)

class Task(BaseModel):
    id: int
    lamp_id: int
    hub_id: int
    priority_id: str
    status: str
    sort_rank: int
    assigned_drone_id: int
    created_at: str
    updated_at: str

class Hub(BaseModel):
    id: int
    name: str
    lat: str
    lon: str

class DroneModel(BaseModel):
    mAh: ClassVar[int] = 8000
    MAXIMUM_RANGE_KM: ClassVar[int] = 25
    MAX_SPEED_KMH: ClassVar[int] = 130
    AVG_SPEED_KMH: ClassVar[int] = 70
    WORK_TIME_SEC: ClassVar[int] = 120

class EnergyModel(BaseModel):
    ENERGY_PER_KM: ClassVar[float] = 100/DroneModel.MAXIMUM_RANGE_KM
    #постоянные потери
    TAKEOFF_LANDING_COST: ClassVar[int] = 2
    #замена/позиционирование
    WORK_COST: ClassVar[int] = 2
    #запас на ветер/ошибку
    SAFETY_MARGIN: ClassVar[int] = 10
    MIN_PCT: ClassVar[int] = 30

class ConnectionManager:
    def __init__(self) -> None:
        self.active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        dead: List[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

