import time,os,traceback
from pathlib import Path
from sqlalchemy import select
from src.config.database import Session,Base,engine
from src.config.schema import upgrade as schema_upgrade
from src.models.entities import Review
from src.services.business import queue
from src.services.statistics import diagnose
Base.metadata.create_all(engine)
schema_upgrade(engine)
# Recover committed jobs if a process stopped between database commit and queue push.
with Session() as db:
    for obj in db.scalars(select(Review).where(Review.status.in_(['queued','running']))):queue.rpush('mill:jobs',obj.id)
while True:
    Path('/tmp/worker-heartbeat').touch()
    item=queue.blpop('mill:jobs',timeout=2)
    if not item:continue
    with Session() as db:
        obj=db.get(Review,int(item[1]))
        if not obj or obj.status not in ('queued','running'):continue
        obj.status='running';db.commit()
        try:
            # 快照在受理时已按校准版本换算完成；worker 只消费冻结结果，不重读
            # 当前校准单，因此受理后的换标不会改变已受理诊断。
            obj.result=diagnose(obj.snapshot);obj.status='completed'
            Path('/artifacts').mkdir(exist_ok=True)
            Path(f'/artifacts/review-{obj.id}.json').write_text(__import__('json').dumps({'result':obj.result,'calibration':obj.calibration},ensure_ascii=False))
        except Exception as e:obj.status='failed';obj.note=str(e);traceback.print_exc()
        db.commit()
