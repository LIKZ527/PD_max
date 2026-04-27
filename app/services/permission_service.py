"""
角色模板与用户细粒度权限（动态权限列）。
与 PD 项目思路一致，表名适配 PD_max：permission_definitions / user_permissions / role_templates。
初始仅写入 admin 角色模板且 template_json 为空对象（全部未授权），由前端调接口维护定义与模板。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import pymysql.cursors

from app.database import get_conn

logger = logging.getLogger(__name__)

# 内置默认代码（JWT 管理员判断仍用 admin）
ADMIN_ROLE = "admin"
USER_ROLE = "user"

# 兼容旧 import；新代码请用 get_valid_role_codes()
VALID_ROLES = (ADMIN_ROLE, USER_ROLE)


def _q(ident: str) -> str:
    return "`" + ident.replace("`", "``") + "`"


class PermissionService:
    _fields_cache: Optional[List[str]] = None
    _labels_cache: Optional[Dict[str, str]] = None
    _roles_cache_active: Optional[List[str]] = None
    _roles_cache_all: Optional[List[str]] = None

    @classmethod
    def _load_role_codes(cls, active_only: bool) -> List[str]:
        try:
            with get_conn() as conn:
                with conn.cursor(pymysql.cursors.DictCursor) as cur:
                    if active_only:
                        cur.execute(
                            "SELECT code FROM role_definitions WHERE is_active=1 "
                            "ORDER BY sort_order ASC, code ASC"
                        )
                    else:
                        cur.execute(
                            "SELECT code FROM role_definitions ORDER BY sort_order ASC, code ASC"
                        )
                    rows = cur.fetchall()
            if rows:
                return [str(r["code"]) for r in rows]
            if active_only:
                # 避免配置误操作导致「无可分配角色」
                return [ADMIN_ROLE, USER_ROLE]
        except Exception:
            logger.debug("读取 role_definitions 失败，使用内置角色列表", exc_info=True)
        return [ADMIN_ROLE, USER_ROLE]

    @classmethod
    def get_valid_role_codes(cls, *, active_only: bool = True) -> List[str]:
        if active_only:
            if cls._roles_cache_active is None:
                cls._roles_cache_active = cls._load_role_codes(True)
            return list(cls._roles_cache_active)
        if cls._roles_cache_all is None:
            cls._roles_cache_all = cls._load_role_codes(False)
        return list(cls._roles_cache_all)

    @classmethod
    def refresh_roles_cache(cls) -> None:
        cls._roles_cache_active = None
        cls._roles_cache_all = None

    @classmethod
    def _load_definitions(cls) -> None:
        with get_conn() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(
                    "SELECT field_name, label FROM permission_definitions ORDER BY field_name"
                )
                rows = cur.fetchall()
                cls._fields_cache = [r["field_name"] for r in rows]
                cls._labels_cache = {r["field_name"]: r["label"] for r in rows}

    @classmethod
    def get_all_fields(cls) -> List[str]:
        if cls._fields_cache is None:
            cls._load_definitions()
        assert cls._fields_cache is not None
        return cls._fields_cache

    @classmethod
    def get_label(cls, field_name: str) -> str:
        if cls._labels_cache is None:
            cls._load_definitions()
        assert cls._labels_cache is not None
        return cls._labels_cache.get(field_name, field_name)

    @classmethod
    def refresh_cache(cls) -> None:
        cls._fields_cache = None
        cls._labels_cache = None
        cls._load_definitions()

    @staticmethod
    def ensure_table_exists() -> None:
        """
        按 role_definitions 为每个角色补一条 role_templates（INSERT IGNORE，JSON 为空对象）。
        若尚无 role_definitions 表数据，则回退为 admin、user。
        """
        codes = PermissionService.get_valid_role_codes(active_only=False)
        with get_conn() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                for role in codes:
                    cur.execute(
                        """
                        INSERT IGNORE INTO role_templates (role, template_json)
                        VALUES (%s, %s)
                        """,
                        (role, "{}"),
                    )
            conn.commit()
        logger.info("已同步角色模板占位：%s", ",".join(codes))

    @staticmethod
    def get_role_template(role: str) -> Dict[str, int]:
        with get_conn() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(
                    "SELECT template_json FROM role_templates WHERE role=%s", (role,)
                )
                row = cur.fetchone()
                if row:
                    template = json.loads(row["template_json"] or "{}")
                else:
                    template = {}
        all_fields = PermissionService.get_all_fields()
        return {field: int(template.get(field, 0)) for field in all_fields}

    @staticmethod
    def apply_role_template_to_users(
        role: str, user_ids: Optional[List[int]] = None
    ) -> int:
        template = PermissionService.get_role_template(role)
        all_fields = PermissionService.get_all_fields()

        with get_conn() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                if user_ids is None:
                    cur.execute(
                        "SELECT user_id FROM user_permissions WHERE role=%s", (role,)
                    )
                    rows = cur.fetchall()
                    user_ids = [int(r["user_id"]) for r in rows]
                    if not user_ids:
                        return 0

                for uid in user_ids:
                    cur.execute(
                        "DELETE FROM user_permissions WHERE user_id=%s", (uid,)
                    )
                    fields = ["user_id", "role"] + all_fields
                    values: List[Any] = [uid, role]
                    for f in all_fields:
                        values.append(template.get(f, 0))
                    placeholders = ",".join(["%s"] * len(values))
                    fields_sql = ",".join(_q(f) for f in fields)
                    sql = f"INSERT INTO {_q('user_permissions')} ({fields_sql}) VALUES ({placeholders})"
                    cur.execute(sql, tuple(values))
            conn.commit()
        logger.info("已将角色 %s 的模板应用到 %s 个用户", role, len(user_ids))
        return len(user_ids)

    @staticmethod
    def update_role_template(
        role: str, permissions: Dict[str, bool], apply_to_existing: bool = False
    ) -> bool:
        valid = PermissionService.get_valid_role_codes(active_only=False)
        if role not in valid:
            raise ValueError(f"无效角色，可选: {valid}")
        all_fields = PermissionService.get_all_fields()
        full_permissions = {
            field: 1 if permissions.get(field, False) else 0 for field in all_fields
        }
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO role_templates (role, template_json)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE template_json = VALUES(template_json)
                    """,
                    (role, json.dumps(full_permissions)),
                )
            conn.commit()
        if apply_to_existing:
            PermissionService.apply_role_template_to_users(role)
        return True

    @staticmethod
    def get_all_role_templates() -> Dict[str, Dict[str, int]]:
        templates: Dict[str, Dict[str, int]] = {}
        with get_conn() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute("SELECT role, template_json FROM role_templates")
                for row in cur.fetchall():
                    raw = json.loads(row["template_json"] or "{}")
                    templates[row["role"]] = {
                        k: int(v) for k, v in raw.items() if isinstance(v, (int, bool))
                    }
        return templates

    @staticmethod
    def create_default_permissions(user_id: int, role: str) -> bool:
        active = PermissionService.get_valid_role_codes(active_only=True)
        if role not in active:
            role = USER_ROLE if USER_ROLE in active else (active[0] if active else USER_ROLE)
        template = PermissionService.get_role_template(role)
        all_fields = PermissionService.get_all_fields()

        with get_conn() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(
                    "SELECT id FROM user_permissions WHERE user_id=%s", (user_id,)
                )
                if cur.fetchone():
                    return False
                fields = ["user_id", "role"] + all_fields
                values: List[Any] = [user_id, role]
                for f in all_fields:
                    values.append(template.get(f, 0))
                placeholders = ",".join(["%s"] * len(values))
                fields_sql = ",".join(_q(f) for f in fields)
                sql = f"INSERT INTO {_q('user_permissions')} ({fields_sql}) VALUES ({placeholders})"
                cur.execute(sql, tuple(values))
            conn.commit()
        logger.info("创建默认权限: user_id=%s role=%s", user_id, role)
        return True

    @staticmethod
    def get_user_permissions(user_id: int) -> Optional[Dict[str, Any]]:
        with get_conn() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, username, real_name, role AS base_role
                    FROM users
                    WHERE id=%s AND is_active=1
                    """,
                    (user_id,),
                )
                user = cur.fetchone()
                if not user:
                    return None

                cur.execute(
                    "SELECT * FROM user_permissions WHERE user_id=%s", (user_id,)
                )
                perm_row = cur.fetchone()
                if not perm_row:
                    PermissionService.create_default_permissions(
                        user_id, str(user["base_role"])
                    )
                    cur.execute(
                        "SELECT * FROM user_permissions WHERE user_id=%s", (user_id,)
                    )
                    perm_row = cur.fetchone()

                all_fields = PermissionService.get_all_fields()
                permissions: Dict[str, bool] = {}
                for field in all_fields:
                    permissions[field] = bool(perm_row.get(field, 0)) if perm_row else False

                with_labels: Dict[str, Dict[str, Any]] = {}
                for field, value in permissions.items():
                    with_labels[field] = {
                        "value": value,
                        "label": PermissionService.get_label(field),
                    }

                return {
                    "user_id": user_id,
                    "username": user["username"],
                    "real_name": user.get("real_name"),
                    "base_role": user["base_role"],
                    "current_role": perm_row["role"] if perm_row else user["base_role"],
                    "role": perm_row["role"] if perm_row else user["base_role"],
                    "permissions": permissions,
                    "permissions_with_labels": with_labels,
                    "updated_at": str(perm_row["updated_at"]) if perm_row else None,
                }

    @staticmethod
    def update_permissions(
        user_id: int,
        role: Optional[str] = None,
        permissions: Optional[Dict[str, bool]] = None,
    ) -> bool:
        if role and role not in PermissionService.get_valid_role_codes(active_only=True):
            raise ValueError(
                f"无效角色，可选: {PermissionService.get_valid_role_codes(active_only=True)}"
            )

        with get_conn() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(
                    "SELECT id FROM user_permissions WHERE user_id=%s", (user_id,)
                )
                perm_row = cur.fetchone()
                if not perm_row:
                    cur.execute("SELECT role FROM users WHERE id=%s", (user_id,))
                    u = cur.fetchone()
                    if not u:
                        raise ValueError("用户不存在")
                    PermissionService.create_default_permissions(
                        user_id, role or str(u["role"])
                    )
                    cur.execute(
                        "SELECT id FROM user_permissions WHERE user_id=%s", (user_id,)
                    )
                    perm_row = cur.fetchone()

                updates: List[str] = []
                params: List[Any] = []
                if role:
                    updates.append("role=%s")
                    params.append(role)
                if permissions:
                    for perm_field, value in permissions.items():
                        if perm_field not in PermissionService.get_all_fields():
                            raise ValueError(f"无效的权限字段: {perm_field}")
                        updates.append(f"{_q(perm_field)}=%s")
                        params.append(1 if value else 0)
                if not updates:
                    return True
                params.append(user_id)
                set_clause = ", ".join(updates)
                sql = f"UPDATE {_q('user_permissions')} SET {set_clause} WHERE user_id=%s"
                cur.execute(sql, tuple(params))
            conn.commit()
        logger.info("更新权限: user_id=%s", user_id)
        return True

    @staticmethod
    def check_permission(user_id: int, permission_field: str) -> bool:
        if permission_field not in PermissionService.get_all_fields():
            return False
        with get_conn() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(
                    f"SELECT {_q(permission_field)} AS pf FROM user_permissions WHERE user_id=%s",
                    (user_id,),
                )
                row = cur.fetchone()
                if not row:
                    return False
                return bool(row.get("pf", 0))

    @staticmethod
    def list_all_permissions(
        page: int = 1,
        size: int = 20,
        role: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> Dict[str, Any]:
        all_fields = PermissionService.get_all_fields()
        select_perm = (
            ",".join(f"p.{_q(f)} AS {_q(f)}" for f in all_fields) if all_fields else ""
        )

        with get_conn() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                where_conditions = ["u.is_active = 1"]
                params: List[Any] = []
                if role:
                    where_conditions.append(
                        "(p.role=%s OR (p.role IS NULL AND u.role=%s))"
                    )
                    params.extend([role, role])
                if keyword:
                    where_conditions.append(
                        "(u.username LIKE %s OR u.real_name LIKE %s OR IFNULL(u.phone,'') LIKE %s)"
                    )
                    like = f"%{keyword}%"
                    params.extend([like, like, like])
                where_clause = " AND ".join(where_conditions)

                cur.execute(
                    f"""
                    SELECT COUNT(*) AS total FROM users u
                    LEFT JOIN user_permissions p ON u.id=p.user_id
                    WHERE {where_clause}
                    """,
                    tuple(params),
                )
                total = int(cur.fetchone()["total"])

                offset = (page - 1) * size
                perm_select = f",{select_perm}" if select_perm else ""
                cur.execute(
                    f"""
                    SELECT u.id AS user_id, u.username, u.real_name,
                           COALESCE(p.role, u.role) AS role
                           {perm_select}
                    FROM users u
                    LEFT JOIN user_permissions p ON u.id=p.user_id
                    WHERE {where_clause}
                    ORDER BY u.created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    tuple(params + [size, offset]),
                )
                rows = cur.fetchall()

        result_list: List[Dict[str, Any]] = []
        for row in rows:
            item: Dict[str, Any] = {
                "user_id": row["user_id"],
                "username": row["username"],
                "real_name": row.get("real_name"),
                "role": row["role"],
            }
            for field in all_fields:
                item[field] = bool(row.get(field, 0))
            item["permissions_list"] = [
                {
                    "field": field,
                    "label": PermissionService.get_label(field),
                    "value": bool(row.get(field, 0)),
                }
                for field in all_fields
            ]
            result_list.append(item)

        return {
            "total": total,
            "page": page,
            "size": size,
            "pages": (total + size - 1) // size if size else 0,
            "list": result_list,
        }

    @staticmethod
    def delete_permissions(user_id: int) -> bool:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM user_permissions WHERE user_id=%s", (user_id,)
                )
            conn.commit()
        return True

    @staticmethod
    def add_permission_definition(field_name: str, label: str) -> bool:
        if not re.match(r"^perm_[a-z][a-z0-9_]*$", field_name):
            raise ValueError(
                "字段名必须以 perm_ 开头，且只能包含小写字母、数字、下划线"
            )
        with get_conn() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(
                    "SELECT 1 FROM permission_definitions WHERE field_name=%s",
                    (field_name,),
                )
                if cur.fetchone():
                    raise ValueError(f"权限字段 {field_name} 已存在")

                cur.execute(f"SHOW COLUMNS FROM {_q('user_permissions')}")
                meta_cols = {"id", "user_id", "role", "created_at", "updated_at"}
                existing = [r["Field"] for r in cur.fetchall()]
                perm_cols = [c for c in existing if c not in meta_cols]
                after_column = perm_cols[-1] if perm_cols else "role"

                alter_sql = (
                    f"ALTER TABLE {_q('user_permissions')} ADD COLUMN {_q(field_name)} "
                    f"TINYINT DEFAULT 0 COMMENT %s AFTER {_q(after_column)}"
                )
                cur.execute(alter_sql, (label,))

                cur.execute(
                    "INSERT INTO permission_definitions (field_name, label) VALUES (%s, %s)",
                    (field_name, label),
                )

                cur.execute("SELECT role, template_json FROM role_templates")
                for trow in cur.fetchall():
                    trole = trow["role"]
                    tpl = json.loads(trow["template_json"] or "{}")
                    if field_name not in tpl:
                        tpl[field_name] = 0
                        cur.execute(
                            "UPDATE role_templates SET template_json=%s WHERE role=%s",
                            (json.dumps(tpl), trole),
                        )
            conn.commit()
        PermissionService.refresh_cache()
        logger.info("新增权限字段: %s (%s)", field_name, label)
        return True

    @staticmethod
    def remove_permission_definition(field_name: str) -> bool:
        protected = ("perm_permission_manage",)
        if field_name in protected:
            raise ValueError(f"字段 {field_name} 为系统保留，不可删除")

        with get_conn() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(
                    "SELECT 1 FROM permission_definitions WHERE field_name=%s",
                    (field_name,),
                )
                if not cur.fetchone():
                    raise ValueError(f"权限字段 {field_name} 不存在")

                cur.execute(
                    f"ALTER TABLE {_q('user_permissions')} DROP COLUMN {_q(field_name)}"
                )
                cur.execute(
                    "DELETE FROM permission_definitions WHERE field_name=%s",
                    (field_name,),
                )

                cur.execute("SELECT role, template_json FROM role_templates")
                for trow in cur.fetchall():
                    trole = trow["role"]
                    tpl = json.loads(trow["template_json"] or "{}")
                    if field_name in tpl:
                        del tpl[field_name]
                        cur.execute(
                            "UPDATE role_templates SET template_json=%s WHERE role=%s",
                            (json.dumps(tpl), trole),
                        )
            conn.commit()
        PermissionService.refresh_cache()
        logger.info("删除权限字段: %s", field_name)
        return True
