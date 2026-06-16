"""
手动初始化脚本
==============
用法：
    python -m scripts.seed          # 建表 + 写入权限/角色/超管
"""
import asyncio

from core.bootstrap import bootstrap_system
from core.database import AsyncSessionLocal, init_db


async def main() -> None:
    await init_db()
    async with AsyncSessionLocal() as db:
        await bootstrap_system(db)
    print("✓ claw-zep 初始化完成")


if __name__ == "__main__":
    asyncio.run(main())
