# -*- mode: python ; coding: utf-8 -*-
"""
Metin Atölyesi — PyInstaller Spec
Kullanım:
  build_exe.bat
  veya:
  pyinstaller MetinAtolyesi.spec
"""

from pathlib import Path
import sys

ROOT = Path(SPECPATH)   # D:\METİN ATÖLYESİ

# ---------------------------------------------------------------------------
# Tessdata — Arapça/Osmanlıca/Türkçe dil paketleri
# ---------------------------------------------------------------------------
tessdata_user = Path.home() / ".metin_atolyesi" / "tessdata"
tessdata_app  = ROOT / "tessdata"

tessdata_src = tessdata_user if tessdata_user.exists() else tessdata_app

datas = [
    # PowerShell araçları (Windows OCR + PDF render)
    (str(ROOT / "tools"), "tools"),
]

# Tessdata dosyaları
if tessdata_src.exists():
    for td_file in tessdata_src.glob("*.traineddata"):
        datas.append((str(td_file), "tessdata"))

# ---------------------------------------------------------------------------
# Gizli importlar — dinamik import edilen modüller
# ---------------------------------------------------------------------------
hidden_imports = [
    # tkinter (bazen atlanır)
    "tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox",
    "tkinter.colorchooser", "tkinter.font", "tkinter.simpledialog",
    "tkinter.scrolledtext",
    # PIL
    "PIL", "PIL.Image", "PIL.ImageTk", "PIL.ImageDraw",
    "PIL.ImageEnhance", "PIL.ImageOps", "PIL.ImageFilter",
    # PDF
    "fitz",                    # PyMuPDF
    "pypdfium2",
    "pypdf", "pypdf.errors",
    # OCR
    "pytesseract",
    "rapidocr_onnxruntime",
    # Anthropic / Claude
    "anthropic", "anthropic.types",
    "httpx", "httpcore", "anyio",
    # Network
    "requests", "urllib3", "certifi",
    # Export
    "openpyxl", "openpyxl.styles", "openpyxl.utils",
    "docx", "docx.oxml",
    "reportlab", "reportlab.lib", "reportlab.platypus",
    # Image processing
    "cv2",          # opencv-python
    "numpy",
    "scipy",
    # Metin Atölyesi modülleri (lazy import'lar)
    "metin_atolyesi.core.deskew",
    "metin_atolyesi.core.claude_ocr",
    "metin_atolyesi.core.transkribus_ocr",
    "metin_atolyesi.core.manuscript_library",
    "metin_atolyesi.core.hf_store",
    "metin_atolyesi.core.github_sync",
    "metin_atolyesi.core.sync_store",
    "metin_atolyesi.core.batch_queue",
    "metin_atolyesi.core.classifier",
    "metin_atolyesi.core.searchable_pdf",
    "metin_atolyesi.core.exporters",
    "metin_atolyesi.core.corrections_store",
    "metin_atolyesi.core.text_tools",
    "metin_atolyesi.core.dependencies",
    "metin_atolyesi.ui.manuscript_wizard",
    # XML / JSON
    "xml.etree.ElementTree",
    "json",
    "zlib",
]

# ---------------------------------------------------------------------------
# Hariç tutulanlar — boyutu küçültmek için
# (kullanıcı bunları yüklemişse yine de çalışır; yoksa motor listesinde yok)
# ---------------------------------------------------------------------------
excludes = [
    "easyocr",       # ~2 GB torch gerektiriyor — sistem kurulumundan kullanılır
    "torch",
    "torchvision",
    "torchaudio",
    "transformers",
    "kraken",
    "surya",
    # Kullanılmayan stdlib
    "email.mime",
    "http.server",
    "xmlrpc",
    "unittest",
    "doctest",
    "pdb",
    "profile",
    "cProfile",
    "pstats",
    "tkinter.test",
    # Dev araçları
    "pytest",
    "setuptools",
    "pip",
    "wheel",
    "distutils",
]

# ---------------------------------------------------------------------------
# Analiz
# ---------------------------------------------------------------------------
block_cipher = None

a = Analysis(
    [str(ROOT / "run_app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ---------------------------------------------------------------------------
# Exe (konsol gizli — GUI uygulama)
# ---------------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MetinAtolyesi",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # Konsol penceresi açma
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="metin_atolyesi.ico",   # .ico dosyası varsa açın
    version_file=None,
)

# ---------------------------------------------------------------------------
# Klasör toplama (--onedir modu: hızlı başlangıç)
# ---------------------------------------------------------------------------
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MetinAtolyesi",
)
