from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from datetime import datetime,timezone
from redis import Redis
from src.config.settings import REDIS_URL
from src.models.entities import Batch,Inspection,Review
from src.utils.serialize import record
from src.services import calibration
queue=Redis.from_url(REDIS_URL,decode_responses=True)
def batches(db):
    rows=db.execute(select(Batch,func.count(Inspection.id)).outerjoin(Inspection,Inspection.batch_id==Batch.id).group_by(Batch.id).order_by(Batch.id.desc())).all()
    return [{**record(b),'samples':n} for b,n in rows]
def create(db,model,data):
    obj=model(**data);db.add(obj)
    try:db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'编号已存在，请使用独立编号')
    return record(obj)
def inspections(db,batch_id=None):
    q=select(Inspection,Batch.code,Batch.line).join(Batch,Batch.id==Inspection.batch_id).order_by(Inspection.id.desc())
    if batch_id:q=q.where(Inspection.batch_id==batch_id)
    return [{**record(i),'batch_code':code,'line':line} for i,code,line in db.execute(q)]
def add_inspection(db,data):
    if not db.get(Batch,data['batch_id']):raise HTTPException(404,'原粮批次不存在')
    if data.get('source','manual')=='instrument':
        # 仪器读数必须给出采样时刻：补录的迟到记录也按当时采样时刻选校准单，
        # 而不是按录入时间。
        if not data.get('sampled_at'):raise HTTPException(422,'仪器读数必须提供采样时刻，迟到补录请填写原始采样时间')
        data['sampled_at']=calibration.to_utc(data['sampled_at'])
    elif not data.get('sampled_at'):
        data['sampled_at']=datetime.now(timezone.utc)
    return create(db,Inspection,data)
def submit(db,data,user):
    # 受理过程中若恰好并发发布，退出本次读取并重试，确保快照与所记录的校准
    # 版本严格同属一个完整版本，不会半新半旧。
    for _ in range(3):
        before=calibration.current_release(db)
        release_view=calibration.release_snapshot(before)
        rows=inspections(db)
        after=calibration.current_release(db)
        if (before.id if before else None)==(after.id if after else None):break
    else:raise HTTPException(409,'校准单正在发布，请稍后重新受理诊断')
    if data['line']!='全部':rows=[x for x in rows if x['line']==data['line']]
    if len(rows)<5:raise HTTPException(422,'该范围至少需要 5 条检验记录，请先录入')
    converted,blocked=calibration.convert_rows(rows,release_view)
    if blocked:raise HTTPException(422,detail={'message':calibration.blocked_message(blocked),'blocked':blocked,'calibration_version':release_view['version']})
    release_view={**release_view,
        'applied_count':sum(1 for x in converted if x['calibration']['applied']),
        'manual_count':sum(1 for x in converted if not x['calibration']['applied'])}
    obj=Review(**data,created_by=user.email,snapshot=converted,calibration=release_view);db.add(obj);db.commit()
    try:queue.rpush('mill:jobs',obj.id)
    except Exception:
        obj.status='failed';obj.note='队列不可用，请恢复后重新提交';db.commit();raise HTTPException(503,obj.note)
    return record(obj)
def review(db,id):
    obj=db.get(Review,id)
    if not obj:raise HTTPException(404,'复核单不存在')
    return obj
def approve(db,id,note,user):
    obj=review(db,id)
    if obj.status!='completed':raise HTTPException(409,'只有已计算且未签核的复核单可以签核')
    obj.status='approved';obj.note=note;obj.approved_by=user.email;db.commit()
    return record(obj)
