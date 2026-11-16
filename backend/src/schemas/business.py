from pydantic import BaseModel,Field,field_validator
from typing import Literal
from datetime import datetime
class Login(BaseModel):
    email:str
    password:str
class BatchInput(BaseModel):
    code:str=Field(min_length=3,max_length=50,pattern=r"^[A-Za-z0-9_-]+$")
    line:Literal["一线","二线","三线"]
    supplier:str=Field(min_length=1,max_length=80)
    tonnes:float=Field(gt=0,le=10000,allow_inf_nan=False)
    received_date:str
    @field_validator('received_date')
    @classmethod
    def valid_date(cls,v):
        from datetime import date
        date.fromisoformat(v)
        return v
class InspectionInput(BaseModel):
    sample_code:str=Field(min_length=3,max_length=70,pattern=r"^[A-Za-z0-9_-]+$")
    batch_id:int=Field(gt=0)
    flour_yield:float=Field(gt=0,le=100,allow_inf_nan=False)
    moisture:float=Field(ge=0,le=30,allow_inf_nan=False)
    inspector:str=Field(min_length=1,max_length=50)
    source:Literal["manual","instrument"]="manual"
    sampled_at:datetime|None=None
class ReviewInput(BaseModel):
    title:str=Field(min_length=2,max_length=120)
    line:Literal["全部","一线","二线","三线"]="全部"
class ApprovalInput(BaseModel):
    note:str=Field(min_length=5,max_length=1500)
class CalibrationPointInput(BaseModel):
    reading:float=Field(allow_inf_nan=False)
    standard:float=Field(allow_inf_nan=False)
class CalibrationSheetInput(BaseModel):
    code:str=Field(min_length=3,max_length=60,pattern=r"^[A-Za-z0-9_-]+$")
    effective_from:datetime
    effective_to:datetime
    points:list[CalibrationPointInput]=Field(min_length=2,max_length=50)
    note:str=Field(default="",max_length=1500)
    @field_validator('effective_to')
    @classmethod
    def period_valid(cls,value,info):
        start=info.data.get('effective_from')
        if start is not None and value<=start:raise ValueError('生效结束时间必须晚于开始时间')
        return value
    @field_validator('points')
    @classmethod
    def readings_unique(cls,points):
        readings=[p.reading for p in points]
        if len(set(readings))!=len(readings):raise ValueError('校准点仪器读数不能重复')
        return points
