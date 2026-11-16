import csv,io
from fastapi import HTTPException
from fastapi.responses import Response
def export_review(obj):
    if obj.status not in ('completed','approved'):raise HTTPException(409,'计算完成后才可导出')
    output=io.StringIO();w=csv.writer(output)
    w.writerow(['复核单',obj.id,'标题',obj.title,'状态',obj.status,'范围',obj.line])
    for k in ['n','mean','std','q1','median','q3','iqr','lower','upper','checksum']:w.writerow([k,obj.result[k]])
    w.writerow(['签核人',obj.approved_by,'签核意见',obj.note])
    calibration=obj.calibration or {}
    w.writerow(['校准版本',calibration.get('version',0),'校准单数',len(calibration.get('sheets',[]))])
    for sheet in calibration.get('sheets',[]):
        w.writerow(['校准单',sheet.get('code'),'生效',sheet.get('effective_from'),sheet.get('effective_to'),'对照点',__import__('json').dumps(sheet.get('points',[]),ensure_ascii=False)])
    w.writerow(['样本编号','批次','产线','出粉率（原值）','出粉率（换算值）','校准单','采样时刻','来源','水分','异常'])
    out={r['sample_code'] for r in obj.result['outliers']}
    for row in obj.snapshot:
        cal=(row.get('calibration') or {})
        w.writerow([row['sample_code'],row['batch_code'],row['line'],row.get('original_yield',row['flour_yield']),row.get('converted_yield',row['flour_yield']),cal.get('sheet_code') or '',row.get('sampled_at') or '',row.get('source','manual'),row['moisture'],'是' if row['sample_code'] in out else '否'])
    return Response('﻿'+output.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="mill-yield-review-{obj.id}.csv"'})
