"""机坪巡查业务规则：状态流转、字段校验、发现问题逐项登记与整改闭环都收在这里。

状态序列：待派发 → 巡查中 → 已提交 → 已整改（已作废为任何非终态都可进入的负向终态）。
- 提交结果：按巡查项目逐项登记发现问题数，为每个有问题的项目生成一条待整改事项；
  发现问题数空缺或为负数时拦截并在操作留痕里记录。
- 回填整改：向待整改事项回填整改结论与整改人，同一条巡查单重复回填只保留最后一次。
- 完成整改：仍有整改结论未回填的事项时不允许流转到最终状态；状态只进不退，
  不允许回到前一段。派发巡查与作废巡查动作继续可用。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "apron"
REQUIRED_FIELDS = ["巡查单号", "巡查区域", "巡查人员"]
STATUS_ORDER = ["待派发", "巡查中", "已提交", "已整改"]
VOID_STATUS = "已作废"
RECTIFY_ACTION = "回填整改"
VOID_ACTION = "作废巡查"
FINAL_STATUSES = ["已整改", VOID_STATUS]
SUBMIT_FIELDS = ["巡查日期", "巡查时长", "巡查人员"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _as_int(raw: Any) -> int | None:
    """把前端传过来的问题数转成非负整数；空串、None 视为空缺，非整数也报回。"""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


class ApronService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        area: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filtered_rows(keyword=keyword, status=status, area=area)
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = rows[start:start + size]
        return [self._list_view(row) for row in page_rows], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["发现问题数"] = 0
        entry["待整改事项"] = []
        entry["操作留痕"] = []
        rows.append(entry)
        return entry, []

    def area_summary(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        area: str | None = None,
    ) -> list[dict[str, Any]]:
        """按巡查区域汇总发现问题数；口径与列表完全一致（同一套筛选、同一份数据）。"""
        rows = self._filtered_rows(keyword=keyword, status=status, area=area)
        summaries: list[dict[str, Any]] = []
        index: dict[str, dict[str, Any]] = {}
        for row in rows:
            region = str(row.get("巡查区域") or "未填写区域")
            if region not in index:
                index[region] = {
                    "巡查区域": region,
                    "巡查单数": 0,
                    "发现问题数": 0,
                    "待整改数": 0,
                    "已整改数": 0,
                }
                summaries.append(index[region])
            bucket = index[region]
            bucket["巡查单数"] += 1
            bucket["发现问题数"] += int(row.get("发现问题数") or 0)
            total_items = row.get("待整改事项") or []
            bucket["待整改数"] += sum(
                1
                for item in total_items
                if int(item.get("发现问题数") or 0) > 0 and not item.get("整改结论")
            )
            bucket["已整改数"] += sum(1 for item in total_items if item.get("整改结论"))
        return summaries

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str, bool]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"巡查单 {entry_id} 不存在或已归档", False
        entry.setdefault("待整改事项", [])
        entry.setdefault("操作留痕", [])

        if action == "派发巡查":
            ok, message = self._dispatch(entry)
        elif action == "提交结果":
            ok, message = self._submit(entry, values)
        elif action == RECTIFY_ACTION:
            ok, message = self._apply_rectification(entry, values)
        elif action == "完成整改":
            ok, message = self._finish(entry)
        elif action == VOID_ACTION:
            ok, message = self._void(entry)
        else:
            message = f"动作「{action}」不属于机坪巡查可执行范围"
            self._trace(entry, action, False, message)
            ok = False
        return entry, message, ok

    # ----- 动作规则 -----

    def _dispatch(self, entry: dict[str, Any]) -> tuple[bool, str]:
        action = "派发巡查"
        blocked = self._check_current(entry, action, allowed_current=["待派发"])
        if blocked:
            return False, blocked
        entry["status"] = "巡查中"
        entry["pending"] = True
        entry["abnormal"] = False
        self._trace(entry, action, True, "状态由「待派发」流转为「巡查中」")
        return True, f"巡查单已{action}"

    def _finish(self, entry: dict[str, Any]) -> tuple[bool, str]:
        action = "完成整改"
        blocked = self._check_current(entry, action, allowed_current=["已提交"])
        if blocked:
            return False, blocked
        if not entry.get("待整改事项"):
            # 提交时没有发现问题：已提交即可视为闭环终点，无需再走完成整改
            message = "该巡查单没有待整改事项，无需完成整改"
            self._trace(entry, action, False, message)
            return False, message
        pending = self._pending_items(entry)
        if pending:
            names = "、".join(str(item.get("巡查项目")) for item in pending)
            message = (
                f"巡查项目「{names}」的整改结论尚未回填，"
                "巡查单不允许流转到最终状态（已整改）；请先逐条回填整改结论与整改人"
            )
            self._trace(entry, action, False, message)
            return False, message
        entry["status"] = "已整改"
        entry["pending"] = False
        entry["abnormal"] = False
        self._trace(entry, action, True, "整改事项全部回填，状态流转为「已整改」")
        return True, f"巡查单已{action}"

    def _void(self, entry: dict[str, Any]) -> tuple[bool, str]:
        action = VOID_ACTION
        current = str(entry.get("status") or "")
        if current == VOID_STATUS:
            message = "巡查单已作废，不能重复作废"
            self._trace(entry, action, False, message)
            return False, message
        if current == "已整改":
            message = "巡查单已整改归档，不允许作废"
            self._trace(entry, action, False, message)
            return False, message
        entry["status"] = VOID_STATUS
        entry["pending"] = False
        entry["abnormal"] = True
        self._trace(entry, action, True, f"状态由「{current}」作废")
        return True, f"巡查单已{action}"

    def _submit(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[bool, str]:
        action = "提交结果"
        blocked = self._check_current(entry, action, allowed_current=["巡查中"])
        if blocked:
            return False, blocked

        details, error = self._build_items(values)
        if error:
            # 发现问题数空缺或为负数：拦截状态流转，同时照旧留痕
            self._trace(entry, action, False, error)
            return False, error

        seq = 0
        items: list[dict[str, Any]] = []
        for name, count in details:
            if count <= 0:
                # 该项目没有问题，登记问题数但不生成待整改事项
                continue
            seq += 1
            items.append({
                "事项编号": f"{entry['巡查单号']}-R{seq:02d}",
                "巡查项目": name,
                "发现问题数": count,
                "整改结论": None,
                "整改人": None,
                "整改时间": None,
            })

        for field in SUBMIT_FIELDS:
            raw = values.get(field)
            if raw is not None and str(raw).strip():
                entry[field] = raw
        entry["巡查项目"] = "、".join(name for name, _ in details)
        entry["待整改事项"] = items
        entry["发现问题数"] = sum(count for _, count in details)
        entry["status"] = "已提交"
        # 仍有待整改事项时业务上未闭环，继续计入待处理；零问题单提交即闭环
        entry["pending"] = bool(items)
        entry["abnormal"] = False
        pending_count = len([1 for _, count in details if count > 0])
        self._trace(
            entry,
            action,
            True,
            f"登记巡查项目 {len(details)} 项，发现问题 {entry['发现问题数']} 个，"
            f"生成待整改事项 {pending_count} 条",
        )
        return True, f"巡查单已{action}"

    def _apply_rectification(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[bool, str]:
        action = RECTIFY_ACTION
        current = str(entry.get("status") or "")
        if current in FINAL_STATUSES:
            message = f"巡查单已处于「{current}」终态，不允许再回填整改结论"
            self._trace(entry, action, False, message)
            return False, message
        if current != "已提交":
            message = (
                f"巡查单当前状态为「{current}」，尚未提交巡查结果，无法回填整改结论"
            )
            self._trace(entry, action, False, message)
            return False, message
        raw_items = values.get("整改明细")
        if not isinstance(raw_items, list) or not raw_items:
            message = "整改明细不能为空，请逐条回填整改结论与整改人"
            self._trace(entry, action, False, message)
            return False, message

        items = entry.setdefault("待整改事项", [])
        updates: list[dict[str, Any]] = []
        for index, payload in enumerate(raw_items, start=1):
            if not isinstance(payload, dict):
                message = f"第 {index} 条整改明细格式不正确"
                self._trace(entry, action, False, message)
                return False, message
            key = str(payload.get("事项编号") or payload.get("巡查项目") or "").strip()
            target = None
            if key:
                for item in items:
                    if item.get("事项编号") == key or item.get("巡查项目") == key:
                        target = item
                        break
            if target is None:
                message = f"第 {index} 条整改明细匹配不到待整改事项，请核对事项编号或巡查项目"
                self._trace(entry, action, False, message)
                return False, message
            conclusion = str(payload.get("整改结论") or "").strip()
            rectifier = str(payload.get("整改人") or "").strip()
            if not conclusion or not rectifier:
                message = (
                    f"巡查项目「{target.get('巡查项目')}」的整改结论与整改人均需回填，"
                    "缺少任一项都不能提交"
                )
                self._trace(entry, action, False, message)
                return False, message
            updates.append({"item": target, "结论": conclusion, "整改人": rectifier})

        # 全部校验通过后统一覆盖；同一条巡查单重复回填，只保留最后一次
        timestamp = _now()
        for update in updates:
            item = update["item"]
            item["整改结论"] = update["结论"]
            item["整改人"] = update["整改人"]
            item["整改时间"] = timestamp
        self._trace(
            entry,
            action,
            True,
            f"回填整改结论 {len(updates)} 条（重复提交以最后一次为准）",
        )
        return True, "整改结论已回填"

    def _build_items(self, values: dict[str, Any]) -> tuple[list[tuple[str, int]], str]:
        raw_details = values.get("问题明细")
        details: list[tuple[str, Any]] = []
        if isinstance(raw_details, list) and raw_details:
            for index, detail in enumerate(raw_details, start=1):
                if not isinstance(detail, dict):
                    return [], f"第 {index} 个巡查项目的明细格式不正确"
                name = str(detail.get("巡查项目") or detail.get("name") or "").strip()
                if not name:
                    return [], f"第 {index} 个巡查项目缺少项目名称，请补全后再提交"
                details.append((name, detail.get("发现问题数", detail.get("count"))))
        else:
            project = str(values.get("巡查项目") or values.get("项目") or "").strip()
            if not project:
                return [], "巡查项目不能为空，请至少填写一个巡查项目"
            details = [(project, values.get("发现问题数"))]

        parsed: list[tuple[str, int]] = []
        for name, raw_count in details:
            count = _as_int(raw_count)
            if count is None:
                return [], f"巡查项目「{name}」的发现问题数空缺或不是整数，请填写非负整数"
            if count < 0:
                return [], f"巡查项目「{name}」的发现问题数不能为负数（当前 {count}）"
            parsed.append((name, count))
        return parsed, ""

    # ----- 共用校验与汇总 -----

    def _check_current(
        self, entry: dict[str, Any], action: str, *, allowed_current: list[str]
    ) -> str:
        """状态只进不退：终态与非上一阶段的动作都拦下，返回非空的拦截原因。"""
        current = str(entry.get("status") or "")
        if current in FINAL_STATUSES:
            return f"巡查单已处于「{current}」终态，不允许再执行「{action}」"
        if current not in allowed_current:
            return (
                f"巡查单当前状态为「{current}」，不允许执行「{action}」；"
                "状态只进不退，也不允许回到前一段，请先完成当前阶段"
            )
        return ""

    def _filtered_rows(
        self,
        *,
        keyword: str | None,
        status: str | None,
        area: str | None,
    ) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("巡查单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if area:
            rows = [row for row in rows if area in str(row.get("巡查区域", ""))]
        return rows

    def _list_view(self, row: dict[str, Any]) -> dict[str, Any]:
        """列表行：待整改数按明细实时计算，保证与按区域汇总同源。"""
        view = dict(row)
        view["待整改数"] = len(self._pending_items(row))
        return view

    def _pending_items(self, row: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            item
            for item in row.get("待整改事项") or []
            if int(item.get("发现问题数") or 0) > 0 and not item.get("整改结论")
        ]

    def _trace(self, entry: dict[str, Any], action: str, ok: bool, detail: str) -> None:
        """无论成功还是失败都追加一条操作留痕，刷新后仍随巡查单明细返回。"""
        entry.setdefault("操作留痕", []).append(
            {
                "时间": _now(),
                "动作": action,
                "结果": "成功" if ok else "失败",
                "说明": detail,
            }
        )
