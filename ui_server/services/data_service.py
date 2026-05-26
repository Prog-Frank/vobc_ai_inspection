"""
数据查询服务模块
- 多系统合并分页解析
- 字段对齐与排序
"""
from typing import List, Optional


class DataService:
    def __init__(self):
        pass

    def parse_multi_systems(
        self,
        session,
        parser,
        LABEL_MAP_REVERSE: dict,
        systems: List[str],
        page: int = 1,
        page_size: int = 10000,
    ) -> dict:
        all_results = []
        all_columns = []
        seen_cols = set()
        field_to_systems = {}

        for sys_name in systems:
            if sys_name not in parser.configs:
                continue
            target_label = LABEL_MAP_REVERSE.get(sys_name)
            if target_label is None:
                continue

            hits = [
                (midx, off, ln)
                for midx, off, ln, lbl in session.index
                if lbl == target_label
            ]
            sys_fields = set()

            for midx, off, ln in hits:
                frame = session.get_frame(midx, off, ln)
                record = parser.parse_frame(frame, sys_name)
                if record:
                    record["系统"] = sys_name
                    record["__mmap_idx__"] = midx
                    record["__frame_offset__"] = off
                    record["__frame_length__"] = ln
                    all_results.append(record)
                    for k in record.keys():
                        if not k.startswith("__"):
                            sys_fields.add(k)

            for f in sys_fields:
                if f not in field_to_systems:
                    field_to_systems[f] = []
                field_to_systems[f].append(sys_name)

        sort_key = None
        for k in ["时间", "时间戳", "记录时间"]:
            if all_results and k in all_results[0]:
                sort_key = k
                break
        if sort_key:
            all_results.sort(key=lambda r: r.get(sort_key, ""))

        for r in all_results:
            for k in r.keys():
                if k not in seen_cols:
                    all_columns.append(k)
                    seen_cols.add(k)

        unified_columns = ["系统"] + [
            c for c in all_columns
            if c not in ["系统", "__mmap_idx__", "__frame_offset__", "__frame_length__"]
        ]
        internal_cols = ["__mmap_idx__", "__frame_offset__", "__frame_length__"]

        for r in all_results:
            for col in unified_columns:
                if col not in r:
                    r[col] = None

        total = len(all_results)
        pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = min(start + page_size, total)
        page_data = all_results[start:end]

        del all_results

        return {
            "columns": unified_columns,
            "internal_columns": internal_cols,
            "total": total,
            "page": page,
            "pages": pages,
            "data": page_data,
            "systems": systems,
            "field_systems": field_to_systems,
        }
