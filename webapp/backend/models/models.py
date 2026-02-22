from fastapi.types import BaseModel
from starlette.routing import Match


class TasksStatus(BaseModel):
    QUEUED = "QUEUED"
    ASSIGNED = "ASSIGNED"
    ENROUTE = "ENROUTE"
    WORKING = "WORKING"
    DONE = "DONE"
    FAILED = "FAILED"

class Drone(BaseModel):
    id: int
    name: str
    speed: float
    charge: float
    mode: str
    connection: dict
    current_task_id: int

class Task(BaseModel):
    id: int
    lamp_id: int
    target: list[float]
    priority: str
    status: str
