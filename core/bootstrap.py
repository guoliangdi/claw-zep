"""
系统初始化（幂等）
==================
- 写入全部系统权限点
- 创建系统内置角色并绑定权限
- 创建超级管理员账号（来自 settings）

可在应用启动时调用，或通过 `python -m scripts.seed` 手动执行。
"""
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.security import hash_password
from models.rbac import Permission, Role, SYSTEM_PERMISSIONS, SYSTEM_ROLES
from models.user import SystemRole, User, UserStatus

logger = structlog.get_logger(__name__)


async def _ensure_permissions(db: AsyncSession) -> dict[str, Permission]:
    existing = {p.code: p for p in (await db.scalars(select(Permission))).all()}
    for code, name, resource, action in SYSTEM_PERMISSIONS:
        if code not in existing:
            perm = Permission(
                code=code, name=name, resource=resource, action=action,
                description=name,
            )
            db.add(perm)
            existing[code] = perm
    await db.flush()
    return existing


async def _ensure_roles(db: AsyncSession, perms: dict[str, Permission]) -> None:
    from sqlalchemy.orm import selectinload

    # 预加载 permissions 关系，避免 noload 导致重复 INSERT（幂等关键）
    existing = {
        r.name: r
        for r in (
            await db.scalars(
                select(Role)
                .where(Role.tenant_id.is_(None))
                .options(selectinload(Role.permissions))
            )
        ).all()
    }
    for role_name, perm_codes in SYSTEM_ROLES.items():
        desired = [perms[c] for c in perm_codes if c in perms]
        role = existing.get(role_name)
        if role is None:
            role = Role(
                name=role_name,
                description=f"系统内置角色 {role_name}",
                is_system=True,
                tenant_id=None,
            )
            db.add(role)
            await db.flush()
            role.permissions = desired
        else:
            # 仅当权限集合变化时才重写（关系已 selectinload，可正确 diff）
            current_codes = {p.code for p in role.permissions}
            desired_codes = {p.code for p in desired}
            if current_codes != desired_codes:
                role.permissions = desired
    await db.flush()


async def _ensure_super_admin(db: AsyncSession) -> None:
    email = settings.super_admin_email
    exists = await db.scalar(select(User).where(User.email == email))
    if exists:
        return
    admin = User(
        email=email,
        username="superadmin",
        display_name="Super Admin",
        hashed_password=hash_password(settings.super_admin_password),
        system_role=SystemRole.SUPER_ADMIN.value,
        status=UserStatus.ACTIVE.value,
        tenant_id=None,
    )
    db.add(admin)
    await db.flush()
    logger.info("super admin created", email=email)


async def bootstrap_system(db: AsyncSession) -> None:
    perms = await _ensure_permissions(db)
    await _ensure_roles(db, perms)
    await _ensure_super_admin(db)
    await db.commit()
    logger.info(
        "system bootstrap complete",
        permissions=len(perms),
        roles=len(SYSTEM_ROLES),
    )
