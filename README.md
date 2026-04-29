# PDF 签名工具 🔏

一个简洁的 Windows 桌面 PDF 签名工具。

## 功能

- 📄 拖入 PDF 或 Word 文档（Word 自动转 PDF）
- ✍️ 在 PDF 上放置签名（拖拽、缩放、旋转）
- 🖼️ 自动去除签名图片白底（白底黑字 → 透明 PNG）
- 📚 签名库管理（保存/删除/复用多个签名）
- 📑 多页 PDF 支持
- 💾 导出新 PDF（默认原名_signed.pdf，可覆盖）
- 🔍 鼠标滚轮 + Ctrl 缩放文档视图

## 安装

### 方式 1：直接下载 .exe（推荐）

前往 [Releases](../../releases) 下载最新版本的 .exe 文件，双击运行即可。

### 方式 2：从源码运行

```bash
# 克隆仓库
git clone https://github.com/dadaniya99/pdf-signer-tool.git
cd pdf-signer-tool

# 安装依赖
pip install -r requirements.txt

# 运行
python src/app.py
```

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| Ctrl+O | 打开文件 |
| Ctrl+S | 保存 PDF |
| Ctrl+Delete | 删除选中签名 |
| R | 旋转签名 90° |
| Delete | 删除选中签名 |

## 依赖

- Python 3.7+
- PyQt6
- PyMuPDF (fitz)
- Pillow (PIL)
- python-docx

## 许可证

MIT
