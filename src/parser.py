"""
苏州6号线 VOBC日志解析引擎 v2
- mmap 映射文件，不一次性读入内存
- 帧索引代替帧切片，零额外内存
- 按需分页解析，不缓存全量结果
"""

import struct
import json
import os
import re
import mmap
from datetime import datetime, timedelta
from collections import OrderedDict, Counter
from pathlib import Path


# ============================================================
# 常量 — 从帧头配置文件加载
# ============================================================
FRAME_HEAD_CONFIG = {
    "无效帧固定长度": 19,
    "帧长度起始字节索引": 0,
    "帧长度占用字节数": 2,
    "时间长度起始字节索引": 2,
    "时间长度占用字节数": 8,
    "红蓝网起始字节索引": 10,
    "红蓝网占用字节数": 1,
    "正常冗余起始字节索引": 11,
    "正常冗余占用字节数": 1,
    "帧体长度起始字节索引": 12,
    "帧体长度占用字节数": 2,
    "帧标识符起始字节索引": 14,
    "帧标识符占用字节数": 1,
    "控制周期序列号起始字节索引": 15,
    "控制周期序列号占用字节数": 4,
}

# 帧标识符 → 系统名称（从 definetion.csv 加载）
FRAME_LABEL_MAP = {
    0x40: "红网CCOV", 0x41: "蓝网CCOV",
    0x42: "通信板1", 0x43: "通信板2",
    0x44: "MMI", 0x45: "ATO故障",
    0x46: "ATO应用", 0x47: "ATP应用故障",
    0x48: "ATP应用", 0x49: "ATP应用记录3",
    0x4A: "A机平台", 0x4B: "B机平台",
    0x4C: "C机平台", 0x4D: "记录系统自身",
    0x4E: "ATP测速相关信息",
    0x51: "ATP应用记录3", 0x52: "ATO应用3",
    0x54: "ATO-TMS-苏州6",
    0x5B: "ATO2平台记录", 0x5C: "ATO1平台记录",
    0x5D: "ATO2故障", 0x5E: "ATO2运行",
    0x5F: "ATP测速相关信息", 0x99: "CCOV线程记录",
    0x01: "VOBC至AOM红网", 0x02: "VOBC至AOM蓝网",
    0x08: "TIAS至AOM红网", 0x0D: "AOM应用",
    0x0F: "AOM1平台记录", 0x10: "AOM2平台记录",
    0x12: "CSB运行信息", 0x13: "新CSB运行信息",
    0x19: "TIAS至AOM蓝网", 0x1C: "TRDP应用",
}

# 系统名称 → 帧标识符（反查）
LABEL_MAP_REVERSE = {v: k for k, v in FRAME_LABEL_MAP.items()}

# 板卡与系统对应关系
BOARD_SYSTEMS = {
    "CCOV板卡": [
        "红网CCOV", "蓝网CCOV", "通信板1", "通信板2",
        "ATO故障", "ATO应用3", "ATO应用", "ATP应用故障",
        "ATP应用记录3", "ATO-TMS-苏州6", "ATP应用",
        "A机平台", "B机平台", "C机平台",
        "ATO2故障", "ATO1平台记录", "ATO2平台记录",
    ],
    "CSB板卡": [
        "AOM应用", "AOM1平台记录", "AOM2平台记录",
        "CSB运行信息", "新CSB运行信息",
    ],
}

# 所有可解析系统
ALL_PARSEABLE_SYSTEMS = [
    "红网CCOV", "蓝网CCOV", "通信板1", "通信板2",
    "MMI", "ATO故障", "ATO应用3", "ATO应用", "ATP应用故障",
    "ATP应用记录3", "ATO-TMS-苏州6", "ATP应用",
    "A机平台", "B机平台", "C机平台",
    "ATO2故障", "ATO1平台记录", "ATO2平台记录",
    "AOM应用", "AOM1平台记录", "AOM2平台记录",
    "CSB运行信息", "新CSB运行信息",
    "CCOV线程记录", "TRDP应用",
    "TIAS至AOM红网", "TIAS至AOM蓝网",
    "VOBC至AOM红网", "VOBC至AOM蓝网",
]


