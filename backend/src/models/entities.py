from sqlalchemy import String, Float, Integer, ForeignKey, JSON, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from src.config.database import Base
class User(Base):
    __tablename__="users"
    id:Mapped[int]=mapped_column(primary_key=True)
    email:Mapped[str]=mapped_column(String(100),unique=True)
    password_hash:Mapped[str]=mapped_column(String(300))
    role:Mapped[str]=mapped_column(String(20))
class Batch(Base):
    __tablename__="batches"
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(50),unique=True)
    line:Mapped[str]=mapped_column(String(20))
    supplier:Mapped[str]=mapped_column(String(80))
    tonnes:Mapped[float]=mapped_column(Float)
    received_date:Mapped[str]=mapped_column(String(10))
class Inspection(Base):
    __tablename__="inspections"
    id:Mapped[int]=mapped_column(primary_key=True)
    sample_code:Mapped[str]=mapped_column(String(70),unique=True)
    batch_id:Mapped[int]=mapped_column(ForeignKey("batches.id"))
    flour_yield:Mapped[float]=mapped_column(Float)
    moisture:Mapped[float]=mapped_column(Float)
    inspector:Mapped[str]=mapped_column(String(50))
    # 仪器原始读数始终保留；采样时刻决定受理诊断时套用哪一版校准单。
    sampled_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True,default=lambda:datetime.now(timezone.utc))
    source:Mapped[str]=mapped_column(String(20),default="manual")
class CalibrationSheet(Base):
    __tablename__="calibration_sheets"
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(60),unique=True)
    status:Mapped[str]=mapped_column(String(20),default="draft")
    effective_from:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    effective_to:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    points:Mapped[list]=mapped_column(JSON,default=list)
    note:Mapped[str]=mapped_column(Text,default="")
    version:Mapped[int]=mapped_column(Integer,default=0)
    created_by:Mapped[str]=mapped_column(String(100))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    published_by:Mapped[str]=mapped_column(String(100),default="")
    published_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
class CalibrationRelease(Base):
    """每次成功发布生成一份不可变的完整校准版本快照。"""
    __tablename__="calibration_releases"
    id:Mapped[int]=mapped_column(primary_key=True)
    version:Mapped[int]=mapped_column(Integer,unique=True)
    sheets:Mapped[list]=mapped_column(JSON,default=list)
    created_by:Mapped[str]=mapped_column(String(100))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class CalibrationState(Base):
    __tablename__="calibration_state"
    id:Mapped[int]=mapped_column(primary_key=True)
    version:Mapped[int]=mapped_column(Integer,default=0)
class Review(Base):
    __tablename__="reviews"
    id:Mapped[int]=mapped_column(primary_key=True)
    title:Mapped[str]=mapped_column(String(120))
    line:Mapped[str]=mapped_column(String(20))
    status:Mapped[str]=mapped_column(String(20),default="queued")
    result:Mapped[dict]=mapped_column(JSON,default=dict)
    snapshot:Mapped[list]=mapped_column(JSON,default=list)
    calibration:Mapped[dict]=mapped_column(JSON,default=dict)
    note:Mapped[str]=mapped_column(Text,default="")
    created_by:Mapped[str]=mapped_column(String(100))
    approved_by:Mapped[str]=mapped_column(String(100),default="")
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class Audit(Base):
    __tablename__="audits"
    id:Mapped[int]=mapped_column(primary_key=True)
    actor:Mapped[str]=mapped_column(String(100))
    action:Mapped[str]=mapped_column(String(200))
    status:Mapped[int]=mapped_column(Integer)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
