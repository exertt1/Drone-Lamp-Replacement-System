import os
import asyncio
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")  # postgresql://user:pass@host:5432/dbname

HUB_NAME = "Kazan Hub"
HUB_LAT = 55.7963
HUB_LON = 49.1088

DRONES_COUNT = 7
LAMPS_COUNT = 10_000


async def init_database():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL не задан в .env")

    pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=10)

    async with pool.acquire() as con:
        # 0) СНЕСЁМ ВСЁ (DEV!)
        await con.execute("DROP TABLE IF EXISTS tasks CASCADE;")
        await con.execute("DROP TABLE IF EXISTS drones CASCADE;")
        await con.execute("DROP TABLE IF EXISTS lamps CASCADE;")
        await con.execute("DROP TABLE IF EXISTS hubs CASCADE;")
        await con.execute("DROP TABLE IF EXISTS priorities CASCADE;")

        # 1) priorities
        await con.execute("""
        CREATE TABLE priorities (
            id smallint PRIMARY KEY,
            priority text NOT NULL UNIQUE
        );
        """)
        await con.execute("""
        INSERT INTO priorities (id, priority) VALUES
          (1,'low'), (2,'medium'), (3,'high');
        """)

        # 2) hubs
        await con.execute("""
        CREATE TABLE hubs (
            id bigserial PRIMARY KEY,
            name text NOT NULL,
            lat double precision NOT NULL,
            lon double precision NOT NULL
        );
        """)

        # 3) lamps
        # ВАЖНО: id TEXT, чтобы спокойно хранить "KZN-00001" и т.п.
        await con.execute("""
        CREATE TABLE lamps (
            id text PRIMARY KEY,
            lat double precision NOT NULL,
            lon double precision NOT NULL,
            status text NOT NULL DEFAULT 'OK',
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT lamps_status_chk CHECK (status IN ('OK','PLAN','URGENT','IN_PROGRESS','FIXED'))
        );
        """)
        await con.execute("CREATE INDEX lamps_lat_idx ON lamps(lat);")
        await con.execute("CREATE INDEX lamps_lon_idx ON lamps(lon);")

        # 4) drones
        await con.execute("""
        CREATE TABLE drones (
            id bigserial PRIMARY KEY,
            code text NOT NULL UNIQUE,
            hub_id bigint NOT NULL REFERENCES hubs(id) ON DELETE RESTRICT,
            lat double precision NOT NULL,
            lon double precision NOT NULL,
            battery_percent int NOT NULL CHECK(battery_percent >= 0 AND battery_percent <= 100),
            status text NOT NULL DEFAULT 'idle',
            current_task_id bigint NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT drones_status_chk CHECK (status IN ('idle','assigned','enroute','working','returning','charging','maintenance','error'))
        );
        """)

        # 5) tasks
        await con.execute("""
        CREATE TABLE tasks (
            id bigserial PRIMARY KEY,
            lamp_id text NOT NULL REFERENCES lamps(id) ON DELETE RESTRICT,
            hub_id bigint NOT NULL REFERENCES hubs(id) ON DELETE RESTRICT,
            priority_id smallint NOT NULL REFERENCES priorities(id) ON DELETE RESTRICT,
            status text NOT NULL DEFAULT 'queued',
            sort_rank bigint NOT NULL DEFAULT (EXTRACT(EPOCH FROM now())::bigint),
            assigned_drone_id bigint NULL REFERENCES drones(id) ON DELETE SET NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT tasks_status_chk CHECK (status IN ('queued','assigned','enroute','working','returning','done','failed','canceled'))
        );
        """)
        await con.execute("CREATE INDEX tasks_status_idx ON tasks(status);")
        await con.execute("CREATE INDEX tasks_sort_idx ON tasks(sort_rank DESC, created_at DESC);")

        # 6) 1 активная задача на одну лампу
        await con.execute("""
        CREATE UNIQUE INDEX uniq_active_task_per_lamp
        ON tasks (lamp_id)
        WHERE status IN ('queued','assigned','enroute','working','returning');
        """)

        # ---- SEED ----
        # Hub
        hub_id = await con.fetchval(
            "INSERT INTO hubs(name, lat, lon) VALUES($1,$2,$3) RETURNING id;",
            HUB_NAME, HUB_LAT, HUB_LON
        )

        # 7 drones
        # (позиция = хаб, батарея — разные)
        for i in range(1, DRONES_COUNT + 1):
            code = f"DRN-{i:03d}"
            batt = [96, 88, 72, 64, 91, 55, 84][i-1] if i <= 7 else 80
            status = "charging" if i == 4 else "idle"
            await con.execute(
                """
                INSERT INTO drones(code, hub_id, lat, lon, battery_percent, status)
                VALUES($1,$2,$3,$4,$5,$6);
                """,
                code, hub_id, HUB_LAT, HUB_LON, batt, status
            )

        # 10 000 lamps (без задач!)
        # Разброс по Казани (условный прямоугольник)
        await con.execute(f"""
        INSERT INTO lamps (id, lat, lon, status)
        SELECT
          'KZN-' || lpad(gs::text, 5, '0') AS id,
          (55.70 + random() * (55.86 - 55.70))::double precision AS lat,
          (49.03 + random() * (49.30 - 49.03))::double precision AS lon,
          CASE
            WHEN random() < 0.02 THEN 'URGENT'
            WHEN random() < 0.05 THEN 'PLAN'
            ELSE 'OK'
          END AS status
        FROM generate_series(1, {LAMPS_COUNT}) AS gs;
        """)

    await pool.close()
    print(DATABASE_URL)


if __name__ == "__main__":
    asyncio.run(init_database())