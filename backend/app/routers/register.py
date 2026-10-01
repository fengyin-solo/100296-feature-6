"""使用登记接口：维护设备登记，覆盖办理登记、申请停用、解停恢复、申请注销等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.register import DEFAULT_OPERATOR, TRANSITIONS, RegisterService

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
def stats() -> dict[str, int]:
    """状态统计：在用台数跟随登记明细实时重算，供概览卡片直接取用。"""
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
    """登记一台设备：缺字段当场点名叫退；重复设备编号只留最早一条并把内容另存备注。"""
    operator = str(payload.values.get("operator") or DEFAULT_OPERATOR).strip() or DEFAULT_OPERATOR
    entry, message = service.create_entry(payload.values, operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    # 重复登记不覆盖原记录，按"已退回但已留痕"提示，不算一次新的成功登记。
    if message:
        return ActionResult(ok=False, message=message, entry=entry)
    return ActionResult(ok=True, message="设备登记已提交，当前为「待登记」，请继续办理登记。", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条设备执行状态流转动作；跳步、终态改动等不允许的动作当场退回并说明卡点。"""
    action = str(payload.values.get("action") or "").strip()
    operator = str(payload.values.get("operator") or DEFAULT_OPERATOR).strip() or DEFAULT_OPERATOR
    entry, message = service.run_action(entry_id, action, operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/{entry_id}/actions")
def available_actions(entry_id: int) -> dict[str, Any]:
    """返回该设备当前状态下允许办理的动作，前端据此收敛按钮；服务端仍会再次把关。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"设备登记 {entry_id} 不存在或已归档")
    status = str(entry.get("status") or "待登记")
    return {"status": status, "actions": list(TRANSITIONS.get(status, {}).keys())}
