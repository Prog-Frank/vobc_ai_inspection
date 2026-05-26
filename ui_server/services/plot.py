"""
绘图数据服务模块
- 解析日志数据用于绘图
- 事件检测与状态生成
- 字段列表与映射配置提取
"""
from typing import List, Optional


class PlotService:
    def __init__(self):
        pass

    def get_plot_data(
        self,
        session,
        parser,
        LABEL_MAP_REVERSE: dict,
        system: str,
        fields: List[str],
        plot_type: str = "line",
        max_records: int = 10000,
    ) -> dict:
        systems = [s.strip() for s in system.split(",") if s.strip()]
        all_records = []

        for sys_name in systems:
            if sys_name not in parser.configs:
                continue
            target_label = LABEL_MAP_REVERSE.get(sys_name)
            if target_label is None:
                continue

            hits = [(midx, off, ln) for midx, off, ln, lbl in session.index if lbl == target_label]
            hits = hits[:max_records]

            for midx, off, ln in hits:
                frame = session.get_frame(midx, off, ln)
                record = parser.parse_frame(frame, sys_name)
                if record:
                    record["系统"] = sys_name
                    all_records.append(record)

        if not all_records:
            return {"error": "未找到数据"}

        sort_key = None
        for k in ["时间", "时间戳", "记录时间"]:
            if k in all_records[0]:
                sort_key = k
                break
        if sort_key:
            all_records.sort(key=lambda r: r.get(sort_key, ""))

        timestamps = []
        field_data = {f: [] for f in fields}

        for idx, record in enumerate(all_records):
            ts = record.get(sort_key, record.get("__frame_offset__", ""))
            timestamps.append(str(ts))

            for f in fields:
                value = record.get(f, None)
                field_data[f].append(value)

        return {
            "timestamps": timestamps,
            "fields": fields,
            "data": field_data,
            "record_count": len(all_records),
            "plot_type": plot_type,
            "system": system,
            "events": [],
            "system_states": []
        }

    def get_fields(self, parser, system: str) -> List[str]:
        if system not in parser.configs:
            return []

        config = parser.configs.get(system, {})
        fields = []

        if isinstance(config, dict) and "fields" in config:
            for field_info in config["fields"]:
                if isinstance(field_info, dict) and "名称" in field_info:
                    fields.append(field_info["名称"])
        elif isinstance(config, list):
            for field_info in config:
                if isinstance(field_info, dict) and "名称" in field_info:
                    fields.append(field_info["名称"])

        return fields

    def get_mappings(self, parser, system: str) -> dict:
        if system not in parser.configs:
            return {}

        config = parser.configs.get(system, {})
        default_mappings = {}
        text_fields = []

        def extract_mapping(field_info):
            if isinstance(field_info, dict):
                name = field_info.get("名称", "")
                event_explain = field_info.get("事件说明", "")
                if name and event_explain:
                    field_mapping = {}
                    has_mapping = False
                    for item in event_explain.split("#"):
                        if ":" in item:
                            parts = item.split(":", 1)
                            if len(parts) == 2:
                                k, v = parts
                                try:
                                    field_mapping[v.strip()] = int(k.strip())
                                    has_mapping = True
                                except ValueError:
                                    continue
                    if has_mapping:
                        default_mappings[name] = field_mapping
                        text_fields.append(name)

        if isinstance(config, dict) and "fields" in config:
            for field_info in config["fields"]:
                extract_mapping(field_info)
        elif isinstance(config, list):
            for field_info in config:
                extract_mapping(field_info)

        return {"mappings": default_mappings, "text_fields": text_fields}
