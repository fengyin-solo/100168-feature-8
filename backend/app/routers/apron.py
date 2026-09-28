"""机坪巡查接口：维护巡查单，覆盖派发巡查、提交结果、回填整改、完成整改、作废巡查等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.apron import ApronService

router = APIRouter(prefix="/api/apron", tags=["机坪巡查"])

service = ApronService()

LIST_FIELDS = ["巡查单号", "巡查区域", "巡查人员", "巡查日期", "巡查项目", "发现问题数", "巡查时长", "巡查状态"]
STATUSES = ["待派发", "巡查中", "已提交", "已整改", "已作废"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按巡查单号检索"),
    status: str | None = Query(default=None, description="待派发、巡查中、已提交、已整改、已作废"),
    area: str | None = Query(default=None, description="按巡查区域检索，汇总口径与列表一致"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按巡查单号、巡查区域与状态过滤机坪巡查列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, area=area, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/summary")
def area_summary(
    keyword: str | None = Query(default=None, description="按巡查单号检索"),
    status: str | None = Query(default=None, description="与列表一致的状态过滤"),
    area: str | None = Query(default=None, description="与列表一致的巡查区域过滤"),
) -> dict[str, Any]:
    """按巡查区域汇总发现问题数；与巡查单列表同一套筛选、同一份数据，刷新后仍成立。"""
    items = service.area_summary(keyword=keyword, status=status, area=area)
    return {
        "module": "apron",
        "group_by": "巡查区域",
        "total": len(items),
        "items": items,
    }


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出机坪巡查清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "apron", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条巡查单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"巡查单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条巡查单，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="巡查单已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条巡查单执行派发巡查、提交结果、回填整改、完成整改、作废巡查。

    提交结果需在 values 里带「问题明细」（逐项巡查项目+发现问题数）；
    回填整改需在 values 里带「整改明细」（逐项整改结论+整改人）。
    不允许的动作会被拦下并说明原因，失败尝试同样写入该巡查单的操作留痕。
    """
    action = str(payload.values.get("action") or "").strip()
    entry, message, ok = service.run_action(entry_id, action, payload.values)
    if not ok:
        return ActionResult(ok=False, message=message, entry=entry)
    return ActionResult(ok=True, message=message, entry=entry)
