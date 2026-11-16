import random
from datetime import datetime, timezone
from sqlalchemy import select,func
from src.config.database import Session,Base,engine
from src.models.entities import User,Batch,Inspection,Review,CalibrationSheet,CalibrationRelease
from src.utils.security import password_hash
from src.services.statistics import diagnose
from src.services import calibration

def at(day,hour=0):
    return datetime(2026,11,day,hour,tzinfo=timezone.utc)

# 一次校准换标：旧表 2026-11-01 至 2026-11-13，新表 2026-11-13 起生效。
CAL_SHEETS=[
    dict(code='CAL-1115-V1',effective_from=at(1),effective_to=at(13),
         points=[{'reading':60.0,'standard':60.4},{'reading':70.0,'standard':70.4},{'reading':75.0,'standard':75.2},{'reading':80.0,'standard':80.6},{'reading':85.0,'standard':85.7}],
         note='换标前仪器校准单，按旧读数建立对照'),
    dict(code='CAL-1115-V2',effective_from=at(13),effective_to=at(20),
         points=[{'reading':60.0,'standard':60.8},{'reading':70.0,'standard':71.0},{'reading':75.0,'standard':76.0},{'reading':80.0,'standard':81.2},{'reading':85.0,'standard':86.0}],
         note='仪器换标后校准单，读数整体上移约 1 个百分点'),
]

def seed():
    Base.metadata.create_all(engine);rng=random.Random(3101)
    with Session() as db:
        for role in ['admin','analyst','viewer']:
            email=f'{role}@demo.local'
            if not db.scalar(select(User).where(User.email==email)):db.add(User(email=email,password_hash=password_hash('Demo123!'),role=role))
        db.flush()
        for item in CAL_SHEETS:
            if not db.scalar(select(CalibrationSheet).where(CalibrationSheet.code==item['code'])):
                db.add(CalibrationSheet(**item,status='draft',created_by='admin@demo.local'))
        db.flush()
        # 发布是幂等的：已有 release 时同号重试直接返回同一版本。
        for item in CAL_SHEETS:
            sheet=db.scalar(select(CalibrationSheet).where(CalibrationSheet.code==item['code']))
            calibration.publish(db,sheet.id,db.scalar(select(User).where(User.email=='admin@demo.local')))
        db.flush()
        for i in range(40):
            code='QH-1115-A' if i==0 else f'QH-{1101+i:04}-B'
            batch=db.scalar(select(Batch).where(Batch.code==code))
            if not batch:
                batch=Batch(code=code,line=['一线','二线','三线'][i%3],supplier=['丰垦粮业','北原合作社','河谷粮仓'][i%3],tonnes=round(25+i*.7,1),received_date=f'2026-11-{1+i%15:02}')
                db.add(batch);db.flush()
            for j in range(15):
                sc=f'{code}-S{j+1:02}';val=round(max(65,min(82,rng.gauss(73+i%3*1.4,1.6))),2)
                if i in (0,9,25) and j==14:val=65.0 if i==0 else 82.0
                moisture=round(rng.uniform(11.5,14.2),2)
                if not db.scalar(select(Inspection).where(Inspection.sample_code==sc)):
                    # 前 20 批是换标前的手录旧样本，沿用原值；后 20 批是仪器直读，
                    # 按采样时刻选校准单换算。
                    instrument=i>=20
                    db.add(Inspection(sample_code=sc,batch_id=batch.id,flour_yield=val,moisture=moisture,inspector=['林洁','周麦','陈禾'][i%3],
                        source='instrument' if instrument else 'manual',
                        sampled_at=at(3+i%15,7+j%5) if instrument else None))
        db.flush()
        if not db.scalar(select(Review).where(Review.title=='11月15日全线出粉率初审')):
            from src.services.business import inspections
            rows=inspections(db)
            release_view=calibration.release_snapshot(calibration.current_release(db))
            converted,blocked=calibration.convert_rows(rows,release_view)
            if blocked:raise RuntimeError(calibration.blocked_message(blocked))
            release_view={**release_view,
                'applied_count':sum(1 for x in converted if x['calibration']['applied']),
                'manual_count':sum(1 for x in converted if not x['calibration']['applied'])}
            db.add(Review(title='11月15日全线出粉率初审',line='全部',status='completed',snapshot=converted,calibration=release_view,result=diagnose(converted),created_by='analyst@demo.local',note='待质量负责人核对异常点及签核'))
        db.commit()
        print({m.__tablename__:db.scalar(select(func.count()).select_from(m)) for m in [Batch,Inspection,Review,CalibrationSheet,CalibrationRelease]})
if __name__=='__main__':seed()
