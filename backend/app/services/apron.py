"""机坪巡查业务规则：状态流转、发现问题登记、整改回填与区域汇总都收在这里。

闭环口径：
- 巡查单提交结果时，按巡查项目逐项登记发现问题数，发现问题数大于 0 的项目生成待整改事项；
  发现问题数空缺或为负数时拒绝提交并在操作留痕里照旧记一笔。
- 提交整改时逐项回填整改结论与整改人，重复提交只保留最后一次；全部待整改事项回填后
  才能流转到最终状态「已整改」。
- 状态只能沿顺序前进，不允许回到前一段；「已作废」是终止态，派发巡查、作废巡查继续可用。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "apron"
REQUIRED_FIELDS = ["巡查单号", "巡查区域", "巡查人员"]
# 已整改是巡查闭环的最终状态；已作废是终止态，两者都不再向后流转
STATUS_ORDER = ["待派发", "巡查中", "已提交", "已整改", "已作废"]
FINAL_STATUS = "已整改"
VOID_STATUS = "已作废"
# 只允许前进：待派发→巡查中→已提交，整改全部回填后→已整改；作废为终止态
ACTION_RULES = {"派发巡查": "巡查中", "提交结果": "已提交", "提交整改": "已整改", "作废巡查": "已作废"}
NEGATIVE_ACTIONS = ["作废巡查"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _issue_count(row: dict[str, Any]) -> int:
    """巡查单发现问题总数：优先取逐项明细之和，其次回退到单数字段。"""
    items = row.get("items")
    if isinstance(items, list) and items:
        return sum(int(item.get("发现问题数") or 0) for item in items if isinstance(item, dict))
    try:
        return max(int(row.get("发现问题数") or 0), 0)
    except (TypeError, ValueError):
        return 0


def _open_items(row: dict[str, Any]) -> list[dict[str, Any]]:
    """仍待整改的事项：有发现问题且整改结论或整改人还没回填齐。"""
    items = row.get("items")
    if not isinstance(items, list):
        return []
    return [
        item
        for item in items
        if isinstance(item, dict)
        and int(item.get("发现问题数") or 0) > 0
        and (not str(item.get("整改结论") or "").strip() or not str(item.get("整改人") or "").strip())
    ]


def _to_count(raw: Any) -> tuple[int | None, str | None]:
    """把前端提交的发现问题数解析成非负整数；空缺、负数、非整数都判错。"""
    if isinstance(raw, bool):
        return None, "发现问题数必须是非负整数"
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, "发现问题数空缺"
    try:
        count = int(raw) if isinstance(raw, int) else int(str(raw).strip())
    except (TypeError, ValueError):
        return None, "发现问题数必须是非负整数"
    if count < 0:
        return None, "发现问题数不能为负数"
    return count, None


class ApronService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filter(keyword=keyword, status=status)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def area_summary(self, *, keyword: str | None = None, status: str | None = None) -> dict[str, Any]:
        """按巡查区域汇总发现问题数；与巡查单列表共用同一套筛选口径，刷新后仍由仓库实时计算。"""
        month_prefix = datetime.now().strftime("%Y-%m")
        groups: dict[str, dict[str, Any]] = {}
        for row in self._filter(keyword=keyword, status=status):
            area = str(row.get("巡查区域") or "未分区")
            bucket = groups.setdefault(
                area,
                {"巡查区域": area, "巡查单数": 0, "发现问题数": 0, "待整改数": 0, "已整改数": 0, "本月发现问题": 0},
            )
            items = row.get("items") if isinstance(row.get("items"), list) else []
            found = _issue_count(row)
            pending = len(_open_items(row))
            repaired = sum(
                1
                for item in items
                if isinstance(item, dict)
                and int(item.get("发现问题数") or 0) > 0
                and str(item.get("整改结论") or "").strip()
                and str(item.get("整改人") or "").strip()
            )
            bucket["巡查单数"] += 1
            bucket["发现问题数"] += found
            bucket["待整改数"] += pending
            bucket["已整改数"] += repaired
            if str(row.get("巡查日期") or "").startswith(month_prefix):
                bucket["本月发现问题"] += found
        items = sorted(groups.values(), key=lambda item: item["巡查区域"])
        total = {
            "巡查区域": "合计",
            "巡查单数": sum(item["巡查单数"] for item in items),
            "发现问题数": sum(item["发现问题数"] for item in items),
            "待整改数": sum(item["待整改数"] for item in items),
            "已整改数": sum(item["已整改数"] for item in items),
            "本月发现问题": sum(item["本月发现问题"] for item in items),
        }
        return {"items": items, "total": total}

    def _filter(self, *, keyword: str | None, status: str | None) -> list[dict[str, Any]]:
        rows = list(store.rows(MODULE))
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("巡查单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for field in ("巡查日期", "巡查时长"):
            if str(values.get(field) or "").strip():
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["items"] = []
        entry["操作留痕"] = []
        self._audit(entry, "登记巡查单", True, "巡查单已登记")
        rows.append(entry)
        return entry, []

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"巡查单 {entry_id} 不存在或已归档"
        entry.setdefault("操作留痕", [])
        if action not in ACTION_RULES:
            message = f"动作「{action}」不属于机坪巡查可执行范围"
            self._audit(entry, action, False, message, values)
            return None, message

        if action == "派发巡查":
            return self._dispatch(entry)
        if action == "提交结果":
            return self._submit_findings(entry, values)
        if action == "提交整改":
            return self._submit_repairs(entry, values)
        if action == "作废巡查":
            return self._void(entry, values)
        return None, f"动作「{action}」不属于机坪巡查可执行范围"

    def _dispatch(self, entry: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        if entry["status"] != "待派发":
            message = f"当前状态「{entry['status']}」不允许派发巡查，巡查单只能沿流程前进"
            self._audit(entry, "派发巡查", False, message)
            return None, message
        entry["status"] = "巡查中"
        entry["pending"] = True
        self._audit(entry, "派发巡查", True, "巡查单已派发")
        return entry, "巡查单已派发巡查"

    def _submit_findings(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        if entry["status"] != "巡查中":
            message = f"当前状态「{entry['status']}」不允许提交结果，状态不允许回到前一段"
            self._audit(entry, "提交结果", False, message, values)
            return None, message
        raw_items = values.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            message = "提交结果须按巡查项目逐项登记发现问题数"
            self._audit(entry, "提交结果", False, message, values)
            return None, message

        parsed: list[dict[str, Any]] = []
        seen: set[str] = set()
        errors: list[str] = []
        for index, raw in enumerate(raw_items, start=1):
            if not isinstance(raw, dict):
                errors.append(f"第 {index} 项不是有效的巡查项目")
                continue
            name = str(raw.get("项目") or raw.get("巡查项目") or "").strip()
            if not name:
                errors.append(f"第 {index} 项巡查项目空缺")
            elif name in seen:
                errors.append(f"巡查项目「{name}」重复登记")
            count, count_error = _to_count(raw.get("发现问题数"))
            if count_error:
                errors.append(f"巡查项目「{name or index}」{count_error}")
            if name and name not in seen and count is not None:
                seen.add(name)
                parsed.append({"巡查项目": name, "发现问题数": count})
        # 任何一项不合法都整单驳回，数据原样不动，只补一条留痕
        if errors:
            message = "发现问题登记失败：" + "；".join(errors)
            self._audit(entry, "提交结果", False, message, values)
            return None, message

        for field in ("巡查日期", "巡查时长"):
            if str(values.get(field) or "").strip():
                entry[field] = values.get(field)
        entry["items"] = parsed
        entry["巡查项目"] = self._join_items(parsed)
        entry["发现问题数"] = sum(int(item["发现问题数"]) for item in parsed)
        if entry["发现问题数"] == 0:
            # 没有发现问题，无需整改，直接闭环
            entry["status"] = FINAL_STATUS
            entry["pending"] = False
            message = "巡查结果已提交，未发现问题，巡查单已闭环"
        else:
            entry["status"] = "已提交"
            entry["pending"] = True
            message = f"巡查结果已提交，已生成 {entry['发现问题数']} 项待整改事项"
        entry["abnormal"] = False
        self._audit(entry, "提交结果", True, message, {"项目数": len(parsed), "发现问题数": entry["发现问题数"]})
        return entry, message

    def _submit_repairs(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        if entry["status"] not in ("已提交", FINAL_STATUS):
            message = f"当前状态「{entry['status']}」不允许提交整改结论"
            self._audit(entry, "提交整改", False, message, values)
            return None, message
        raw_items = values.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            message = "提交整改须逐项回填整改结论与整改人"
            self._audit(entry, "提交整改", False, message, values)
            return None, message

        existing = {
            str(item.get("巡查项目")): item
            for item in entry.get("items", [])
            if isinstance(item, dict)
        }
        updates: list[tuple[dict[str, Any], str, str]] = []
        errors: list[str] = []
        seen: set[str] = set()
        for index, raw in enumerate(raw_items, start=1):
            if not isinstance(raw, dict):
                errors.append(f"第 {index} 项不是有效的整改事项")
                continue
            name = str(raw.get("项目") or raw.get("巡查项目") or "").strip()
            item = existing.get(name)
            if not name or item is None:
                errors.append(f"第 {index} 项巡查项目与待整改事项对不上")
                continue
            if int(item.get("发现问题数") or 0) <= 0:
                errors.append(f"巡查项目「{name}」没有发现问题，无需整改")
                continue
            if name in seen:
                errors.append(f"巡查项目「{name}」重复提交整改结论")
                continue
            conclusion = str(raw.get("整改结论") or "").strip()
            repairer = str(raw.get("整改人") or "").strip()
            if not conclusion or not repairer:
                errors.append(f"巡查项目「{name}」整改结论或整改人空缺")
                continue
            seen.add(name)
            updates.append((item, conclusion, repairer))
        if errors:
            message = "整改回填失败：" + "；".join(errors)
            self._audit(entry, "提交整改", False, message, values)
            return None, message

        # 同一条巡查单重复提交整改结论只保留最后一次：直接覆盖原结论与整改人
        for item, conclusion, repairer in updates:
            item["整改结论"] = conclusion
            item["整改人"] = repairer
            item["整改时间"] = _now()

        open_items = _open_items(entry)
        repaired = sum(
            1
            for item in entry.get("items", [])
            if isinstance(item, dict)
            and int(item.get("发现问题数") or 0) > 0
            and str(item.get("整改结论") or "").strip()
            and str(item.get("整改人") or "").strip()
        )
        if open_items:
            # 结论没回填齐：不允许流转到最终状态，也不允许回到前一段，维持已提交
            message = f"已回填 {repaired} 项整改结论，仍有 {len(open_items)} 项待整改，巡查单暂不能闭环"
            self._audit(entry, "提交整改", True, message, {"回填项数": len(updates)})
            entry["status"] = "已提交"
            entry["pending"] = True
            return entry, message

        entry["status"] = FINAL_STATUS
        entry["pending"] = False
        message = f"全部 {repaired} 项整改结论已回填，巡查单闭环"
        self._audit(entry, "提交整改", True, message, {"回填项数": len(updates)})
        return entry, message

    def _void(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        if entry["status"] == VOID_STATUS:
            message = "巡查单已作废，不能重复作废"
            self._audit(entry, "作废巡查", False, message, values)
            return None, message
        if entry["status"] == FINAL_STATUS:
            message = "巡查单已闭环，不允许作废"
            self._audit(entry, "作废巡查", False, message, values)
            return None, message
        entry["status"] = VOID_STATUS
        entry["pending"] = False
        entry["abnormal"] = True
        self._audit(entry, "作废巡查", True, "巡查单已作废", values or None)
        return entry, "巡查单已作废"

    def _join_items(self, parsed: list[dict[str, Any]]) -> str:
        return "、".join(item["巡查项目"] for item in parsed)

    def _audit(
        self,
        entry: dict[str, Any],
        action: str,
        ok: bool,
        message: str,
        submitted: dict[str, Any] | None = None,
    ) -> None:
        """成功、失败都照旧留痕，方便追查被拦下的提交。"""
        record: dict[str, Any] = {
            "时间": _now(),
            "动作": action,
            "结果": "成功" if ok else "失败",
            "说明": message,
        }
        if submitted:
            record["提交内容"] = submitted
        entry.setdefault("操作留痕", []).append(record)
