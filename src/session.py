"""
会话管理 — 管理文件 mmap 映射和帧索引的生命周期
"""
import mmap
import uuid
from pathlib import Path
from collections import Counter
from parser import build_frame_index, detect_systems_from_index, group_detected


class Session:
    """单个上传会话，持有 mmap 对象和帧索引"""

    def __init__(self, file_paths: list[str]):
        self.session_id = uuid.uuid4().hex[:8]
        self.file_paths = file_paths  # 原始文件路径列表
        self.mmaps: list[mmap.mmap] = []  # mmap 对象列表（多文件）
        self._file_objs: list = []  # 对应的文件对象，用于关闭
        self.index: list[tuple] = []  # 合并后的帧索引
        self.detected: Counter = Counter()  # 检测到的系统统计
        self.file_names: list[str] = []  # 文件名列表
        self._open()

    def _open(self):
        """打开所有文件的 mmap 并合并帧索引"""
        for path in self.file_paths:
            p = Path(path)
            if not p.exists():
                continue

            f = open(p, "rb")
            try:
                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            except ValueError:
                # 空文件
                f.close()
                continue

            file_index = build_frame_index(mm)
            detected = detect_systems_from_index(file_index)

            # 如果有多个文件，需要给后续文件的 offset 加上前一个文件的大小
            # 这里我们用 (mmap_index, offset_in_file, length, label) 四元组
            mmap_idx = len(self.mmaps)
            for off, ln, lbl in file_index:
                self.index.append((mmap_idx, off, ln, lbl))

            self.mmaps.append(mm)
            self._file_objs.append(f)  # 保存文件句柄，mmap 依赖它保持打开
            self.detected += detected
            self.file_names.append(p.name)

    def get_frame(self, mmap_idx: int, offset: int, length: int) -> bytes:
        """从指定 mmap 中取帧数据"""
        return bytes(self.mmaps[mmap_idx][offset:offset + length])

    def close(self):
        """关闭所有 mmap 和文件句柄"""
        for mm in self.mmaps:
            try:
                mm.close()
            except Exception:
                pass
        for f in self._file_objs:
            try:
                f.close()
            except Exception:
                pass
        self.mmaps.clear()
        self._file_objs.clear()
        self.index.clear()


class SessionManager:
    """管理所有会话"""

    def __init__(self):
        self.sessions: dict[str, Session] = {}

    def create(self, file_paths: list[str]) -> Session:
        """创建新会话"""
        session = Session(file_paths)
        self.sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session:
        if session_id not in self.sessions:
            raise KeyError(f"会话不存在: {session_id}")
        return self.sessions[session_id]

    def remove(self, session_id: str):
        if session_id in self.sessions:
            self.sessions[session_id].close()
            del self.sessions[session_id]

    def cleanup_all(self):
        """清理所有会话"""
        for sid in list(self.sessions.keys()):
            self.remove(sid)
