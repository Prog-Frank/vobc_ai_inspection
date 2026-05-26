"""
智能巡检服务模块
- 规则加载
- 单帧/多帧规则检查
- 巡检结果汇总
"""
import json
from pathlib import Path
from typing import List, Optional


class InspectionService:
    def __init__(self, rules_dir: Path):
        self.rules_dir = Path(rules_dir)
        self.rules_dir.mkdir(parents=True, exist_ok=True)
        self._rules_cache = None

    def load_rules(self) -> List[dict]:
        rules = []
        for f in self.rules_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    rule = json.load(fp)
                    rule["_file"] = f.stem
                    rules.append(rule)
            except Exception:
                continue
        self._rules_cache = rules
        return rules

    def get_rules(self) -> List[dict]:
        if self._rules_cache is None:
            return self.load_rules()
        return self._rules_cache

    def get_grouped_rules(self) -> dict:
        rules = self.get_rules()
        grouped = {}
        for r in rules:
            cat = r.get("category", "其他")
            if cat not in grouped:
                grouped[cat] = []
            grouped[cat].append({
                "name": r.get("name", ""),
                "category": cat,
                "severity": r.get("severity", "info"),
                "system": r.get("system", ""),
                "type": r.get("type", "single_frame"),
                "file": r.get("_file", ""),
            })
        return grouped

    def check_single_frame(self, records: List[dict], rule: dict) -> List[dict]:
        hits = []
        conditions = rule.get("conditions", [])
        logic = rule.get("logic", "and")
        system = rule.get("system", "")

        for idx, rec in enumerate(records):
            if rec.get("系统") != system and system:
                continue
            results = []
            for cond in conditions:
                field = cond.get("field", "")
                op = cond.get("op", "eq")
                threshold = cond.get("value")
                actual = rec.get(field, "")

                try:
                    if op == "eq":
                        results.append(str(actual) == str(threshold))
                    elif op == "neq":
                        results.append(str(actual) != str(threshold))
                    elif op == "contains":
                        results.append(str(threshold) in str(actual))
                    elif op in ("gt", "lt", "gte", "lte"):
                        a, t = float(actual), float(threshold)
                        if op == "gt":
                            results.append(a > t)
                        elif op == "lt":
                            results.append(a < t)
                        elif op == "gte":
                            results.append(a >= t)
                        elif op == "lte":
                            results.append(a <= t)
                    else:
                        results.append(False)
                except (ValueError, TypeError):
                    results.append(False)

            if not results:
                continue
            hit = all(results) if logic == "and" else any(results)
            if hit:
                actual_values = {}
                for cond in conditions:
                    field = cond.get("field", "")
                    actual_values[field] = rec.get(field, "")
                hits.append({
                    "index": idx,
                    "record": {k: rec.get(k, "") for k in list(rec.keys())[:10]},
                    "actual_values": actual_values,
                    "time": rec.get("时间", ""),
                })
        return hits

    def check(
        self,
        session,
        parser,
        LABEL_MAP_REVERSE: dict,
        systems: List[str],
        selected_rules: Optional[List[str]] = None,
        max_frames: int = 5000,
        max_results: int = 500,
    ) -> dict:
        rules = self.get_rules()
        if selected_rules:
            active_rules = [r for r in rules if r.get("_file", "") in selected_rules]
        else:
            active_rules = rules

        results = []
        total_critical = 0
        total_warning = 0

        for rule in active_rules:
            rule_system = rule.get("system", "")
            if rule_system not in systems:
                continue

            target_label = LABEL_MAP_REVERSE.get(rule_system)
            if target_label is None:
                continue

            hits_idx = [(midx, off, ln) for midx, off, ln, lbl in session.index if lbl == target_label]
            check_hits = hits_idx[:max_frames]
            records = []
            for midx, off, ln in check_hits:
                frame = session.get_frame(midx, off, ln)
                record = parser.parse_frame(frame, rule_system)
                if record:
                    record["系统"] = rule_system
                    records.append(record)

            hits = self.check_single_frame(records, rule)

            severity = rule.get("severity", "info")
            if hits:
                if severity == "critical":
                    total_critical += len(hits)
                elif severity == "warning":
                    total_warning += len(hits)

                for h in hits:
                    msg = rule.get("message", "")
                    for cond in rule.get("conditions", []):
                        msg = msg.replace("{value}", str(cond.get("value", "")))
                    msg = msg.replace("{actual}", str(h.get("actual_values", "")))

                    results.append({
                        "rule_name": rule.get("name", ""),
                        "category": rule.get("category", ""),
                        "severity": severity,
                        "system": rule_system,
                        "time": h["time"],
                        "message": msg,
                        "actual_values": h.get("actual_values", {}),
                        "suggestion": rule.get("suggestion", ""),
                    })

        severity_order = {"critical": 0, "warning": 1, "info": 2}
        results.sort(key=lambda x: severity_order.get(x["severity"], 3))

        return {
            "results": results[:max_results],
            "summary": {
                "total": len(results),
                "critical": total_critical,
                "warning": total_warning,
            }
        }
