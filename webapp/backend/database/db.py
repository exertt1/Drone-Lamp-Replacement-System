import asyncio
import asyncpg
from webapp.backend.config.config import config



async def init_database():
    con = await asyncpg.connect(config.get("database_url"))

    await con.execute(
        """
        CREATE TABLE task_status IF NOT EXISTS(
            id INT PRIMARY KEY,
            status_name TEXT NOT NULL
        )
        """
    )

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
        CREATE TABLE priorities IF NOT EXISTS (
            id INT PRIMARY KEY,
            priority TEXT NOT NULL
        )
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
        CREATE TABLE tasks IF NOT EXISTS (
            id INT PRIMARY KEY AUTOINCREMENT,
            lamp_id INT REFERENCES lamps(id),
            target VECTOR(3),
            priority_id INT REFERENCES priorities(id),
            estimated_time DECIMAL(3 ,1),
            estimated_energy DECIMAL(3, 2),
            
        )
        """
    )

    await con.execute(
        """
        CREATE TABLE drones IF NOT EXISTS (
            id INT PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            batery DECIMAL(3, 2) NOT NULL CHECK(batery >= 0 OR batery <= 1),
            mode_id TEXT REFERENCES modes(id),
            connection JSONB NOT NULL,
            current_task_id INT REFERENCES tasks(id),
            attempts INT
        """
    )
    await con.cloose()