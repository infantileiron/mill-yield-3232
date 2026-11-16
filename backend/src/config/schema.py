"""启动时的轻量增量迁移。

项目约定表结构由 SQLAlchemy create_all 应用；create_all 不会给已存在的表补列。
校准功能给 inspections / reviews 增加了列，这里在 create_all 之后用幂等 DDL
为旧命名卷补齐，避免升级后旧库直接报缺列。
"""
from sqlalchemy import text

COLUMNS = {
    "inspections": [
        ("sampled_at", "TIMESTAMP WITH TIME ZONE"),
        ("source", "VARCHAR(20) DEFAULT 'manual'"),
    ],
    "reviews": [
        ("calibration", "JSON DEFAULT '{}'::json"),
    ],
}


def upgrade(engine) -> None:
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        for table, columns in COLUMNS.items():
            for name, ddl in columns:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {ddl}'))
