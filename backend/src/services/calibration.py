"""仪器校准单：发布、按采样时刻选单与分段线性换算。

设计要点：
- 校准单草稿可反复修改，只有发布后才会生成一个完整、不可变的校准版本。
- 每次发布递增全局版本号并写入 CalibrationRelease 快照；诊断受理只读取最新
  的单个 release，从而拿到同一时刻完整的一组校准单。
- 校准时段采用左闭右开 [effective_from, effective_to)，相邻时段可以首尾相接。
- 仪器读数只在对照点覆盖范围内做分段线性插值；手录样本永远沿用原值。
"""
from __future__ import annotations

import bisect
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.models.entities import CalibrationRelease, CalibrationSheet, CalibrationState


class CalibrationError(ValueError):
    pass


def to_utc(value: datetime | str | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso(value: datetime | str | None) -> str | None:
    dt = to_utc(value)
    return dt.isoformat() if dt else None


def normalize_points(points) -> list[dict]:
    cleaned = []
    for point in points or []:
        if hasattr(point, "model_dump"):
            point = point.model_dump()
        reading = float(point["reading"])
        standard = float(point["standard"])
        cleaned.append({"reading": reading, "standard": standard})
    if len(cleaned) < 2:
        raise CalibrationError("校准单至少需要 2 个读数与标准值对照点")
    readings = [p["reading"] for p in cleaned]
    if len(set(readings)) != len(readings):
        raise CalibrationError("校准单的仪器读数不能重复")
    return sorted(cleaned, key=lambda p: p["reading"])


def sheet_snapshot(sheet: CalibrationSheet) -> dict:
    return {
        "id": sheet.id,
        "code": sheet.code,
        "version": sheet.version,
        "effective_from": iso(sheet.effective_from),
        "effective_to": iso(sheet.effective_to),
        "points": normalize_points(sheet.points or []),
        "note": sheet.note or "",
    }


def state_version(db) -> int:
    state = db.get(CalibrationState, 1)
    return state.version if state else 0


def ensure_state(db) -> CalibrationState:
    state = db.get(CalibrationState, 1)
    if not state:
        state = CalibrationState(id=1, version=0)
        db.add(state)
        db.flush()
    return state


def current_release(db) -> CalibrationRelease | None:
    return db.scalar(select(CalibrationRelease).order_by(CalibrationRelease.version.desc()).limit(1))


def release_snapshot(release: CalibrationRelease | None) -> dict:
    if not release:
        return {"version": 0, "release_id": None, "sheets": []}
    return {"version": release.version, "release_id": release.id, "sheets": release.sheets or []}


def _periods_overlap(a_from, a_to, b_from, b_to) -> bool:
    return to_utc(a_from) < to_utc(b_to) and to_utc(b_from) < to_utc(a_to)


def _overlaps_with_published(db, sheet: CalibrationSheet) -> list[str]:
    rows = db.scalars(select(CalibrationSheet).where(CalibrationSheet.status == "published", CalibrationSheet.id != sheet.id))
    return [other.code for other in rows if _periods_overlap(sheet.effective_from, sheet.effective_to, other.effective_from, other.effective_to)]


def validate_sheet_dates(sheet: CalibrationSheet) -> None:
    start, end = to_utc(sheet.effective_from), to_utc(sheet.effective_to)
    if not start or not end or start >= end:
        raise CalibrationError("生效时段无效：开始时间必须早于结束时间")
    normalize_points(sheet.points)


def _publish_once(db, sheet_id: int, user) -> dict:
    # 先锁草稿行：同一张校准单的并发/重试发布会串行化，后到者看到 published 后
    # 直接返回同一版本，不会再生成 release。
    sheet = db.scalar(select(CalibrationSheet).where(CalibrationSheet.id == sheet_id).with_for_update())
    if not sheet:
        raise HTTPException(404, "校准单不存在")
    if sheet.status == "published":
        result = {"sheet": _sheet_record(sheet), "version": sheet.version, "already_published": True}
        db.rollback()  # 释放行锁；重试同一张已发布校准单是只读操作。
        return result

    state = db.scalar(select(CalibrationState).where(CalibrationState.id == 1).with_for_update())
    if not state:
        state = CalibrationState(id=1, version=0)
        db.add(state)
        db.flush()

    validate_sheet_dates(sheet)
    conflicts = _overlaps_with_published(db, sheet)
    # 与已发布时段重叠的校准单仍可发布（成为新的当前版本），但受理诊断时会因
    # 样本命中多张校准单而整次受阻；发布响应同时返回冲突编号供页面提示。
    state.version += 1
    sheet.status = "published"
    sheet.version = state.version
    sheet.published_by = user.email
    sheet.published_at = datetime.now(timezone.utc)
    db.flush()

    published = list(db.scalars(select(CalibrationSheet).where(CalibrationSheet.status == "published").order_by(CalibrationSheet.effective_from)))
    release = CalibrationRelease(version=state.version, sheets=[sheet_snapshot(item) for item in published], created_by=user.email)
    db.add(release)
    db.flush()
    db.commit()
    return {"sheet": _sheet_record(sheet), "version": state.version, "release_id": release.id, "already_published": False, "conflicts": conflicts}


def publish(db, sheet_id: int, user) -> dict:
    """发布草稿。失败回滚保留旧版本；同号重试幂等。"""
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return _publish_once(db, sheet_id, user)
        except HTTPException:
            db.rollback()
            raise
        except CalibrationError as exc:
            db.rollback()
            raise HTTPException(422, f"校准单校验失败，仍沿用原校准版本 v{state_version(db)}：{exc}")
        except IntegrityError as exc:
            # 并发发布同一张草稿：唯一约束让其中一个事务失败并整体回滚，
            # 重试时读到 published 状态即返回同一版本，不会重复生效。
            db.rollback()
            last_error = exc
            continue
        except Exception as exc:
            db.rollback()
            last_error = exc
            break
    version = state_version(db)
    raise HTTPException(503, f"校准单发布失败，仍沿用原校准版本 v{version}；请稍后重试" + (f"（{type(last_error).__name__}）" if last_error else ""))


def _sheet_record(sheet: CalibrationSheet) -> dict:
    return {
        "id": sheet.id,
        "code": sheet.code,
        "status": sheet.status,
        "version": sheet.version,
        "effective_from": iso(sheet.effective_from),
        "effective_to": iso(sheet.effective_to),
        "points": normalize_points(sheet.points or []),
        "note": sheet.note or "",
        "created_by": sheet.created_by,
        "created_at": iso(sheet.created_at),
        "published_by": sheet.published_by,
        "published_at": iso(sheet.published_at),
    }


def list_sheets(db) -> dict:
    sheets = list(db.scalars(select(CalibrationSheet).order_by(CalibrationSheet.id.desc())))
    release = current_release(db)
    return {
        "version": release.version if release else 0,
        "release_id": release.id if release else None,
        "sheets": [_sheet_record(sheet) for sheet in sheets],
        "published": release.sheets if release else [],
    }


def _matching_sheets(sampled_at, sheets: list[dict]) -> list[dict]:
    moment = to_utc(sampled_at)
    if not moment:
        return []
    return [sheet for sheet in sheets if to_utc(sheet["effective_from"]) <= moment < to_utc(sheet["effective_to"])]


def interpolate(reading: float, points: list[dict]) -> tuple[float, dict]:
    points = normalize_points(points)
    readings = [point["reading"] for point in points]
    lower_bound, upper_bound = readings[0], readings[-1]
    if reading < lower_bound or reading > upper_bound:
        raise CalibrationError(f"读数 {reading:g} 超出校准对照范围 [{lower_bound:g}, {upper_bound:g}]")
    index = bisect.bisect_right(readings, reading) - 1
    if index >= len(points) - 1:
        lower = upper = points[-1]
        weight = 0.0
        value = lower["standard"]
    else:
        lower, upper = points[index], points[index + 1]
        weight = (reading - lower["reading"]) / (upper["reading"] - lower["reading"])
        value = lower["standard"] + weight * (upper["standard"] - lower["standard"])
    basis = {
        "method": "分段线性插值",
        "lower": dict(lower),
        "upper": dict(upper),
        "weight": round(weight, 6),
        "reading": reading,
        "converted": round(value, 6),
    }
    return round(value, 6), basis


def _convert_one(row: dict, sheets: list[dict]) -> tuple[dict | None, dict | None]:
    raw = float(row["flour_yield"])
    sample = (row.get("source") or "manual").lower()
    if sample != "instrument":
        return {
            "original_yield": raw,
            "converted_yield": raw,
            "flour_yield": raw,
            "calibration": {"applied": False, "basis": "手录样本沿用原值", "sheet_code": None, "version": None},
        }, None
    sampled_at = row.get("sampled_at")
    if not sampled_at:
        return None, {"sample_code": row.get("sample_code"), "reason": "仪器样本缺少采样时刻，无法选校准单"}
    matches = _matching_sheets(sampled_at, sheets)
    if not matches:
        return None, {"sample_code": row.get("sample_code"), "reason": f"采样时刻 {iso(sampled_at)} 不在任何已发布校准单生效时段内"}
    if len(matches) > 1:
        codes = "、".join(sheet["code"] for sheet in matches)
        return None, {"sample_code": row.get("sample_code"), "reason": f"采样时刻 {iso(sampled_at)} 命中重叠校准单 {codes}"}
    sheet = matches[0]
    try:
        value, basis = interpolate(raw, sheet["points"])
    except CalibrationError as exc:
        return None, {"sample_code": row.get("sample_code"), "reason": f"校准单 {sheet['code']} {exc}"}
    if not 0 < value <= 100:
        return None, {"sample_code": row.get("sample_code"), "reason": f"校准单 {sheet['code']} 换算结果 {value:g}% 超出出粉率有效范围 (0,100]"}
    return {
        "original_yield": raw,
        "converted_yield": value,
        "flour_yield": value,
        "calibration": {
            "applied": True,
            "sheet_code": sheet["code"],
            "version": sheet["version"],
            "basis": basis,
        },
    }, None


def convert_rows(rows: list[dict], release: dict | None) -> tuple[list[dict], list[dict]]:
    """把检验快照换算为诊断口径值；返回 (换算后的行, 受阻样本列表)。"""
    sheets = (release or {}).get("sheets", [])
    converted, blocked = [], []
    for row in rows:
        result, problem = _convert_one(row, sheets)
        if problem:
            blocked.append(problem)
            continue
        converted.append({**row, **result})
    return converted, blocked


def blocked_message(blocked: list[dict]) -> str:
    detail = "；".join(f"{item['sample_code']}（{item['reason']}）" for item in blocked)
    return f"整次诊断受阻：{len(blocked)} 个样本无法按采样时刻完成校准换算。{detail}"


def preview(db, sheet_id: int) -> dict:
    sheet = db.get(CalibrationSheet, sheet_id)
    if not sheet:
        raise HTTPException(404, "校准单不存在")
    try:
        validate_sheet_dates(sheet)
    except CalibrationError as exc:
        raise HTTPException(422, f"校准单尚不可用：{exc}")
    from src.services.business import inspections

    sheet_view = _sheet_record(sheet)
    sheet_view["points"] = normalize_points(sheet.points or [])
    # 模拟发布后的完整版本：当前已发布集合 + 本校准单（已发布单用当前定义替换）。
    release = current_release(db)
    siblings = [item for item in (release.sheets if release else []) if item["code"] != sheet.code]
    combined = siblings + [sheet_view]
    start, end = to_utc(sheet.effective_from), to_utc(sheet.effective_to)
    samples, manual_ignored = [], 0
    for row in inspections(db):
        if (row.get("source") or "manual") != "instrument":
            manual_ignored += 1
            continue
        sampled = to_utc(row.get("sampled_at"))
        if not sampled or not (start <= sampled < end):
            continue
        result, problem = _convert_one(row, combined)
        samples.append({
            "sample_code": row["sample_code"],
            "batch_code": row.get("batch_code"),
            "line": row.get("line"),
            "sampled_at": row.get("sampled_at"),
            "original_yield": row["flour_yield"],
            "converted_yield": result["converted_yield"] if result else None,
            "calibration": result["calibration"] if result else None,
            "blocked": bool(problem),
            "reason": problem["reason"] if problem else None,
        })
    published = list(db.scalars(select(CalibrationSheet).where(CalibrationSheet.status == "published", CalibrationSheet.id != sheet.id)))
    conflicts = [other.code for other in published if _periods_overlap(sheet.effective_from, sheet.effective_to, other.effective_from, other.effective_to)]
    blocked_count = sum(1 for sample in samples if sample["blocked"])
    return {
        "sheet": sheet_view,
        "current_version": state_version(db),
        "conflicts": conflicts,
        "samples": samples,
        "affected_count": len(samples),
        "blocked_count": blocked_count,
        "manual_ignored": manual_ignored,
    }