# ============================================================
# 帧索引构建 — 扫描 mmap，只记录位置和标签
# ============================================================
def build_frame_index(mm: mmap.mmap) -> list:
    """
    扫描 mmap 映射的二进制数据，构建帧索引。
    返回: [(offset, length, label), ...]
    每项只记录帧在文件中的偏移、长度和帧标识符，不切片不拷贝。
    """
    index = []
    offset = 0
    total_len = len(mm)
    invalid_len = FRAME_HEAD_CONFIG["无效帧固定长度"]
    len_start = FRAME_HEAD_CONFIG["帧长度起始字节索引"]
    len_bytes = FRAME_HEAD_CONFIG["帧长度占用字节数"]
    flag_start = FRAME_HEAD_CONFIG["正常冗余起始字节索引"]
    label_start = FRAME_HEAD_CONFIG["帧标识符起始字节索引"]

    while offset < total_len - 1:
        if offset + 2 > total_len:
            break

        # 读取帧长度（大端序）
        frame_len = struct.unpack(">H", mm[offset + len_start:offset + len_start + len_bytes])[0]

        # 验证：只收录正常帧(0x55)，冗余帧(0xAA)跳过
        is_normal = (offset + flag_start < total_len
                     and mm[offset + flag_start] == 0x55)
        is_redundant = (offset + flag_start < total_len
                        and mm[offset + flag_start] == 0xAA)

        if (is_normal or is_redundant) and frame_len > 0:
            full_len = frame_len + len_bytes  # 帧长度字段不含自身
            if offset + full_len > total_len:
                break

            if is_normal:
                # 只收录正常帧到索引
                label = mm[offset + label_start]
                index.append((offset, full_len, label))
            offset += full_len
        else:
            offset += invalid_len

    return index


def detect_systems_from_index(index: list) -> Counter:
    """从帧索引检测包含哪些系统（只统计正常帧 label）"""
    sys_counter = Counter()
    for _, _, label in index:
        sys_name = FRAME_LABEL_MAP.get(label)
        if sys_name:
            sys_counter[sys_name] += 1
    return sys_counter


def group_detected(detected: Counter) -> dict:
    """按板卡分组检测结果"""
    grouped = {}
    for board_name, systems in BOARD_SYSTEMS.items():
        found = []
        for s in systems:
            count = detected.get(s, 0)
            if count > 0:
                found.append({"name": s, "count": count})
        if found:
            grouped[board_name] = found

    # 其他系统
    other = []
    for s, c in detected.most_common():
        if not any(s in sys_list for sys_list in BOARD_SYSTEMS.values()):
            other.append({"name": s, "count": c})
    if other:
        grouped["其他"] = other

    return grouped


