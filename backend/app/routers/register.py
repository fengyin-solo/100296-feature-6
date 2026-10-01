"""使用登记接口：维护设备登记，覆盖办理登记、申请停用、解停恢复、申请注销等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.register import RegisterService

router = APIRouter(prefix="/api/register", tags=["使用登记"])

service = RegisterService()

LIST_FIELDS = ["设备编号", "设备名称", "设备种类", "使用单位", "安装地点", "投用日期", "登记证号", "登记状态"]
STATUSES = ["待登记", "已登记", "停用中", "已注销"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按设备编号检索"),
    status: str | None = Query(default=None, description="待登记、已登记、停用中、已注销"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按设备编号与状态过滤使用登记列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def register_stats() -> dict[str, int]:
    """在用/停用等台数按登记明细实时重算，供列表页与概览共用同一口径。"""
    return service.stats()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出使用登记清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "register", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条设备登记明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"设备登记 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """提交设备登记：缺登记证号/使用单位等必填项时点名退回；同一设备重复提交只另存备注。"""
    operator = str(payload.values.pop("operator", "") or "").strip() or None
    entry, message = service.create_entry(payload.values, operator=operator, remark=payload.remark)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条设备登记执行动作；跳步申请会被当场退回，并说明卡在哪一步。"""
    action = str(payload.values.get("action") or "").strip()
    operator = str(payload.values.get("operator") or "").strip() or None
    entry, message = service.run_action(entry_id, action, operator=operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
