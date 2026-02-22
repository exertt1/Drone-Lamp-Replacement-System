from fastapi.types import BaseModel
from environs import Env


class Config(BaseModel):
    env: str
    host: str
    port: str

def init_config():
    env = Env()
    env.read_env()
    return Config(
        env=env("ENV"),
        host=env("HOST"),
        port=env("PORT")
    )
