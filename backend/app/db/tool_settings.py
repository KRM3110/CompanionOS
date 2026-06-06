from uuid import uuid4

from .connection import _utc_now, get_conn


async def upsert_tool_setting(scope: str, tool_id: str, enabled: bool, session_id: str | None = None) -> str:
    setting_id = str(uuid4())
    now = _utc_now()

    async with get_conn() as conn:
        async with conn.execute(
            """
            SELECT id FROM tool_settings
            WHERE scope = ? AND tool_id = ? AND (session_id IS ? OR session_id = ?)
            """,
            (scope, tool_id, session_id, session_id),
        ) as cur:
            existing = await cur.fetchone()

        if existing:
            setting_id = existing["id"]
            await conn.execute(
                """
                UPDATE tool_settings
                SET enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (1 if enabled else 0, now, setting_id),
            )
        else:
            await conn.execute(
                """
                INSERT INTO tool_settings (id, scope, session_id, tool_id, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (setting_id, scope, session_id, tool_id, 1 if enabled else 0, now, now),
            )
        await conn.commit()
    return setting_id


async def list_tool_settings(scope: str, session_id: str | None = None, limit: int = 100) -> list[dict]:
    async with get_conn() as conn:
        if scope == "global":
            async with conn.execute(
                """
                SELECT * FROM tool_settings
                WHERE scope = 'global'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        else:
            if not session_id:
                return []
            async with conn.execute(
                """
                SELECT * FROM tool_settings
                WHERE scope = 'session' AND session_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_effective_tool_enabled_map(session_id: str, tool_ids: list[str]) -> dict[str, bool]:
    enabled: dict[str, bool] = {tid: True for tid in tool_ids}
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT tool_id, enabled FROM tool_settings WHERE scope='global'"
        ) as cur:
            g = await cur.fetchall()
            for r in g:
                enabled[r["tool_id"]] = bool(r["enabled"])

        async with conn.execute(
            "SELECT tool_id, enabled FROM tool_settings WHERE scope='session' AND session_id=?",
            (session_id,),
        ) as cur:
            s = await cur.fetchall()
            for r in s:
                enabled[r["tool_id"]] = bool(r["enabled"])

    return {tid: enabled.get(tid, True) for tid in tool_ids}
