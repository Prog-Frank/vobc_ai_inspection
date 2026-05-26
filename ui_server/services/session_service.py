"""
会话服务模块
- 文件保存（同步）
- 会话创建
- 上传/加载的结果封装
"""
import os
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class SessionService:
    def __init__(self, session_mgr, project_root: Path, upload_dir: Path):
        self.session_mgr = session_mgr
        self.project_root = Path(project_root)
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def cleanup_upload_dir(self):
        for old_file in self.upload_dir.iterdir():
            try:
                old_file.unlink()
            except Exception:
                pass
        self.session_mgr.cleanup_all()

    def save_upload_file(self, filename: str, content: bytes) -> Path:
        save_path = self.upload_dir / filename
        if save_path.exists():
            stem = save_path.stem
            suffix = save_path.suffix
            counter = 1
            while save_path.exists():
                save_path = self.upload_dir / f"{stem}_{counter}{suffix}"
                counter += 1
        with open(save_path, "wb") as f:
            f.write(content)
        return save_path

    def create_session_from_paths(self, saved_paths: List[str], saved_names: List[str]):
        session = self.session_mgr.create(saved_paths)
        if not session.index:
            self.session_mgr.remove(session.session_id)
            return None

        from parser import group_detected

        grouped = group_detected(session.detected)
        total_normal = sum(session.detected.values())

        return {
            "session_id": session.session_id,
            "total_frames": len(session.index),
            "total_normal": total_normal,
            "detected": grouped,
            "file_name": ", ".join(saved_names),
            "file_count": len(saved_names),
        }

    def load_local_files(self, paths: List[str]):
        session = self.session_mgr.create(paths)
        if not session.index:
            self.session_mgr.remove(session.session_id)
            return None

        from parser import group_detected

        grouped = group_detected(session.detected)
        total_normal = sum(session.detected.values())

        return {
            "session_id": session.session_id,
            "total_frames": len(session.index),
            "total_normal": total_normal,
            "detected": grouped,
            "file_name": ", ".join(session.file_names),
            "file_count": len(session.file_names),
        }
