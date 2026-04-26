"""
用户认证模块路由
接口前缀：/auth
包含接口：
  A0. POST /auth/register        - 用户注册（默认 user 角色）
  A1. POST /auth/login           - 登录，返回 JWT token
  A2. GET  /auth/users           - 获取用户列表（仅 admin）
  A3. POST /auth/users           - 新增用户（仅 admin）
  A4. POST /auth/update_role     - 修改用户角色（仅 admin）
  A5. POST /auth/change_password - 修改用户密码
  A6. POST /auth/delete_user     - 删除用户（仅 admin，软删除）
  权限与角色模板：/auth/permissions/*、/auth/permission/definitions/*
  角色配置：/auth/roles/*（增删改查 role_definitions）
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from app.services.permission_service import PermissionService
from app.services.role_definition_service import RoleDefinitionService
from app.services.user_service import UserService, get_user_service, decode_access_token

router = APIRouter(prefix="/auth", tags=["用户认证"])

_bearer = HTTPBearer()


def _current_user(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="未登录或token已过期")
    return payload


def _require_admin(user: dict = Depends(_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="权限不足")
    return user


def _jwt_user_id(user: dict) -> int:
    try:
        return int(user["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="无效的登录状态") from exc


def _can_manage_permissions(user: dict) -> bool:
    if user.get("role") == "admin":
        return True
    return PermissionService.check_permission(_jwt_user_id(user), "perm_permission_manage")


def _require_permission_manager(user: dict = Depends(_current_user)) -> dict:
    if not _can_manage_permissions(user):
        raise HTTPException(status_code=403, detail="无权限管理用户权限")
    return user


# ==================== 请求体 ====================

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    real_name: Optional[str] = None
    password: str = Field(..., min_length=6)
    phone: Optional[str] = None


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    real_name: Optional[str] = None
    password: str = Field(..., min_length=6)
    role: str = "user"
    phone: Optional[str] = None
    email: Optional[str] = None


class UpdateRoleRequest(BaseModel):
    id: int
    role: str


class ChangePasswordRequest(BaseModel):
    id: int
    admin_key: str
    new_password: str = Field(..., min_length=6)


class DeleteUserRequest(BaseModel):
    id: int


class PermissionUpdateReq(BaseModel):
    role: Optional[str] = Field(None, description="users.role，与 GET /auth/roles 中 code 一致")
    permissions: Optional[Dict[str, bool]] = Field(
        None, description="权限键值，如 {\"perm_schedule\": true}"
    )


class UpdateRoleTemplateReq(BaseModel):
    permissions: Dict[str, bool]
    apply_to_existing: bool = False


class AddPermissionDefReq(BaseModel):
    field_name: str = Field(
        ...,
        description="权限字段名，如 perm_feature_x",
        pattern=r"^perm_[a-z][a-z0-9_]*$",
    )
    label: str = Field(..., min_length=1, max_length=64, description="显示名称")


class CreateRoleDefinitionReq(BaseModel):
    code: str = Field(..., min_length=2, max_length=30, description="角色代码，小写+下划线")
    name: str = Field(..., min_length=1, max_length=64, description="显示名称")
    description: Optional[str] = Field(None, max_length=255)
    sort_order: int = Field(100, description="排序，越小越靠前")


class UpdateRoleDefinitionReq(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    description: Optional[str] = Field(None, max_length=255)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = Field(None, description="停用后不可分配给新用户")


# ==================== 路由 ====================

# A0 注册
@router.post("/register", summary="用户注册")
def register(body: RegisterRequest, service: UserService = Depends(get_user_service)):
    try:
        result = service.create_user(
            username=body.username,
            password=body.password,
            real_name=body.real_name,
            role="user",
            phone=body.phone,
        )
        return {"code": 200, "msg": "注册成功", "id": result["id"]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# A1 登录
@router.post("/login", summary="用户登录")
def login(body: LoginRequest, service: UserService = Depends(get_user_service)):
    try:
        return service.login(body.username, body.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# A2 获取用户列表
@router.get("/users", summary="获取用户列表（仅admin）")
def list_users(
    keyword: Optional[str] = None,
    role: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    _: dict = Depends(_require_admin),
    service: UserService = Depends(get_user_service),
):
    try:
        return service.list_users(keyword=keyword, role=role, page=page, page_size=page_size)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# A3 新增用户
@router.post("/users", summary="新增用户（仅admin）")
def create_user(
    body: CreateUserRequest,
    _: dict = Depends(_require_admin),
    service: UserService = Depends(get_user_service),
):
    try:
        return service.create_user(
            username=body.username,
            password=body.password,
            real_name=body.real_name,
            role=body.role,
            phone=body.phone,
            email=body.email,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# A4 修改用户角色
@router.post("/update_role", summary="修改用户角色（仅admin）")
def update_role(
    body: UpdateRoleRequest,
    _: dict = Depends(_require_admin),
    service: UserService = Depends(get_user_service),
):
    try:
        return service.update_role(body.id, body.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# A5 修改密码
@router.post("/change_password", summary="修改用户密码")
def change_password(
    body: ChangePasswordRequest,
    service: UserService = Depends(get_user_service),
):
    try:
        return service.change_password(body.id, body.admin_key, body.new_password)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# A6 删除用户
@router.post("/delete_user", summary="删除用户（仅admin，软删除）")
def delete_user(
    body: DeleteUserRequest,
    current: dict = Depends(_require_admin),
    service: UserService = Depends(get_user_service),
):
    try:
        return service.delete_user(body.id, current_user_id=int(current["sub"]))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------- 角色配置（role_definitions）----------

@router.get("/roles/manage", summary="角色定义全量列表（含停用，仅 admin）")
def list_roles_manage(_: dict = Depends(_require_admin)):
    return {
        "code": 200,
        "data": RoleDefinitionService.list_roles(include_inactive=True),
    }


@router.get("/roles", summary="启用中的角色列表（登录即可，用于下拉）")
def list_roles_active(_: dict = Depends(_current_user)):
    return {
        "code": 200,
        "data": RoleDefinitionService.list_roles(include_inactive=False),
    }


@router.get("/roles/{code}", summary="角色定义详情（仅 admin）")
def get_role_definition(code: str, _: dict = Depends(_require_admin)):
    row = RoleDefinitionService.get_by_code(code)
    if not row:
        raise HTTPException(status_code=404, detail="角色不存在")
    return {"code": 200, "data": row}


@router.post("/roles", summary="新增角色（仅 admin）")
def create_role_definition(body: CreateRoleDefinitionReq, _: dict = Depends(_require_admin)):
    try:
        new_id = RoleDefinitionService.create_role(
            code=body.code,
            name=body.name,
            description=body.description,
            sort_order=body.sort_order,
        )
        return {"code": 200, "msg": "角色已创建", "id": new_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.put("/roles/{code}", summary="更新角色定义（仅 admin）")
def update_role_definition(
    code: str,
    body: UpdateRoleDefinitionReq,
    _: dict = Depends(_require_admin),
):
    try:
        RoleDefinitionService.update_role(
            code,
            name=body.name,
            description=body.description,
            sort_order=body.sort_order,
            is_active=body.is_active,
        )
        return {"code": 200, "msg": "角色已更新"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/roles/{code}", summary="删除角色（仅 admin；非内置且无用户使用）")
def delete_role_definition(code: str, _: dict = Depends(_require_admin)):
    try:
        RoleDefinitionService.delete_role(code)
        return {"code": 200, "msg": "角色已删除"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ---------- 权限与角色模板（动态权限列；管理员模板初始全 0，由接口配置）----------

@router.get("/permissions/me", summary="当前用户权限详情")
def get_my_permissions(user: dict = Depends(_current_user)):
    uid = _jwt_user_id(user)
    data = PermissionService.get_user_permissions(uid)
    if not data:
        raise HTTPException(status_code=404, detail="用户不存在或已禁用")
    return {"code": 200, "data": data}


@router.get("/permissions/roles/templates", summary="所有角色权限模板")
def get_role_templates(_: dict = Depends(_require_permission_manager)):
    templates_raw = PermissionService.get_all_role_templates()
    all_fields = PermissionService.get_all_fields()
    templates: Dict[str, Any] = {}
    for role, perms in templates_raw.items():
        templates[role] = {
            "role": role,
            "permissions": [
                {
                    "field": field,
                    "label": PermissionService.get_label(field),
                    "value": bool(perms.get(field, 0)),
                }
                for field in all_fields
            ],
        }
    return {
        "code": 200,
        "data": templates,
        "valid_roles": PermissionService.get_valid_role_codes(active_only=False),
        "permission_fields": [
            {"field": f, "label": PermissionService.get_label(f)} for f in all_fields
        ],
    }


@router.put("/permissions/roles/{role}/template", summary="更新某角色的权限模板")
def update_role_template_route(
    role: str,
    body: UpdateRoleTemplateReq,
    _: dict = Depends(_require_admin),
):
    allowed_tpl = PermissionService.get_valid_role_codes(active_only=False)
    if role not in allowed_tpl:
        raise HTTPException(status_code=400, detail=f"无效角色，可选: {allowed_tpl}")
    invalid = [k for k in body.permissions if k not in PermissionService.get_all_fields()]
    if invalid:
        raise HTTPException(status_code=400, detail=f"无效的权限字段: {invalid}")
    try:
        PermissionService.update_role_template(
            role, body.permissions, apply_to_existing=body.apply_to_existing
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    msg = f"角色 [{role}] 模板已更新"
    if body.apply_to_existing:
        msg += "，并已同步到已有权限行"
    return {"code": 200, "msg": msg}


@router.get("/permissions", summary="用户权限分页列表")
def list_permissions(
    page: int = 1,
    size: int = 20,
    role: Optional[str] = None,
    keyword: Optional[str] = None,
    _: dict = Depends(_require_permission_manager),
):
    return {
        "code": 200,
        "data": PermissionService.list_all_permissions(
            page=page, size=size, role=role, keyword=keyword
        ),
    }


@router.get("/permissions/{user_id}", summary="指定用户权限详情")
def get_user_permissions_detail(user_id: int, user: dict = Depends(_current_user)):
    uid = _jwt_user_id(user)
    if user.get("role") != "admin" and not _can_manage_permissions(user) and uid != user_id:
        raise HTTPException(status_code=403, detail="仅可查看本人权限")
    data = PermissionService.get_user_permissions(user_id)
    if not data:
        raise HTTPException(status_code=404, detail="用户不存在或已禁用")
    return {"code": 200, "data": data}


@router.put("/permissions/{user_id}", summary="更新用户权限或权限行角色")
def update_user_permissions(
    user_id: int,
    body: PermissionUpdateReq,
    actor: dict = Depends(_current_user),
):
    if not _can_manage_permissions(actor):
        raise HTTPException(status_code=403, detail="无权限修改用户权限")
    aid = _jwt_user_id(actor)
    if user_id == aid and body.role:
        raise HTTPException(status_code=400, detail="不能修改自己的角色")
    try:
        PermissionService.update_permissions(
            user_id=user_id, role=body.role, permissions=body.permissions
        )
        if body.role:
            from app.database import get_conn

            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE users SET role = %s WHERE id = %s", (body.role, user_id)
                    )
                conn.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"code": 200, "msg": "权限已更新"}


@router.post("/permissions/{user_id}/reset", summary="按角色模板重置用户权限")
def reset_user_permissions(user_id: int, actor: dict = Depends(_current_user)):
    if not _can_manage_permissions(actor):
        raise HTTPException(status_code=403, detail="无权重置权限")
    if user_id == _jwt_user_id(actor):
        raise HTTPException(status_code=400, detail="不能重置自己的权限")

    import pymysql.cursors

    from app.database import get_conn

    with get_conn() as conn:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(
                "SELECT role FROM user_permissions WHERE user_id=%s", (user_id,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="用户权限记录不存在")
            rrole = row["role"]
            cur.execute("DELETE FROM user_permissions WHERE user_id=%s", (user_id,))
        conn.commit()
    PermissionService.create_default_permissions(user_id, str(rrole))
    return {"code": 200, "msg": f"已按角色 [{rrole}] 模板重置权限"}


@router.get("/permission/definitions", summary="权限字段定义列表")
def list_permission_definitions(_: dict = Depends(_require_permission_manager)):
    import pymysql.cursors

    from app.database import get_conn

    with get_conn() as conn:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(
                "SELECT field_name, label, created_at FROM permission_definitions "
                "ORDER BY field_name"
            )
            rows = cur.fetchall()
    return {"code": 200, "data": rows, "total": len(rows)}


@router.post("/permission/definitions", summary="新增权限字段（会 ALTER 表）")
def add_permission_definition_route(
    body: AddPermissionDefReq,
    _: dict = Depends(_require_permission_manager),
):
    try:
        PermissionService.add_permission_definition(body.field_name, body.label)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"code": 200, "msg": f"已添加权限字段 {body.field_name}"}


@router.delete("/permission/definitions/{field_name}", summary="删除权限字段（会 ALTER 表）")
def delete_permission_definition_route(
    field_name: str,
    _: dict = Depends(_require_permission_manager),
):
    try:
        PermissionService.remove_permission_definition(field_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"code": 200, "msg": f"已删除权限字段 {field_name}"}
