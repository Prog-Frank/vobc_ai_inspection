"""
导出服务模块
- 按系统导出全量数据
- 生成 csv / xlsx 文件
- 返回文件路径（由 app.py 包装为 FileResponse）
"""
import os
from pathlib import Path
from typing import List, Optional


class ExportService:
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(
        self,
        session,
        parser,
        LABEL_MAP_REVERSE: dict,
        systems: List[str],
        format: str = "csv",
    ) -> dict:
        all_records = []

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
            for midx, off, ln in hits:
                frame = session.get_frame(midx, off, ln)
                record = parser.parse_frame(frame, sys_name)
                if record:
                    record["系统"] = sys_name
                    all_records.append(record)

        if not all_records:
            return {"error": "所选系统无数据"}

        file_name = ", ".join(session.file_names)
        log_time = os.path.splitext(file_name)[0] if file_name else "unknown"

        sys_label = "_".join(systems[:3])
        if len(systems) > 3:
            sys_label += f"_等{len(systems)}系统"

        import pandas as pd
        if format == "csv":
            out_path = self.output_dir / f"{sys_label}_{log_time}.csv"
            df = pd.DataFrame(all_records)
            df.to_csv(str(out_path), index=False, encoding="utf-8-sig")
        else:
            out_path = self.output_dir / f"{sys_label}_{log_time}.xlsx"
            df = pd.DataFrame(all_records)
            df.to_excel(str(out_path), index=False, engine="openpyxl")

        return {
            "path": str(out_path),
            "filename": out_path.name,
            "record_count": len(all_records),
        }
