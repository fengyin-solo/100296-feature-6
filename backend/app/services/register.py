"""使用登记业务规则：状态流转、字段校验、重复登记与流转留痕都收在这里。

状态链：待登记 →（办理登记）→ 已登记 →（申请停用）→ 停用中
停用中 →（解停恢复）→ 已登记；停用中 →（申请注销）→ 已注销（终态）。
任何跳步动作都会被拦下，并说明卡在哪一步。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "register"
ALL_FIELDS = ["设备编号", "设备名称", "设备种类", "使用单位", "安装地点", "投用日期", "登记证号"]
# 登记证号与使用单位是登记业务的硬门槛，设备编号用于判定“同一台设备”
REQUIRED_FIELDS = ["设备编号", "使用单位", "登记证号"]

STATUS_PENDING = "待登记"
STATUS_IN_USE = "已登记"
STATUS_SUSPENDED = "停用中"
STATUS_CANCELED = "已注销"
STATUS_ORDER = [STATUS_PENDING, STATUS_IN_USE, STATUS_SUSPENDED, STATUS_CANCELED]

# 每个状态允许执行的动作及其目标状态；不在表里的动作一律当场退回
TRANSITIONS: dict[str, dict[str, str]] = {
    STATUS_PENDING: {"办理登记": STATUS_IN_USE},
    STATUS_IN_USE: {"申请停用": STATUS_SUSPENDED},
    STATUS_SUSPENDED: {"解停恢复": STATUS_IN_USE, "申请注销": STATUS_CANCELED},
    STATUS_CANCELED: {},
}
ACTION_LABELS = {"办理登记", "申请停用", "解停恢复", "申请注销"}

# 跳步申请时，按当前状态说明“卡在哪一步、下一步该做什么”
BLOCK_HINTS = {
    STATUS_PENDING: "设备还没办完登记，须先执行「办理登记」进入已登记，之后才能申请停用或注销",
    STATUS_IN_USE: "设备登记已办完、正在使用，只能先「申请停用」；注销须在停用之后办理",
    STATUS_SUSPENDED: "设备停用中，恢复使用须先「解停恢复」，确认报废则走「申请注销」",
    STATUS_CANCELED: "注销是终态，已注销的设备不允许再改回在用或停用",
}

DEFAULT_OPERATOR = "值班管理员"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class RegisterService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("设备编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def stats(self) -> dict[str, int]:
        """概览数字一律按登记明细现算，避免列表变了统计还停在旧值。"""
        counts = {status: 0 for status in STATUS_ORDER}
        for row in store.rows(MODULE):
            status = row.get("status")
            if status in counts:
                counts[status] += 1
        return {
            "待登记": counts[STATUS_PENDING],
            "在用台数": counts[STATUS_IN_USE],
            "停用中": counts[STATUS_SUSPENDED],
            "已注销": counts[STATUS_CANCELED],
            "总台数": sum(counts.values()),
        }

    def create_entry(
        self, values: dict[str, Any], operator: str | None = None, remark: str | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        """提交一条设备登记。

        缺必填项当场退回并点名；同一台设备（按设备编号）重复提交时只留最早一条，
        本次内容追加到该记录的备注里，不覆盖原值。
        """
        operator = (operator or DEFAULT_OPERATOR).strip() or DEFAULT_OPERATOR

        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"登记未提交：缺少必填项{'、'.join(missing)}，请补全后再提交"

        code = str(values.get("设备编号") or "").strip()
        rows = store.rows(MODULE)
        duplicate = next((row for row in rows if str(row.get("设备编号") or "").strip() == code), None)
        if duplicate is not None:
            self._append_duplicate_note(duplicate, values, operator, remark)
            self._audit(duplicate, "重复提交登记", duplicate["status"], duplicate["status"], operator)
            return duplicate, (
                f"设备编号 {code} 已有最早一条登记（{duplicate.get('登记证号', '—')}），"
                "本次重复提交未生成新记录，补充内容已另存为备注，原记录未覆盖"
            )

        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in ALL_FIELDS:
            value = values.get(field)
            entry[field] = str(value).strip() if value is not None else ""
        entry["status"] = STATUS_PENDING
        entry["登记状态"] = STATUS_PENDING
        entry["pending"] = True
        entry["abnormal"] = False
        entry["流转记录"] = []
        entry["重复登记备注"] = ""
        rows.append(entry)
        self._audit(entry, "提交登记", "", STATUS_PENDING, operator)
        return entry, "登记已提交，当前状态：待登记，办完登记后方可申请停用"

    def run_action(
        self, entry_id: int, action: str, operator: str | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"设备登记 {entry_id} 不存在或已归档"
        if action not in ACTION_LABELS:
            return None, f"动作「{action}」不属于使用登记可执行范围"

        operator = (operator or DEFAULT_OPERATOR).strip() or DEFAULT_OPERATOR
        current = str(entry.get("status") or "")
        target = TRANSITIONS.get(current, {}).get(action)
        if target is None:
            return None, f"「{action}」被退回：设备当前为「{current}」，{BLOCK_HINTS.get(current, '状态不允许该操作')}"

        before = current
        entry["status"] = target
        entry["登记状态"] = target
        entry["pending"] = target == STATUS_PENDING
        entry["abnormal"] = False
        self._audit(entry, action, before, target, operator)
        return entry, f"已{action}：{before} → {target}（经手人 {operator}）"

    def _append_duplicate_note(
        self,
        entry: dict[str, Any],
        values: dict[str, Any],
        operator: str,
        remark: str | None,
    ) -> None:
        """重复提交只追加备注：保留最早一条登记，后续内容按时间顺序另存。"""
        extras = []
        for field in ALL_FIELDS:
            value = str(values.get(field) or "").strip()
            if value and value != str(entry.get(field) or "").strip():
                extras.append(f"{field}={value}")
        if remark and remark.strip():
            extras.append(f"备注={remark.strip()}")
        detail = "；".join(extras) if extras else "无补充字段"
        line = f"[{_now()}] {operator} 重复提交登记，{detail}"
        existing = str(entry.get("重复登记备注") or "").strip()
        entry["重复登记备注"] = f"{existing}\n{line}" if existing else line

    def _audit(
        self,
        entry: dict[str, Any],
        action: str,
        before: str,
        after: str,
        operator: str,
    ) -> None:
        """每一步都留下时间、经手人与状态变化，事后查得到是谁办的。"""
        entry.setdefault("流转记录", []).append(
            {"时间": _now(), "经手人": operator, "动作": action, "变更前": before, "变更后": after}
        )
