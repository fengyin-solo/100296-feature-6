"""使用登记业务规则：状态流转、字段校验与筛选口径都收在这里。

状态关口（只能相邻流转，不许跳步）：
    待登记 --办理登记--> 已登记 --申请停用--> 停用中 --解停恢复--> 已登记
                         已登记 --申请注销--> 已注销（终态，不能再改回在用）
                         停用中 --申请注销--> 已注销（恢复在用仍须先解停）
每一步流转都在 history 里记下动作、时间、经手人；同一台设备重复提交登记时，
只保留最早那条，后提交的内容追加进备注，不覆盖原记录。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "register"
# 登记证号、使用单位是办证台账的硬指标，缺一项都不允许提交。
REQUIRED_FIELDS = ["设备编号", "设备名称", "设备种类", "使用单位", "登记证号"]
# 重复登记另存备注时，顺带留档的提交字段。
SUBMIT_FIELDS = ["设备名称", "设备种类", "使用单位", "安装地点", "投用日期", "登记证号"]
STATUS_ORDER = ["待登记", "已登记", "停用中", "已注销"]
DEFAULT_OPERATOR = "值班管理员"

# 每个状态下允许办理的动作及目标状态；不在表里的动作一律当场退回。
# 停用中的设备：恢复在用必须先走「解停恢复」；直接退出台账可办「申请注销」。
TRANSITIONS: dict[str, dict[str, str]] = {
    "待登记": {"办理登记": "已登记"},
    "已登记": {"申请停用": "停用中", "申请注销": "已注销"},
    "停用中": {"解停恢复": "已登记", "申请注销": "已注销"},
    "已注销": {},
}
ALL_ACTIONS = ["办理登记", "申请停用", "解停恢复", "申请注销"]

# 跳步申请时的退回说明：（当前状态，动作）-> 卡在哪一步、该先走哪一步。
REJECT_REASONS: dict[tuple[str, str], str] = {
    ("待登记", "申请停用"): "当前停在「待登记」：得先办完登记成为「已登记」，才能申请停用。",
    ("待登记", "申请注销"): "当前停在「待登记」：得先办完登记成为「已登记」，才能申请注销。",
    ("待登记", "解停恢复"): "当前停在「待登记」，设备还没办过登记，无停可解；请先办理登记。",
    ("已登记", "办理登记"): "设备已经是「已登记」，不能重复办理登记。",
    ("已登记", "解停恢复"): "设备目前「已登记」、并未停用，无需解停恢复。",
    ("停用中", "办理登记"): "设备已办过登记，当前停在「停用中」：恢复在用请办理解停恢复，不能重复登记。",
    ("停用中", "申请停用"): "设备已经处于「停用中」，无需重复申请停用；恢复使用请办理解停恢复。",
}


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
        """概览卡片口径：全量明细实时重算，在用台数只认「已登记」。

        停用中属于暂离使用现场，已注销已退出台账，都不计入在用。
        """
        counts = {status: 0 for status in STATUS_ORDER}
        for row in store.rows(MODULE):
            status = row.get("status")
            if status in counts:
                counts[status] += 1
        counts["在用台数"] = counts["已登记"]
        return counts

    def create_entry(
        self, values: dict[str, Any], operator: str
    ) -> tuple[dict[str, Any] | None, str]:
        """提交登记。返回（记录, 说明）：说明为空表示成功，非空表示当场退回。"""
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}，补齐后才能提交登记。"

        device_code = str(values["设备编号"]).strip()
        rows = store.rows(MODULE)
        now = _now()
        duplicate = next(
            (row for row in rows if str(row.get("设备编号", "")).strip() == device_code),
            None,
        )
        if duplicate is not None:
            # 只留最早那条：本次不新建记录，内容追加为备注，并留一条重复登记流水。
            note = self._duplicate_note(values, operator, now)
            duplicate["备注"] = f"{duplicate.get('备注', '')}{note}".strip()
            self._append_history(
                duplicate, "重复登记（已另存备注）", duplicate.get("status", ""),
                duplicate.get("status", ""), operator, now,
            )
            return duplicate, (
                f"设备编号 {device_code} 已有登记记录（编号 {duplicate.get('id')}，"
                f"当前状态「{duplicate.get('status')}」），只保留最早一条；"
                "本次重复提交的内容已另存为备注，未覆盖原记录。"
            )

        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in set(REQUIRED_FIELDS + SUBMIT_FIELDS):
            value = values.get(field)
            if value is not None and str(value).strip():
                entry[field] = str(value).strip()
        self._apply_status(entry, STATUS_ORDER[0])
        entry["history"] = []
        self._append_history(entry, "提交登记", "", STATUS_ORDER[0], operator, now)
        rows.append(entry)
        return entry, ""

    def run_action(
        self, entry_id: int, action: str, operator: str
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"设备登记 {entry_id} 不存在或已归档"
        if action not in ALL_ACTIONS:
            return None, f"动作「{action}」不属于使用登记可执行范围"

        current = str(entry.get("status") or STATUS_ORDER[0])
        allowed = TRANSITIONS.get(current, {})
        if action not in allowed:
            if current == "已注销":
                return None, "设备已注销并退出在用台账，注销后不允许再改回在用。"
            return None, REJECT_REASONS.get(
                (current, action), f"当前停在「{current}」，动作「{action}」不允许办理。"
            )

        target = allowed[action]
        now = _now()
        self._apply_status(entry, target)
        self._append_history(entry, action, current, target, operator, now)
        return entry, f"已{action}，当前状态「{target}」；操作时间 {now}，经手人 {operator}。"

    # ---- 内部辅助 -------------------------------------------------------

    def _apply_status(self, entry: dict[str, Any], status: str) -> None:
        entry["status"] = status
        entry["登记状态"] = status
        # 只有刚提交、还没办证的算待处理；停用与注销都不是异常，只是状态流转。
        entry["pending"] = status == "待登记"
        entry["abnormal"] = False

    def _append_history(
        self,
        entry: dict[str, Any],
        action: str,
        source: str,
        target: str,
        operator: str,
        moment: str,
    ) -> None:
        entry.setdefault("history", []).append(
            {"action": action, "from": source, "to": target, "time": moment, "operator": operator}
        )

    def _duplicate_note(self, values: dict[str, Any], operator: str, moment: str) -> str:
        details = "；".join(
            f"{field}={str(values.get(field)).strip()}"
            for field in SUBMIT_FIELDS
            if str(values.get(field) or "").strip()
        )
        return f"\n[{moment} 重复登记，经手人：{operator}] 本次提交内容：{details or '未填写其他字段'}"
