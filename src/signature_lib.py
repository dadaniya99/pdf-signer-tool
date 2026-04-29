"""签名库管理 - 保存/加载/删除签名"""
import json
import os
import shutil
import uuid
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass
class SignatureEntry:
    """签名库条目"""
    id: str
    name: str
    image_filename: str
    created_at: str


class SignatureLibrary:
    """签名库管理器"""
    
    LIB_DIR_NAME = "signature_lib"
    INDEX_FILE = "index.json"
    
    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = os.path.join(os.path.expanduser("~"), ".pdf_signer")
        
        self.lib_dir = os.path.join(base_dir, self.LIB_DIR_NAME)
        self.index_path = os.path.join(self.lib_dir, self.INDEX_FILE)
        self._entries: List[SignatureEntry] = []
        
        os.makedirs(self.lib_dir, exist_ok=True)
        self._load()
    
    def _load(self):
        """加载签名库索引"""
        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._entries = [SignatureEntry(**e) for e in data.get('signatures', [])]
            except (json.JSONDecodeError, KeyError):
                self._entries = []
    
    def _save(self):
        """保存签名库索引"""
        data = {
            'signatures': [asdict(e) for e in self._entries]
        }
        with open(self.index_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def add(self, name: str, image_data: bytes) -> SignatureEntry:
        """添加签名到库中"""
        sig_id = uuid.uuid4().hex[:12]
        filename = f"sig_{sig_id}.png"
        filepath = os.path.join(self.lib_dir, filename)
        
        with open(filepath, 'wb') as f:
            f.write(image_data)
        
        entry = SignatureEntry(
            id=sig_id,
            name=name,
            image_filename=filename,
            created_at=datetime.now().isoformat()
        )
        self._entries.append(entry)
        self._save()
        return entry
    
    def remove(self, sig_id: str) -> bool:
        """从库中删除签名"""
        for i, e in enumerate(self._entries):
            if e.id == sig_id:
                filepath = os.path.join(self.lib_dir, e.image_filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
                self._entries.pop(i)
                self._save()
                return True
        return False
    
    def get_image_path(self, sig_id: str) -> Optional[str]:
        """获取签名图片路径"""
        for e in self._entries:
            if e.id == sig_id:
                return os.path.join(self.lib_dir, e.image_filename)
        return None
    
    def get_image_data(self, sig_id: str) -> Optional[bytes]:
        """获取签名图片数据"""
        path = self.get_image_path(sig_id)
        if path and os.path.exists(path):
            with open(path, 'rb') as f:
                return f.read()
        return None
    
    def rename(self, sig_id: str, new_name: str) -> bool:
        """重命名签名"""
        for e in self._entries:
            if e.id == sig_id:
                e.name = new_name
                self._save()
                return True
        return False
    
    @property
    def entries(self) -> List[SignatureEntry]:
        return list(self._entries)
    
    def count(self) -> int:
        return len(self._entries)
