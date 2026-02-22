import asyncio
import asyncpg
from webapp.backend.config.config import config



async def init_database():
    con = await asyncpg.connect(config.get("database_url"))
    await con.execute(
        """
        CREATE TABLE modes IF NOT EXISTS(
        id INT PRIMARY KEY AUTOINCREMENT,
        mode TEXT NOT NULL
        );
        """
    )
    await con.execute(
        """
        CREATE TABLE modes IF NOT EXISTS (
            id INT PRIMARY KEY AUTOINCREMENT,
            mode TEXT NOT NULL
        );
        """
    )
    await con.execute(
        """
        CREATE TABLE drones IF NOT EXISTS (
            id INT PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            batery DECIMAL(3, 2) NOT NULL CHECK(batery >= 0 OR batery <= 1),
            mode_id TEXT REFERENCES modes(id),
            signal_rssi INT,
            last_heartbeat TIME
        );
        """
    )
    await con.execute(
        """
        CREATE TABLE tasks IF NOT EXISTS (
            id INT PRIMARY KEY AUTOINCREMENT,
            lamp_id INT REFERENCES lamps(id),
            target
        )
        """
    )