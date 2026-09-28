"""机坪巡查闭环回归测试（纯标准库，直接运行：python3 tests/test_apron.py）。

覆盖：
1. 派发巡查 → 提交结果（逐项登记问题数、生成待整改事项）→ 回填整改 → 完成整改 全链路；
2. 发现问题数空缺或为负数时报错，且失败尝试照旧写入操作留痕；
3. 整改结论未回填时不允许流转到最终状态；
4. 状态只进不退，不允许回到前一段；
5. 同一条巡查单重复回填整改结论只保留最后一次；
6. 按巡查区域汇总与巡查单列表口径一致；
7. 派发巡查、作废巡查动作继续可用。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.apron import ApronService  # noqa: E402


def main() -> None:
    service = ApronService()
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        print(f"{'PASS' if condition else 'FAIL'}  {name}{(' — ' + detail) if detail else ''}")
        if not condition:
            failures.append(name)

    entry, missing = service.create_entry(
        {"巡查单号": "APRO-TEST", "巡查区域": "测试机坪", "巡查人员": "测试员"}
    )
    eid = entry["id"]
    check("登记巡查单", not missing and entry["status"] == "待派发", str(missing))

    # 未派发前不能提交结果
    _, message, ok = service.run_action(eid, "提交结果", {})
    check("未派发不允许提交结果", not ok and "状态只进不退" in message, message)

    _, message, ok = service.run_action(eid, "派发巡查", {})
    check("派发巡查", ok and entry["status"] == "巡查中", message)

    # 空缺与负数报错
    _, message, ok = service.run_action(
        eid, "提交结果", {"问题明细": [{"巡查项目": "道面", "发现问题数": ""}]}
    )
    check("发现问题数空缺报错", not ok and "空缺" in message, message)
    _, message, ok = service.run_action(
        eid, "提交结果", {"问题明细": [{"巡查项目": "道面", "发现问题数": -2}]}
    )
    check("发现问题数为负数报错", not ok and "负数" in message, message)
    failed_traces = [t for t in entry["操作留痕"] if t["结果"] == "失败"]
    check("失败尝试照旧留痕", len(failed_traces) >= 2, f"失败留痕 {len(failed_traces)} 条")
    check("报错后状态不变", entry["status"] == "巡查中", entry["status"])

    # 合法提交：逐项登记，生成待整改事项
    _, message, ok = service.run_action(
        eid,
        "提交结果",
        {
            "巡查日期": "2026-09-28",
            "巡查时长": "60分钟",
            "问题明细": [
                {"巡查项目": "道面巡查", "发现问题数": 0},
                {"巡查项目": "FOD检查", "发现问题数": 3},
                {"巡查项目": "标志标识", "发现问题数": 2},
            ],
        },
    )
    check(
        "逐项提交结果并生成待整改事项",
        ok and entry["发现问题数"] == 5 and len(entry["待整改事项"]) == 2,
        f"{message} / 问题数 {entry['发现问题数']} / 事项 {len(entry['待整改事项'])}",
    )
    check("提交后状态为已提交", entry["status"] == "已提交", entry["status"])
    check(
        "零问题项目不生成待整改事项",
        [item["巡查项目"] for item in entry["待整改事项"]] == ["FOD检查", "标志标识"],
        str([item["巡查项目"] for item in entry["待整改事项"]]),
    )

    # 不允许回到前一段
    _, message, ok = service.run_action(eid, "派发巡查", {})
    check("不允许回到前一段（重新派发）", not ok, message)

    # 未回填完不允许流转到最终状态
    _, message, ok = service.run_action(eid, "完成整改", {})
    check("整改结论未回填不允许完成整改", not ok and "尚未回填" in message, message)

    # 结论与整改人缺一不可
    _, message, ok = service.run_action(
        eid,
        "回填整改",
        {"整改明细": [{"事项编号": "APRO-TEST-R01", "整改结论": "已清理", "整改人": ""}]},
    )
    check("缺整改人时报错", not ok and "均需回填" in message, message)

    # 回填两项
    _, message, ok = service.run_action(
        eid,
        "回填整改",
        {
            "整改明细": [
                {"事项编号": "APRO-TEST-R01", "整改结论": "第一次结论", "整改人": "张三"},
                {"事项编号": "APRO-TEST-R02", "整改结论": "油漆补划", "整改人": "李四"},
            ]
        },
    )
    check("逐条回填整改结论与整改人", ok, message)

    # 重复提交只保留最后一次
    _, message, ok = service.run_action(
        eid,
        "回填整改",
        {"整改明细": [{"事项编号": "APRO-TEST-R01", "整改结论": "复查合格", "整改人": "王五"}]},
    )
    item = entry["待整改事项"][0]
    check(
        "重复回填只保留最后一次",
        ok and item["整改结论"] == "复查合格" and item["整改人"] == "王五",
        f"{item['整改结论']} / {item['整改人']}",
    )

    # 全部回填后才能闭环
    _, message, ok = service.run_action(eid, "完成整改", {})
    check("全部回填后流转到已整改", ok and entry["status"] == "已整改", message)

    # 终态不能再回填、不能作废
    _, message, ok = service.run_action(
        eid, "回填整改", {"整改明细": [{"事项编号": "APRO-TEST-R01", "整改结论": "x", "整改人": "y"}]}
    )
    check("已整改终态不允许再回填", not ok, message)
    _, message, ok = service.run_action(eid, "作废巡查", {})
    check("已整改不允许作废", not ok, message)

    # 0 问题巡查单：已提交即无待整改事项，无需完成整改
    zero, _ = service.create_entry(
        {"巡查单号": "APRO-ZERO", "巡查区域": "测试机坪", "巡查人员": "测试员"}
    )
    service.run_action(zero["id"], "派发巡查", {})
    _, _, ok = service.run_action(
        zero["id"], "提交结果", {"问题明细": [{"巡查项目": "夜间巡查", "发现问题数": 0}]}
    )
    _, message, ok = service.run_action(zero["id"], "完成整改", {})
    check("零问题单无需完成整改", not ok and "没有待整改事项" in message, message)

    # 作废继续可用：待派发/巡查中均可作废，已作废不能重复
    voided, _ = service.create_entry(
        {"巡查单号": "APRO-VOID", "巡查区域": "测试机坪", "巡查人员": "测试员"}
    )
    _, message, ok = service.run_action(voided["id"], "作废巡查", {})
    check("待派发可直接作废", ok and voided["status"] == "已作废" and voided["abnormal"], message)
    _, message, ok = service.run_action(voided["id"], "作废巡查", {})
    check("已作废不能重复作废", not ok, message)

    # 汇总与列表口径一致
    list_items, list_total = service.list_entries(area="测试机坪", page=1, size=200)
    summary = {row["巡查区域"]: row for row in service.area_summary(area="测试机坪")}
    check("汇总区域只含过滤结果", set(summary) == {"测试机坪"}, str(set(summary)))
    check(
        "汇总巡查单数与列表一致",
        summary["测试机坪"]["巡查单数"] == list_total,
        f"{summary['测试机坪']['巡查单数']} vs {list_total}",
    )
    check(
        "汇总发现问题数与列表一致",
        summary["测试机坪"]["发现问题数"]
        == sum(int(row["发现问题数"] or 0) for row in list_items),
        str(summary["测试机坪"]),
    )
    check(
        "汇总待整改数与列表一致",
        summary["测试机坪"]["待整改数"]
        == sum(int(row["待整改数"]) for row in list_items),
        str(summary["测试机坪"]),
    )

    # 状态过滤也同步
    submitted, submitted_total = service.list_entries(status="已提交", page=1, size=200)
    submitted_summary = service.area_summary(status="已提交")
    check(
        "状态过滤下汇总与列表一致",
        sum(row["巡查单数"] for row in submitted_summary) == submitted_total
        and sum(int(row["发现问题数"]) for row in submitted_summary)
        == sum(int(row["发现问题数"] or 0) for row in submitted),
        f"{submitted_total} 条",
    )

    print()
    if failures:
        print(f"{len(failures)} 项失败：{failures}")
        raise SystemExit(1)
    print("全部通过")


if __name__ == "__main__":
    main()