# ============================================================
# 数据解析引擎
# ============================================================
class DataParser:
    def __init__(self, config_dir=None):
        self.configs = {}
        if config_dir is None:
            project_root = Path(__file__).parent.parent
            config_dir = project_root / "config" / "data_configuration_file" / "LCF_510_28.0.15"
        self.config_dir = Path(config_dir)
        self._load_configs()

    def _load_configs(self):
        for sys_name in ALL_PARSEABLE_SYSTEMS:
            json_path = self.config_dir / (sys_name + ".json")
            if json_path.exists():
                with open(json_path, "r", encoding="utf-8") as f:
                    self.configs[sys_name] = json.load(f)

    def available_systems(self) -> list:
        return list(self.configs.keys())

    # ----------------------------------------------------------
    # 数值转换工具
    # ----------------------------------------------------------
    @staticmethod
    def _bytes_to_uint(data: bytes) -> int:
        value = 0
        for b in data:
            value = (value << 8) | b
        return value

    @staticmethod
    def _bytes_to_int(data: bytes) -> int:
        value = DataParser._bytes_to_uint(data)
        bit_len = len(data) * 8
        if bit_len > 0 and value >= (1 << (bit_len - 1)):
            value -= (1 << bit_len)
        return value

    @staticmethod
    def _decode_event(raw_value_str: str, event_explain: str) -> str:
        if not event_explain:
            return raw_value_str
        try:
            raw_val = int(float(raw_value_str))
        except (ValueError, TypeError):
            return raw_value_str
        for item in event_explain.split("#"):
            if ":" in item:
                k, v = item.split(":", 1)
                try:
                    if int(k) == raw_val:
                        return v
                except ValueError:
                    continue
        return raw_value_str

    @staticmethod
    def _sanitize(s: str) -> str:
        s = s.replace(chr(0xFFFD), "")
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)

    # ----------------------------------------------------------
    # 字段值解析
    # ----------------------------------------------------------
    def _parse_bytes_value(self, raw: bytes, data_manage: str, event_explain: str) -> str:
        byte_len = len(raw)
        if data_manage == "时间格式":
            if byte_len == 8:
                return self._sanitize(raw.decode("ascii", errors="replace").replace(".", ":"))
            elif byte_len == 6:
                s = raw.decode("ascii", errors="replace")
                return self._sanitize(s[0:2] + ":" + s[2:4] + ":" + s[4:6])
            return raw.hex()
        elif data_manage == "普通文本":
            try:
                val = raw.decode("ascii", errors="replace").strip()
                if val.count(chr(0xFFFD)) > len(val) // 2:
                    return "0x" + format(self._bytes_to_uint(raw), "X") if raw else ""
                return self._sanitize(val)
            except Exception:
                return raw.hex()
        elif data_manage == "无符号数":
            value = str(self._bytes_to_uint(raw))
            return self._decode_event(value, event_explain)
        elif data_manage == "有符号数":
            value = str(self._bytes_to_int(raw))
            return self._decode_event(value, event_explain)
        elif data_manage == "时间格式_UTC":
            seconds = self._bytes_to_uint(raw)
            if seconds != 0xFFFFFFFF and byte_len == 4:
                dt = datetime(1999, 1, 1) + timedelta(seconds=seconds)
                return dt.strftime("%H:%M:%S")
            return "0x%X" % seconds
        elif data_manage == "时间格式_UTC_Add8H":
            seconds = self._bytes_to_uint(raw)
            if seconds != 0xFFFFFFFF and byte_len == 4:
                dt = datetime(1999, 1, 1) + timedelta(seconds=seconds, hours=8)
                return dt.strftime("%H:%M:%S")
            return "0x%X" % seconds
        elif data_manage == "小数":
            if byte_len >= 4:
                try:
                    return str(struct.unpack(">f", raw)[0])
                except Exception:
                    return str(self._bytes_to_uint(raw))
            return str(self._bytes_to_uint(raw))
        else:
            val = self._bytes_to_uint(raw)
            return "0x%X" % val if val else "0x0"

    def _parse_bits_value(self, cur_byte: int, bit_offset: int, bit_length: int,
                          data_manage: str, event_explain: str) -> str:
        if bit_length <= 0 or bit_offset + bit_length > 8:
            return "0"
        shifted = (cur_byte << (8 - bit_offset - bit_length)) & 0xFF
        extracted = shifted >> (8 - bit_length)

        if data_manage == "普通文本":
            return format(extracted, "0" + str(bit_length) + "b")
        elif data_manage == "数组":
            return "0x%X" % extracted
        else:
            value = str(extracted)
            return self._decode_event(value, event_explain)

    # ----------------------------------------------------------
    # 单帧解析
    # ----------------------------------------------------------
    def parse_frame(self, frame: bytes, system_name: str) -> dict:
        """解析单帧，返回 OrderedDict"""
        if system_name not in self.configs:
            return {}

        fields = self.configs[system_name]
        result = OrderedDict()

        cur_byte_offset = 0
        cur_bit_offset = 0
        group_name = ""
        group_parts = []

        i = 0
        while i < len(fields):
            f = fields[i]
            name = f.get("名称", "")
            data_type = f.get("数据类型", "")
            group_relation = f.get("组合关系", "无")
            is_reserved = (name in ("预留", "保留"))
            is_var = f.get("是否变化块长度") == "可变"

            # 组合名
            if group_relation == "组合":
                if group_name and group_parts:
                    result[group_name] = "|".join(group_parts)
                elif group_name:
                    result[group_name] = "无"
                group_name = name
                group_parts = []
                i += 1
                continue

            # Bytes 字段
            if data_type == "Bytes":
                byte_len = int(f["字节长度"]) if f.get("字节长度") else 0
                if byte_len <= 0:
                    i += 1
                    continue

                if cur_bit_offset > 0:
                    cur_bit_offset = 0
                    cur_byte_offset += 1

                explicit_offset = f.get("字节偏移量")
                if explicit_offset and str(explicit_offset).strip():
                    cur_byte_offset = int(explicit_offset)

                if cur_byte_offset + byte_len <= len(frame):
                    raw = frame[cur_byte_offset:cur_byte_offset + byte_len]
                    data_manage = f.get("数据处理", "无符号数")
                    event_explain = f.get("事件说明", "")
                    value = self._parse_bytes_value(raw, data_manage, event_explain)
                else:
                    value = None

                if not is_reserved and value is not None:
                    result[name] = value

                cur_byte_offset += byte_len

                # 可变长度字段
                if is_var and value is not None:
                    try:
                        var_count = int(float(value))
                    except (ValueError, TypeError):
                        var_count = 0
                    len_block = int(f["块长度"]) if f.get("块长度") else 0

                    if var_count > 0 and len_block > 0:
                        i += 1
                        var_fields = []
                        while i < len(fields):
                            vf = fields[i]
                            vr = vf.get("组合关系", "无")
                            vdt = vf.get("数据类型", "")
                            if vdt == "Bits" and vr in ("开始", "中间", "结束"):
                                var_fields.append(vf)
                                if vr == "结束":
                                    i += 1
                                    break
                            elif vdt == "" and vr == "组合":
                                i += 1
                                continue
                            else:
                                break
                            i += 1

                        for vi in range(var_count):
                            temp_bit_off = 0
                            for vf in var_fields:
                                vn = vf.get("名称", "")
                                vb_off = int(vf.get("位偏移量", 0)) if vf.get("位偏移量") else 0
                                vb_len = int(vf.get("位长度", 0)) if vf.get("位长度") else 0
                                vdm = vf.get("数据处理", "无符号数")
                                ve = vf.get("事件说明", "")

                                if cur_byte_offset < len(frame) and vb_len > 0:
                                    val = self._parse_bits_value(
                                        frame[cur_byte_offset], vb_off, vb_len, vdm, ve)
                                    if vn not in ("预留", "保留"):
                                        result[vn + str(vi)] = val

                                temp_bit_off += vb_len
                                if temp_bit_off >= 8:
                                    temp_bit_off = 0
                                    cur_byte_offset += 1
                        continue

            # Bits 字段
            elif data_type == "Bits":
                bit_len = int(f["位长度"]) if f.get("位长度") else 0
                bit_off = int(f["位偏移量"]) if f.get("位偏移量") else 0
                if bit_len <= 0:
                    i += 1
                    continue

                if cur_byte_offset < len(frame):
                    data_manage = f.get("数据处理", "无符号数")
                    event_explain = f.get("事件说明", "")
                    value = self._parse_bits_value(
                        frame[cur_byte_offset], bit_off, bit_len, data_manage, event_explain)

                    if not is_reserved:
                        result[name] = value
                        if group_relation in ("开始", "中间", "结束") and group_name:
                            if value not in ("否", "0", "") and event_explain:
                                if "1:是" in event_explain:
                                    group_parts.append(name)

                    if group_relation == "结束" and group_name:
                        result[group_name] = "|".join(group_parts) if group_parts else "无"
                        group_name = ""
                        group_parts = []

                cur_bit_offset += bit_len
                if cur_bit_offset >= 8:
                    cur_bit_offset = 0
                    cur_byte_offset += 1

            i += 1

        if group_name and group_parts:
            result[group_name] = "|".join(group_parts)
        elif group_name:
            result[group_name] = "无"

        return result

    # ----------------------------------------------------------
    # 分页解析：从帧索引按需解析（支持多 mmap）
    # ----------------------------------------------------------
    def parse_page(self, mmaps: list, index: list, system_name: str,
                   page: int = 1, page_size: int = 10000) -> dict:
        """
        按需分页解析指定系统的帧。
        mmaps: mmap 对象列表
        index: [(mmap_idx, offset, length, label), ...]
        返回: {"columns": [...], "total": N, "page": N, "pages": N, "data": [...]}
        """
        if system_name not in self.configs:
            return {"columns": [], "total": 0, "page": page, "pages": 0, "data": []}

        target_label = LABEL_MAP_REVERSE.get(system_name)
        if target_label is None:
            return {"columns": [], "total": 0, "page": page, "pages": 0, "data": []}

        # 筛出该系统的帧索引
        hits = [(midx, off, ln) for midx, off, ln, lbl in index if lbl == target_label]

        total = len(hits)
        pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = min(start + page_size, total)
        page_hits = hits[start:end]

        # 逐帧解析
        results = []
        columns = []
        seen_cols = set()
        for midx, off, ln in page_hits:
            frame = bytes(mmaps[midx][off:off + ln])  # mmap切片 → bytes
            record = self.parse_frame(frame, system_name)
            if record:
                record["__mmap_idx__"] = midx
                record["__frame_offset__"] = off
                record["__frame_length__"] = ln
                results.append(record)
                # 收集列名（取前100条采样）
                if len(columns) < 200:
                    for k in record.keys():
                        if k not in seen_cols:
                            columns.append(k)
                            seen_cols.add(k)

        # 排序列：时间优先
        priority_cols = ["时间", "序列号", "系统"]
        ordered_cols = []
        for p in priority_cols:
            if p in seen_cols:
                ordered_cols.append(p)
        for c in columns:
            if c not in ordered_cols:
                ordered_cols.append(c)

        return {
            "columns": ordered_cols,
            "total": total,
            "page": page,
            "pages": pages,
            "data": results,
        }

    def parse_all_for_system(self, mmaps: list, index: list, system_name: str) -> list:
        """
        解析指定系统的全部帧（用于导出等场景）。
        返回: [OrderedDict, ...]
        """
        if system_name not in self.configs:
            return []

        target_label = LABEL_MAP_REVERSE.get(system_name)
        if target_label is None:
            return []

        hits = [(midx, off, ln) for midx, off, ln, lbl in index if lbl == target_label]
        results = []
        for midx, off, ln in hits:
            frame = bytes(mmaps[midx][off:off + ln])
            record = self.parse_frame(frame, system_name)
            if record:
                results.append(record)
        return results
