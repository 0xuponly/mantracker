"""Async SQLAlchemy setup. No raw secrets in logs."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings


class Base(DeclarativeBase):
    pass


def get_engine():
    return create_async_engine(
        get_settings().database_url,
        echo=get_settings().debug,
    )


engine = get_engine()
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def _migrate_accounts_to_profile_id(sync_conn):
    """One-time: add profile_id, backfill from user_id, then recreate accounts without user_id (FK-safe)."""
    result = sync_conn.execute(text("PRAGMA table_info(accounts)"))
    rows = result.fetchall()
    columns = [row[1] for row in rows]
    if "profile_id" in columns and "user_id" not in columns:
        return

    def recreate_accounts_without_user_id():
        sync_conn.execute(text("PRAGMA foreign_keys = OFF"))
        sync_conn.execute(text(
            "CREATE TABLE accounts_new ("
            "id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "
            "profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE, "
            "name VARCHAR(255) NOT NULL, "
            "type VARCHAR(20) NOT NULL, "
            "provider VARCHAR(64), "
            "is_active INTEGER NOT NULL DEFAULT 1, "
            "created_at DATETIME, "
            "updated_at DATETIME)"
        ))
        sync_conn.execute(text(
            "INSERT INTO accounts_new (id, profile_id, name, type, provider, is_active, created_at, updated_at) "
            "SELECT id, profile_id, name, type, provider, is_active, created_at, updated_at FROM accounts"
        ))
        sync_conn.execute(text("DROP TABLE accounts"))
        sync_conn.execute(text("ALTER TABLE accounts_new RENAME TO accounts"))
        sync_conn.execute(text("PRAGMA foreign_keys = ON"))

    if "profile_id" in columns and "user_id" in columns:
        # Backfill any NULL profile_id from user_id so INSERT into accounts_new succeeds
        sync_conn.execute(text("UPDATE accounts SET profile_id = user_id WHERE profile_id IS NULL"))
        recreate_accounts_without_user_id()
        return
    if "user_id" in columns:
        result = sync_conn.execute(text("SELECT DISTINCT user_id FROM accounts"))
        user_ids = [row[0] for row in result.fetchall()]
        for uid in user_ids:
            sync_conn.execute(
                text("INSERT OR IGNORE INTO profiles (id, name, created_at) VALUES (:id, :name, datetime('now'))"),
                {"id": uid, "name": f"Profile {uid}"},
            )
        sync_conn.execute(text("ALTER TABLE accounts ADD COLUMN profile_id INTEGER"))
        sync_conn.execute(text("UPDATE accounts SET profile_id = user_id"))
        recreate_accounts_without_user_id()
    else:
        sync_conn.execute(text("ALTER TABLE accounts ADD COLUMN profile_id INTEGER"))


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_accounts_to_profile_id)
