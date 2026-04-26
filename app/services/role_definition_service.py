"""
可配置角色定义（role_definitions）的增删改查，与 users.role、role_templates 对齐。
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

import pymysql.cursors

from app.database import get_conn
from app.services.permission_service import PermissionService

logger = logging.getLogger(__name__)

ROLE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,29}$")


class RoleDefinitionService:
    @staticmethod
    def list_roles(*, include_inactive: bool = False) -> List[Dict[str, Any]]:
        with get_conn() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                if include_inactive:
                    cur.execute(
                        "SELECT id, code, name, description, sort_order, is_system, "
                        "is_active, created_at, updated_at FROM role_definitions "
                        "ORDER BY sort_order ASC, code ASC"
                    )
                else:
                    cur.execute(
                        "SELECT id, code, name, description, sort_order, is_system, "
                        "is_active, created_at, updated_at FROM role_definitions "
                        "WHERE is_active = 1 ORDER BY sort_order ASC, code ASC"
                    )
                return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def get_by_code(code: str) -> Optional[Dict[str, Any]]:
        with get_conn() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(
                    "SELECT id, code, name, description, sort_order, is_system, "
                    "is_active, created_at, updated_at FROM role_definitions WHERE code=%s",
                    (code,),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    @staticmethod
    def _count_users_with_role(code: str) -> int:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM users WHERE role=%s AND is_active=1", (code,)
                )
                return int(cur.fetchone()[0])

    @staticmethod
    def create_role(
        code: str,
        name: str,
        description: Optional[str] = None,
        sort_order: int = 100,
    ) -> int:
        code = (code or "").strip().lower()
        if not ROLE_CODE_PATTERN.match(code):
            raise ValueError(
                "角色代码须为小写字母开头，2–30 位，仅含小写字母、数字、下划线"
            )
        name = (name or "").strip()
        if not name:
            raise ValueError("显示名称不能为空")

        with get_conn() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute("SELECT 1 FROM role_definitions WHERE code=%s", (code,))
                if cur.fetchone():
                    raise ValueError(f"角色代码已存在: {code}")
                cur.execute(
                    """
                    INSERT INTO role_definitions
                    (code, name, description, sort_order, is_system, is_active)
                    VALUES (%s, %s, %s, %s, 0, 1)
                    """,
                    (code, name, description, sort_order),
                )
                new_id = int(cur.lastrowid)
                cur.execute(
                    """
                    INSERT IGNORE INTO role_templates (role, template_json)
                    VALUES (%s, '{}')
                    """,
                    (code,),
                )
            conn.commit()
        PermissionService.refresh_roles_cache()
        logger.info("新建角色: code=%s id=%s", code, new_id)
        return new_id

    @staticmethod
    def update_role(
        code: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        sort_order: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> bool:
        row = RoleDefinitionService.get_by_code(code)
        if not row:
            raise ValueError("角色不存在")

        if is_active is False and RoleDefinitionService._count_users_with_role(code) > 0:
            raise ValueError("仍有用户使用该角色，无法停用，请先调整用户角色")

        updates: List[str] = []
        params: List[Any] = []
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("显示名称不能为空")
            updates.append("name=%s")
            params.append(name)
        if description is not None:
            updates.append("description=%s")
            params.append(description)
        if sort_order is not None:
            updates.append("sort_order=%s")
            params.append(sort_order)
        if is_active is not None:
            updates.append("is_active=%s")
            params.append(1 if is_active else 0)

        if not updates:
            return True

        params.append(code)
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE role_definitions SET {', '.join(updates)} WHERE code=%s",
                    tuple(params),
                )
            conn.commit()
        PermissionService.refresh_roles_cache()
        return True

    @staticmethod
    def delete_role(code: str) -> bool:
        row = RoleDefinitionService.get_by_code(code)
        if not row:
            raise ValueError("角色不存在")
        if int(row.get("is_system") or 0):
            raise ValueError("系统内置角色不可删除")
        if RoleDefinitionService._count_users_with_role(code) > 0:
            raise ValueError("仍有用户使用该角色，无法删除")

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM role_templates WHERE role=%s", (code,))
                cur.execute("DELETE FROM role_definitions WHERE code=%s", (code,))
            conn.commit()
        PermissionService.refresh_roles_cache()
        logger.info("已删除角色: %s", code)
        return True
