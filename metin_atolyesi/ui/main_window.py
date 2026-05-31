from __future__ import annotations

import shutil
import tempfile
import threading
import tkinter as tk
import os
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import Image, ImageTk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    BaseTk = TkinterDnD.Tk
except Exception:
    DND_FILES = None
    BaseTk = tk.Tk

from metin_atolyesi import APP_DISPLAY_NAME
from metin_atolyesi.core.ai_tools import local_ai_available, run_local_ai
from metin_atolyesi.core import exporters, pdf_tools
from metin_atolyesi.core.corrections_store import CorrectionsStore
from metin_atolyesi.core.dependencies import collect_status, missing_dependency_text
from metin_atolyesi.core.models import PageRecord, Project, VocabularyItem
from metin_atolyesi.core.ocr import images_from_pdf, ocr_image, preprocess_image, run_multi_mode_ocr
from metin_atolyesi.core.project_store import EXPORTS_DIR, create_project, load_project, save_project
from metin_atolyesi.core.searchable_pdf import create_searchable_pdf, extract_text_layer, has_text_layer
from metin_atolyesi.core.text_tools import apply_command, extract_vocabulary, find_suspicious_words
from metin_atolyesi.ui.ocr_panel import OcrPanel


class MainWindow(BaseTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_DISPLAY_NAME)
        self.geometry("1320x820")
        self.minsize(980, 620)
        self.project: Project = create_project("Metin Atolyesi")
        self.dirty = False
        self.preview_image: ImageTk.PhotoImage | None = None
        self.preview_zoom = 1.0
        self.pan_start: tuple[int, int] | None = None
        self.preview_original: Image.Image | None = None
        self.preview_pages: list[Path] = []
        self.preview_page_index = 0
        self.last_saved_pdf: Path | None = None
        self.fit_preview_to_window = True
        self.preview_edit_mode = False
        self.preview_drag_item = None
        self.preview_drag_points: list[tuple[int, int]] = []
        self.preview_canvas_items: list[int] = []
        self.preview_redo_items: list[int] = []
        self.crop_select_mode = False
        self.preview_display_size: tuple[int, int] = (0, 0)
        self.corrections: CorrectionsStore = CorrectionsStore()
        self.ocr_corrections: dict[str, str] = {}
        self._ocr_thread: threading.Thread | None = None
        self._autosave_id: str | None = None
        self.ocr_engine_var = tk.StringVar(value="otomatik")
        self.ocr_lang_var = tk.StringVar(value="tur+eng")
        self.ocr_preprocess_var = tk.StringVar(value="çoklu deneme")
        self.ocr_deskew_var = tk.BooleanVar(value=False)
        self.ocr_confidence_var = tk.BooleanVar(value=False)
        self.ocr_scope_var = tk.StringVar(value="geçerli sayfa")
        self.ocr_reference_text = ""
        self.ocr_dictionary: set[str] = set()
        self.double_split_order_var = tk.StringVar(value="sağ sayfa önce")
        # Mod yönetimi ve son açılanlar
        self.recent_files: list[str] = []
        self._current_mode: str = "normal"
        self._config_path: Path = Path.home() / ".metin_atolyesi_config.json"
        self._mode_label_var = tk.StringVar(value="")
        self._pdf_preview_image: ImageTk.PhotoImage | None = None
        self._pdf_preview_pages: list[Path] = []
        self._pdf_preview_page_index: int = 0
        self._pdf_preview_zoom: float = 1.0
        self._load_recent_files()
        self._build_style()
        self._build_toolbar()
        self._build_layout()
        self._bind_events()
        self._setup_drag_drop()
        self._refresh_all()
        self._start_autosave()

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TButton", padding=(8, 5))
        style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Status.TLabel", foreground="#666", font=("Segoe UI", 9))

    # ── Araç çubuğu renk sabitleri ────────────────────────────────────────
    _TB_BG  = "#1e1e2e"   # araç çubuğu arkaplanı
    _TB_BTN = "#2a2a40"   # normal düğme arkaplanı
    _TB_ACT = "#0d6efd"   # aktif mod düğmesi (mavi)
    _TB_FG  = "#d8daf0"   # yazı rengi
    _TB_SEP = "#3a3a58"   # ince ayırıcı rengi

    def _build_toolbar(self) -> None:
        """Koyu navigasyon araç çubuğu: [≡ Dosya ▾] | [🔍 OCR] | [📄 PDF İşlemleri]"""
        bar = tk.Frame(self, bg=self._TB_BG)
        bar.pack(fill=tk.X, side=tk.TOP)

        # Uygulama adı / logo
        tk.Label(
            bar, text="  📚 Metin Atölyesi",
            bg=self._TB_BG, fg=self._TB_FG,
            font=("Segoe UI", 10, "bold"), pady=10,
        ).pack(side=tk.LEFT)

        tk.Frame(bar, bg=self._TB_SEP, width=1).pack(
            side=tk.LEFT, fill=tk.Y, pady=5, padx=4)

        # Dosya hamburger menü düğmesi
        self._dosya_mb = tk.Menubutton(
            bar, text="  ≡  Dosya  ",
            bg=self._TB_BTN, fg=self._TB_FG,
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT, pady=10,
            activebackground=self._TB_SEP, activeforeground=self._TB_FG,
            cursor="hand2", direction="below",
        )
        self._dosya_mb.pack(side=tk.LEFT, padx=1)
        self._build_dosya_menu(self._dosya_mb)

        tk.Frame(bar, bg=self._TB_SEP, width=1).pack(
            side=tk.LEFT, fill=tk.Y, pady=5, padx=4)

        # OCR modu düğmesi (varsayılan aktif)
        self._ocr_nav_btn = tk.Button(
            bar, text="  🔍  OCR  ",
            bg=self._TB_ACT, fg="white",
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT, pady=10,
            activebackground="#0a58ca", activeforeground="white",
            bd=0, cursor="hand2",
            command=lambda: self._set_mode("ocr"),
        )
        self._ocr_nav_btn.pack(side=tk.LEFT, padx=1)

        # PDF İşlemleri modu düğmesi
        self._pdf_nav_btn = tk.Button(
            bar, text="  📄  PDF İşlemleri  ",
            bg=self._TB_BTN, fg=self._TB_FG,
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT, pady=10,
            activebackground=self._TB_SEP, activeforeground=self._TB_FG,
            bd=0, cursor="hand2",
            command=lambda: self._set_mode("pdf"),
        )
        self._pdf_nav_btn.pack(side=tk.LEFT, padx=1)

    def _build_dosya_menu(self, mb: tk.Menubutton) -> None:
        """Dosya hamburger açılır menüsünü oluşturur."""
        menu = tk.Menu(
            mb, tearoff=0,
            bg="#252537", fg=self._TB_FG,
            activebackground=self._TB_ACT, activeforeground="white",
            font=("Segoe UI", 10),
            bd=0, relief=tk.FLAT,
        )
        mb.configure(menu=menu)

        menu.add_command(label="  📂  Yeni Proje",              command=self.new_project)
        menu.add_command(label="  📁  Proje Aç",                command=self.open_project)
        menu.add_command(label="  💾  Kaydet          Ctrl+S",  command=self.save)
        menu.add_separator()
        menu.add_command(label="  📄  PDF / Görsel Yükle",      command=self.load_source)
        menu.add_command(label="  📑  Toplu Yükle",             command=self.load_sources_dialog)
        menu.add_separator()
        self._recent_menu = tk.Menu(
            menu, tearoff=0,
            bg="#252537", fg=self._TB_FG,
            activebackground=self._TB_ACT, activeforeground="white",
            font=("Segoe UI", 10),
        )
        menu.add_cascade(label="  🕐  Son Açılanlar  ▸", menu=self._recent_menu)
        self._refresh_recent_menu()
        menu.add_separator()
        menu.add_command(label="  📝  Word Aktar",               command=self.export_word)
        menu.add_command(label="  📊  Excel Aktar",              command=self.export_excel)
        menu.add_command(label="  📄  Metin Aktar",              command=self.export_txt)
        menu.add_command(label="  🔍  Aranabilir PDF Oluştur",   command=self.export_searchable_pdf)
        menu.add_separator()
        menu.add_separator()
        menu.add_command(label="  ✍  El Yazması Öğret",         command=self.open_manuscript_wizard)
        menu.add_command(label="  📚  Yazma Kütüphanesi",        command=self.open_manuscript_library)
        menu.add_separator()
        menu.add_command(label="  ⚙  Bağımlılıkları Denetle",   command=self.show_dependencies)
        menu.add_command(label="  ⚡  Claude API Ayarları",      command=self.open_claude_settings)
        menu.add_command(label="  🤗  HuggingFace Ayarları",     command=self.open_hf_settings)
        menu.add_separator()
        menu.add_command(label="  ✖  Çıkış",                    command=self.on_close)

    def _build_layout(self) -> None:
        self.batch_var = tk.IntVar(value=self.project.batch_size)

        root = ttk.Frame(self, padding=8)
        root.pack(fill=tk.BOTH, expand=True)

        # ── Durum çubuğu (en altta sabitlenir) ───────────────────────────
        bottom = ttk.Frame(root)
        bottom.pack(fill=tk.X, pady=(4, 0), side=tk.BOTTOM)
        self.status_var = tk.StringVar(value="Hazır")
        ttk.Label(bottom, textvariable=self.status_var, style="Status.TLabel").pack(side=tk.LEFT)

        # ── İki mod çerçevesi (aynı alanda; biri görünür) ────────────────
        self._classic_frame = ttk.Frame(root)   # klasik mod (dahili, menüde yok)
        self._ocr_frame     = ttk.Frame(root)
        self._pdf_frame     = ttk.Frame(root)

        self._build_classic_layout(self._classic_frame)
        self._build_ocr_frame_content(self._ocr_frame)
        self._build_pdf_frame_content(self._pdf_frame)

        # OCR moduyla başla
        self._set_mode("ocr")

        # GitHub veri reposu — arka planda pull
        self.after(2000, self._startup_sync)

    # -----------------------------------------------------------------------
    # Üç mod çerçevesi inşa metodları
    # -----------------------------------------------------------------------

    def _build_classic_layout(self, parent: ttk.Frame) -> None:
        """Normal mod — sol PDF önizleme + sağ not defteri."""
        self.paned = ttk.Panedwindow(parent, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True)

        left  = ttk.Frame(self.paned)
        right = ttk.Frame(self.paned)
        self.paned.add(left,  weight=1)
        self.paned.add(right, weight=2)

        self._build_left(left)
        self._build_right(right)

    def _build_ocr_frame_content(self, parent: ttk.Frame) -> None:
        """OCR modu — OcrPanel pencerenin tamamını kaplar."""
        self.ocr_panel = OcrPanel(
            parent,
            project=self.project,
            corrections=self.corrections,
            on_text_saved=self._on_ocr_text_saved,
        )
        self.ocr_panel.pack(fill=tk.BOTH, expand=True)

    def _build_pdf_frame_content(self, parent: ttk.Frame) -> None:
        """PDF İşlemleri modu — sol önizleme + sağ araçlar."""
        # ── Üst başlık çubuğu ─────────────────────────────────────────────
        header = ttk.Frame(parent, padding=(0, 0, 0, 6))
        header.pack(fill=tk.X)
        ttk.Label(header, text="📄 PDF İşlemleri", style="Header.TLabel").pack(side=tk.LEFT)
        btn_row = ttk.Frame(header)
        btn_row.pack(side=tk.RIGHT)
        ttk.Button(btn_row, text="Aç", command=self.load_source).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="Son Açılanlar ▾", command=self._show_recent_pdf_menu).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="Dosyada Kaydet", command=self.save_pdf_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="Farklı Kaydet", command=self.save_pdf_as_dialog).pack(side=tk.LEFT, padx=2)

        # ── Ana bölme: sol önizleme + sağ araçlar ─────────────────────────
        main_paned = ttk.Panedwindow(parent, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True)

        preview_frame = ttk.Frame(main_paned)
        tools_frame   = ttk.Frame(main_paned)
        main_paned.add(preview_frame, weight=1)
        main_paned.add(tools_frame,   weight=2)

        # Sol: PDF önizleme
        ttk.Label(preview_frame, text="Önizleme").pack(anchor=tk.W)
        self.pdf_preview = tk.Canvas(
            preview_frame, bg="#f4f4f4",
            highlightthickness=1, highlightbackground="#ccc",
        )
        self.pdf_preview.pack(fill=tk.BOTH, expand=True)
        nav = ttk.Frame(preview_frame)
        nav.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(nav, text="◀", width=3, command=lambda: self._pdf_preview_nav(-1)).pack(side=tk.LEFT)
        ttk.Button(nav, text="▶", width=3, command=lambda: self._pdf_preview_nav(1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav, text="−", width=3, command=lambda: self._zoom_pdf_preview(0.85)).pack(side=tk.LEFT, padx=(6, 2))
        ttk.Button(nav, text="+", width=3, command=lambda: self._zoom_pdf_preview(1.18)).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav, text="Sığdır", command=self._fit_pdf_preview).pack(side=tk.LEFT, padx=4)

        # Sağ: PDF araçları (mevcut _build_pdf_tab ile doldur)
        self._build_pdf_tab(tools_frame)

    def _set_mode(self, mode: str) -> None:
        """OCR / PDF modları arasında geçiş yapar; araç çubuğunu günceller."""
        # Tüm mod çerçevelerini gizle
        self._classic_frame.pack_forget()
        self._ocr_frame.pack_forget()
        self._pdf_frame.pack_forget()

        self._current_mode = mode

        if mode == "normal":
            self._classic_frame.pack(fill=tk.BOTH, expand=True)
        elif mode == "ocr":
            self._ocr_frame.pack(fill=tk.BOTH, expand=True)
            if hasattr(self, "ocr_panel"):
                self.ocr_panel.set_project(self.project, self.corrections)
                self.after(80, self.ocr_panel.refresh)
        elif mode == "pdf":
            self._pdf_frame.pack(fill=tk.BOTH, expand=True)
            self.after(80, self._refresh_pdf_frame_preview)

        # Araç çubuğu düğmelerini vurgula
        if hasattr(self, "_ocr_nav_btn") and self._ocr_nav_btn:
            self._ocr_nav_btn.configure(
                bg=self._TB_ACT if mode == "ocr" else self._TB_BTN,
                fg="white"      if mode == "ocr" else self._TB_FG,
            )
            self._pdf_nav_btn.configure(
                bg=self._TB_ACT if mode == "pdf" else self._TB_BTN,
                fg="white"      if mode == "pdf" else self._TB_FG,
            )

    def _build_left(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent)
        header.pack(fill=tk.X)
        ttk.Label(header, text="Sayfa / PDF Goruntusu", style="Header.TLabel").pack(side=tk.LEFT)
        self.page_var = tk.StringVar(value="0/0")
        ttk.Label(header, textvariable=self.page_var).pack(side=tk.RIGHT, padx=8)
        nav = ttk.Frame(parent)
        nav.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(nav, text="Önceki Sayfa", command=lambda: self.goto_page(-1)).pack(side=tk.LEFT)
        ttk.Button(nav, text="Sonraki Sayfa", command=lambda: self.goto_page(1)).pack(side=tk.LEFT, padx=6)

        self.preview = tk.Canvas(parent, bg="#f4f4f4", highlightthickness=1, highlightbackground="#ddd")
        self.preview.pack(fill=tk.BOTH, expand=True, pady=6)
        preview_tools = ttk.Frame(parent)
        preview_tools.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(preview_tools, text="-", width=3, command=lambda: self.zoom_preview(0.85)).pack(side=tk.LEFT)
        ttk.Button(preview_tools, text="+", width=3, command=lambda: self.zoom_preview(1.18)).pack(side=tk.LEFT, padx=4)
        ttk.Button(preview_tools, text="Sığdır", width=7, command=self.fit_preview).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(preview_tools, text="✋", width=4, command=self.set_hand_cursor).pack(side=tk.LEFT)

        ttk.Label(parent, text="Ornek okuma / referans bilgi").pack(anchor=tk.W)
        self.examples = tk.Text(parent, height=5, wrap=tk.WORD, undo=True)
        self.examples.pack(fill=tk.X)

    def _build_right(self, parent: ttk.Frame) -> None:
        """Normal mod sağ bölme: Metin, Dizin ve Şüpheli Okumalar sekmeleri.
        OCR ve PDF İşlemleri sekmeleri kaldırıldı — artık tam ekran modları."""
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True)
        self._notebook = notebook

        text_tab    = ttk.Frame(notebook, padding=6)
        vocab_tab   = ttk.Frame(notebook, padding=6)
        suspect_tab = ttk.Frame(notebook, padding=6)
        notebook.add(text_tab,    text="Metin")
        notebook.add(vocab_tab,   text="Dizin / Söz Varlığı")
        notebook.add(suspect_tab, text="Şüpheli Okumalar")

        # ── Metin sekmesi ─────────────────────────────────────────────────
        self.text = tk.Text(text_tab, wrap=tk.WORD, undo=True, font=("Segoe UI", 11))
        self.text.tag_configure("suspicious", foreground="#b00020", background="#ffe5e9")
        self.text.tag_configure("uncertain", foreground="#8a5a00", background="#fff3a3")
        self.text.pack(fill=tk.BOTH, expand=True)
        self.text.bind("<Button-3>", self.show_text_context_menu)

        command_bar = ttk.Frame(text_tab)
        command_bar.pack(fill=tk.X, pady=(6, 0))
        self.command_var = tk.StringVar()
        entry = ttk.Entry(command_bar, textvariable=self.command_var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        entry.bind("<Return>", lambda _e: self.run_command())
        ttk.Button(command_bar, text="Komutu Çalıştır", command=self.run_command).pack(side=tk.LEFT, padx=(6, 0))

        # Mod geçişi araç çubuğuyla yapılıyor (üstteki OCR / PDF İşlemleri düğmeleri)

        # ── Dizin sekmesi ─────────────────────────────────────────────────
        self.vocab = ttk.Treeview(
            vocab_tab,
            columns=("headword", "origin", "meaning", "usage", "suffixes", "location", "note"),
            show="headings",
            height=14,
        )
        for key, label in {
            "headword": "Madde Başı", "origin": "Köken", "meaning": "Anlam",
            "usage": "Kullanım",  "suffixes": "Ek",   "location": "Sayfa/Varak", "note": "Not",
        }.items():
            self.vocab.heading(key, text=label)
            self.vocab.column(key, width=130 if key != "meaning" else 260)
        self.vocab.pack(fill=tk.BOTH, expand=True)
        vocab_buttons = ttk.Frame(vocab_tab)
        vocab_buttons.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(vocab_buttons, text="Satır Ekle", command=self.add_vocab_row).pack(side=tk.LEFT)
        ttk.Button(vocab_buttons, text="Seçileni Sil", command=self.delete_vocab_row).pack(side=tk.LEFT, padx=6)

        # ── Şüpheli Okumalar sekmesi ──────────────────────────────────────
        self.suspicious_list = tk.Listbox(suspect_tab)
        self.suspicious_list.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            suspect_tab,
            text="Sarı/kırmızı işaretlenen kelimeler OCR modunda da vurgulanır.",
        ).pack(anchor=tk.W, pady=(6, 0))

    def _build_pdf_tab(self, parent: ttk.Frame) -> None:
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        content = ttk.Frame(canvas)
        content.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Label(content, text="PDF Düzenleme", style="Header.TLabel").grid(row=0, column=0, columnspan=8, sticky=tk.W, pady=(0, 8))

        self.pdf_pages_var = tk.StringVar()
        self.pdf_output_name_var = tk.StringVar(value="duzenlenmis.pdf")
        self.pdf_split_var = tk.IntVar(value=1)
        self.pdf_dpi_var = tk.IntVar(value=120)
        self.pdf_quality_var = tk.IntVar(value=70)
        self.pdf_rotate_var = tk.IntVar(value=90)
        self.pdf_rotate_direction_var = tk.StringVar(value="sağa 90")
        self.pdf_orientation_var = tk.StringVar(value="dikey")
        self.crop_left_var = tk.DoubleVar(value=0)
        self.crop_top_var = tk.DoubleVar(value=0)
        self.crop_right_var = tk.DoubleVar(value=0)
        self.crop_bottom_var = tk.DoubleVar(value=0)

        self.num_format_var = tk.StringVar(value="{NUM} / {COUNT}")
        self.num_font_var = tk.StringVar(value="Calibri - Regular")
        self.num_size_var = tk.IntVar(value=10)
        self.num_position_var = tk.StringVar(value="alt, orta")
        self.num_angle_var = tk.DoubleVar(value=0)
        self.num_color_var = tk.StringVar(value="#000000")
        self.num_x_var = tk.DoubleVar(value=0)
        self.num_y_var = tk.DoubleVar(value=3)
        self.num_first_page_var = tk.IntVar(value=1)
        self.num_offset_var = tk.IntVar(value=0)
        self.page_number_layout_var = tk.StringVar(value="tek sayfa")

        self.folio_first_side_var = tk.StringVar(value="a")
        self.folio_second_side_var = tk.StringVar(value="b")
        self.folio_per_page_var = tk.StringVar(value="tek varak")
        self.folio_lines_var = tk.IntVar(value=0)

        self.mark_kind_var = tk.StringVar(value="metin")
        self.mark_text_var = tk.StringVar(value="")
        self.mark_x_var = tk.DoubleVar(value=20)
        self.mark_y_var = tk.DoubleVar(value=20)
        self.mark_w_var = tk.DoubleVar(value=50)
        self.mark_h_var = tk.DoubleVar(value=20)
        self.mark_color_var = tk.StringVar(value="#ff0000")
        self.mark_line_var = tk.DoubleVar(value=1.5)
        self.mark_image_path: Path | None = None

        self._build_pdf_tool_cards(content)
        return

        row = 1
        ttk.Label(content, text="Seçili sayfalar").grid(row=row, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(content, textvariable=self.pdf_pages_var, width=22).grid(row=row, column=1, sticky=tk.W, padx=4)
        ttk.Label(content, text="Örn. 1,3-5. Boşsa tüm sayfalar.").grid(row=row, column=2, columnspan=4, sticky=tk.W, padx=4)
        row += 1
        ttk.Label(content, text="Çıktı adı").grid(row=row, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(content, textvariable=self.pdf_output_name_var, width=28).grid(row=row, column=1, columnspan=2, sticky=tk.W, padx=4)
        ttk.Button(content, text="Son Kaydedilen PDF'yi Kullan", command=self.reload_current_pdf).grid(row=row, column=3, sticky=tk.W, padx=4)

        row += 1
        ttk.Separator(content).grid(row=row, column=0, columnspan=8, sticky=tk.EW, pady=8)
        row += 1
        ttk.Label(content, text="Sayfa İşlemleri", style="Header.TLabel").grid(row=row, column=0, columnspan=8, sticky=tk.W)
        row += 1
        ttk.Label(content, text="Her dosyada sayfa").grid(row=row, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Spinbox(content, from_=1, to=200, textvariable=self.pdf_split_var, width=6).grid(row=row, column=1, sticky=tk.W, padx=4)
        ttk.Button(content, text="PDF'yi Böl", command=self.split_pdf_dialog).grid(row=row, column=2, sticky=tk.W, padx=4)
        ttk.Button(content, text="Seçili Sayfaları Dışarı Aktar", command=self.export_selected_pages).grid(row=row, column=3, sticky=tk.W, padx=4)
        ttk.Button(content, text="Seçili Sayfayı Sil / Çıkar", command=self.delete_selected_pages).grid(row=row, column=4, sticky=tk.W, padx=4)
        ttk.Button(content, text="PDFleri Birleştir", command=self.merge_pdfs_dialog).grid(row=row, column=5, sticky=tk.W, padx=4)
        row += 1
        ttk.Button(content, text="Sayfaların Yerini Değiştir / Düzenle", command=self.reorder_pages_dialog).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=4, pady=4)
        ttk.Label(content, text="Sıkıştırma: DPI").grid(row=row, column=2, sticky=tk.E, padx=4)
        ttk.Spinbox(content, from_=50, to=300, textvariable=self.pdf_dpi_var, width=6).grid(row=row, column=3, sticky=tk.W, padx=4)
        ttk.Label(content, text="Kalite").grid(row=row, column=4, sticky=tk.E, padx=4)
        ttk.Spinbox(content, from_=20, to=95, textvariable=self.pdf_quality_var, width=6).grid(row=row, column=5, sticky=tk.W, padx=4)
        ttk.Button(content, text="PDF'yi Küçült", command=self.compress_current_pdf).grid(row=row, column=6, sticky=tk.W, padx=4)

        row += 1
        ttk.Separator(content).grid(row=row, column=0, columnspan=8, sticky=tk.EW, pady=8)
        row += 1
        ttk.Label(content, text="Kırpma", style="Header.TLabel").grid(row=row, column=0, columnspan=8, sticky=tk.W)
        row += 1
        labels = [("Sol", self.crop_left_var), ("Üst", self.crop_top_var), ("Sağ", self.crop_right_var), ("Alt", self.crop_bottom_var)]
        for col, (label, var) in enumerate(labels):
            ttk.Label(content, text=label).grid(row=row, column=col * 2, sticky=tk.E, padx=4)
            ttk.Spinbox(content, from_=0, to=200, increment=1, textvariable=var, width=7).grid(row=row, column=col * 2 + 1, sticky=tk.W, padx=4)
        row += 1
        ttk.Button(content, text="Seçili Sayfayı Kırp", command=self.crop_current_pdf).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=4, pady=4)
        ttk.Label(content, text="Değerler milimetredir; boş sayfa seçimi tüm PDF'ye uygulanır.").grid(row=row, column=2, columnspan=5, sticky=tk.W)

        row += 1
        ttk.Separator(content).grid(row=row, column=0, columnspan=8, sticky=tk.EW, pady=8)
        row += 1
        ttk.Label(content, text="Sayfa Numarası / Varak Numarası", style="Header.TLabel").grid(row=row, column=0, columnspan=8, sticky=tk.W)
        row += 1
        ttk.Label(content, text="Format").grid(row=row, column=0, sticky=tk.E, padx=4)
        ttk.Entry(content, textvariable=self.num_format_var, width=24).grid(row=row, column=1, sticky=tk.W, padx=4)
        ttk.Label(content, text="Yazı tipi").grid(row=row, column=2, sticky=tk.E, padx=4)
        ttk.Combobox(content, textvariable=self.num_font_var, values=["Calibri - Regular", "Helvetica", "Times-Roman", "Courier"], width=22, state="readonly").grid(row=row, column=3, sticky=tk.W, padx=4)
        ttk.Label(content, text="Yazı boyutu").grid(row=row, column=4, sticky=tk.E, padx=4)
        ttk.Spinbox(content, from_=6, to=72, textvariable=self.num_size_var, width=6).grid(row=row, column=5, sticky=tk.W, padx=4)
        row += 1
        ttk.Label(content, text="Konum").grid(row=row, column=0, sticky=tk.E, padx=4)
        ttk.Combobox(content, textvariable=self.num_position_var, values=["alt, orta", "alt, sol", "alt, sağ", "üst, orta", "üst, sol", "üst, sağ", "orta"], width=14, state="readonly").grid(row=row, column=1, sticky=tk.W, padx=4)
        ttk.Label(content, text="Açı").grid(row=row, column=2, sticky=tk.E, padx=4)
        ttk.Spinbox(content, from_=-360, to=360, textvariable=self.num_angle_var, width=6).grid(row=row, column=3, sticky=tk.W, padx=4)
        ttk.Label(content, text="Renk").grid(row=row, column=4, sticky=tk.E, padx=4)
        ttk.Button(content, text="Seç", command=self.choose_number_color).grid(row=row, column=5, sticky=tk.W, padx=4)
        row += 1
        ttk.Label(content, text="X ekseni uzaklığı").grid(row=row, column=0, sticky=tk.E, padx=4)
        ttk.Spinbox(content, from_=-200, to=200, textvariable=self.num_x_var, width=7).grid(row=row, column=1, sticky=tk.W, padx=4)
        ttk.Label(content, text="mm  Y ekseni uzaklığı").grid(row=row, column=2, sticky=tk.E, padx=4)
        ttk.Spinbox(content, from_=-200, to=200, textvariable=self.num_y_var, width=7).grid(row=row, column=3, sticky=tk.W, padx=4)
        ttk.Label(content, text="İlk sayfa").grid(row=row, column=4, sticky=tk.E, padx=4)
        ttk.Spinbox(content, from_=1, to=9999, textvariable=self.num_first_page_var, width=7).grid(row=row, column=5, sticky=tk.W, padx=4)
        ttk.Label(content, text="Ofset").grid(row=row, column=6, sticky=tk.E, padx=4)
        ttk.Spinbox(content, from_=-9999, to=9999, textvariable=self.num_offset_var, width=7).grid(row=row, column=7, sticky=tk.W, padx=4)
        row += 1
        ttk.Button(content, text="Sayfa Numarası Ekle", command=self.add_page_numbers).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=4, pady=4)
        ttk.Label(content, text="Varak harfleri").grid(row=row, column=2, sticky=tk.E, padx=4)
        ttk.Entry(content, textvariable=self.folio_first_side_var, width=4).grid(row=row, column=3, sticky=tk.W, padx=4)
        ttk.Entry(content, textvariable=self.folio_second_side_var, width=4).grid(row=row, column=3, sticky=tk.E, padx=4)
        ttk.Combobox(content, textvariable=self.folio_per_page_var, values=["tek varak", "çift varak"], width=10, state="readonly").grid(row=row, column=4, sticky=tk.W, padx=4)
        ttk.Label(content, text="Satır").grid(row=row, column=5, sticky=tk.E, padx=4)
        ttk.Spinbox(content, from_=0, to=80, textvariable=self.folio_lines_var, width=6).grid(row=row, column=6, sticky=tk.W, padx=4)
        ttk.Button(content, text="Varak Numarası Ekle", command=self.add_folio_numbers).grid(row=row, column=7, sticky=tk.W, padx=4)

        row += 1
        ttk.Separator(content).grid(row=row, column=0, columnspan=8, sticky=tk.EW, pady=8)
        row += 1
        ttk.Label(content, text="PDF Üzerinde Çalışma", style="Header.TLabel").grid(row=row, column=0, columnspan=8, sticky=tk.W)
        row += 1
        ttk.Label(content, text="Araç").grid(row=row, column=0, sticky=tk.E, padx=4)
        ttk.Combobox(content, textvariable=self.mark_kind_var, values=["metin", "çizgi", "form", "resim", "filigran", "filigranı kapat"], state="readonly", width=14).grid(row=row, column=1, sticky=tk.W, padx=4)
        ttk.Label(content, text="Metin").grid(row=row, column=2, sticky=tk.E, padx=4)
        ttk.Entry(content, textvariable=self.mark_text_var, width=24).grid(row=row, column=3, columnspan=2, sticky=tk.W, padx=4)
        ttk.Button(content, text="Resim Seç", command=self.choose_markup_image).grid(row=row, column=5, sticky=tk.W, padx=4)
        ttk.Button(content, text="Uygula", command=self.apply_markup).grid(row=row, column=6, sticky=tk.W, padx=4)
        row += 1
        for col, (label, var) in enumerate([("X", self.mark_x_var), ("Y", self.mark_y_var), ("Genişlik", self.mark_w_var), ("Yükseklik", self.mark_h_var)]):
            ttk.Label(content, text=label).grid(row=row, column=col * 2, sticky=tk.E, padx=4)
            ttk.Spinbox(content, from_=0, to=500, textvariable=var, width=7).grid(row=row, column=col * 2 + 1, sticky=tk.W, padx=4)
        row += 1
        ttk.Label(content, text="Renk").grid(row=row, column=0, sticky=tk.E, padx=4)
        ttk.Button(content, text="Seç", command=self.choose_markup_color).grid(row=row, column=1, sticky=tk.W, padx=4)
        ttk.Label(content, text="Çizgi kalınlığı").grid(row=row, column=2, sticky=tk.E, padx=4)
        ttk.Spinbox(content, from_=0.5, to=20, increment=0.5, textvariable=self.mark_line_var, width=7).grid(row=row, column=3, sticky=tk.W, padx=4)

        row += 1
        self.pdf_info = tk.Text(content, height=8, wrap=tk.WORD)
        self.pdf_info.grid(row=row, column=0, columnspan=8, sticky=tk.EW, pady=(10, 0))
        self.pdf_info.insert("1.0", "Her işlemden sonra çıktı kaydedilir ve isterseniz son kaydedilen PDF üzerinden çalışmaya devam edilir.\n")
        for col in range(8):
            content.columnconfigure(col, weight=1)

    def _build_pdf_tool_cards(self, content: ttk.Frame) -> None:
        settings = ttk.LabelFrame(content, text="Ortak Ayarlar", padding=8)
        settings.grid(row=1, column=0, columnspan=4, sticky=tk.EW, pady=(0, 10))
        ttk.Label(settings, text="Seçili sayfalar").grid(row=0, column=0, sticky=tk.W, padx=4)
        ttk.Entry(settings, textvariable=self.pdf_pages_var, width=20).grid(row=0, column=1, sticky=tk.W, padx=4)
        ttk.Label(settings, text="Örn. 1,3-5. Boşsa tüm sayfalar.").grid(row=0, column=2, sticky=tk.W, padx=4)
        ttk.Label(settings, text="Çıktı adı").grid(row=1, column=0, sticky=tk.W, padx=4, pady=(6, 0))
        ttk.Entry(settings, textvariable=self.pdf_output_name_var, width=28).grid(row=1, column=1, sticky=tk.W, padx=4, pady=(6, 0))
        ttk.Button(settings, text="Son Kaydedilen PDF'yi Kullan", command=self.reload_current_pdf).grid(row=1, column=2, sticky=tk.W, padx=4, pady=(6, 0))

        tools = [
            ("PDFleri Birleştir", self.open_merge_tool),
            ("PDF'yi Küçült", self.open_compress_tool),
            ("PDF Üzerinde Çalış", self.open_markup_tool),
            ("Yatay / Dikey Format", self.open_orientation_tool),
            ("PDF'yi Sayfalara Ayır", self.open_split_tool),
            ("Çift Sayfayı Tek Sayfa Yap", self.open_double_page_split_tool),
            ("Sayfa Döndür", self.open_rotate_tool),
            ("Sayfa Sil", self.open_delete_tool),
            ("Sayfa Çıkar", self.open_extract_tool),
            ("Sayfaları Sırala", self.open_reorder_tool),
            ("Filigran Ekle", self.open_watermark_tool),
            ("Filigranı Kapat", self.open_whiteout_tool),
            ("Sayfa Numarası Ekle", self.open_page_number_tool),
            ("Varak Numarası Ekle", self.open_folio_number_tool),
            ("PDF Overlay", self.open_markup_tool),
            ("PDF Kırp", self.open_crop_tool),
        ]
        self.pdf_tool_area = ttk.Frame(content)
        self.pdf_tool_area.grid(row=2, column=0, columnspan=4, sticky=tk.EW)
        self.pdf_tool_cards = []
        for label, command in tools:
            self.pdf_tool_cards.append(self._add_pdf_tool_card(self.pdf_tool_area, label, command))
        self.pdf_tool_area.bind("<Configure>", self.reflow_pdf_tool_cards)

        self.pdf_inline_settings = ttk.LabelFrame(content, text="Araç Ayarları", padding=8)
        self.pdf_inline_settings.grid(row=3, column=0, columnspan=4, sticky=tk.EW, pady=(10, 0))
        ttk.Label(self.pdf_inline_settings, text="Bir PDF aracı seçin; ayarlar burada görünecek.").grid(row=0, column=0, sticky=tk.W)
        self.saved_pdf_var = tk.StringVar(value="")
        saved_bar = ttk.Frame(content)
        saved_bar.grid(row=0, column=2, columnspan=2, sticky=tk.EW, pady=(0, 8))
        ttk.Button(saved_bar, text="Klasörde Göster", command=self.show_saved_pdf_folder).pack(side=tk.RIGHT)
        ttk.Label(saved_bar, textvariable=self.saved_pdf_var).pack(side=tk.RIGHT, fill=tk.X, expand=True)
        for col in range(4):
            content.columnconfigure(col, weight=1)

    def _add_pdf_tool_card(self, parent: ttk.Frame, label: str, command):
        frame = ttk.Frame(parent, padding=4, relief=tk.RIDGE)
        icon = tk.Canvas(frame, width=36, height=32, highlightthickness=0, bg="#f8f8f8")
        icon.pack(side=tk.LEFT, padx=(0, 8))
        self.draw_pdf_tool_icon(icon, label)
        ttk.Button(frame, text=label, command=command, width=18).pack(side=tk.LEFT, fill=tk.X, expand=True)
        return frame

    def reflow_pdf_tool_cards(self, event=None) -> None:
        width = max(1, self.pdf_tool_area.winfo_width())
        card_width = 235
        cols = max(1, min(6, width // card_width))
        for index, frame in enumerate(self.pdf_tool_cards):
            frame.grid(row=index // cols, column=index % cols, sticky=tk.EW, padx=4, pady=4)
        for col in range(cols):
            self.pdf_tool_area.columnconfigure(col, weight=1)

    def draw_pdf_tool_icon(self, icon: tk.Canvas, label: str) -> None:
        icon.create_rectangle(8, 4, 28, 28, outline="#666", fill="#fff")
        icon.create_line(12, 12, 24, 12, fill="#777")
        icon.create_line(12, 18, 24, 18, fill="#777")
        if "Birleştir" in label:
            icon.create_line(3, 8, 8, 8, arrow=tk.LAST, fill="#2a6")
        elif "Küçült" in label:
            icon.create_rectangle(13, 9, 23, 23, outline="#2a6")
        elif "OCR" in label:
            icon.create_text(18, 16, text="OCR", font=("Segoe UI", 6, "bold"), fill="#06c")
        elif "Numarası" in label:
            icon.create_text(18, 16, text="123", font=("Segoe UI", 6, "bold"), fill="#900")
        elif "Kırp" in label or "Tek Sayfa" in label:
            icon.create_line(18, 4, 18, 28, dash=(2, 2), fill="#c60")
        elif "Döndür" in label:
            icon.create_arc(9, 7, 27, 25, start=20, extent=280, outline="#06c")
        elif "Filigran" in label:
            icon.create_text(18, 16, text="W", font=("Segoe UI", 9, "bold"), fill="#999")

    def _bind_events(self) -> None:
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.text.bind("<<Modified>>", self.on_text_modified)
        self.examples.bind("<<Modified>>", self.on_examples_modified)
        self.vocab.bind("<Double-1>", self.edit_vocab_row)
        self.preview.bind("<Control-MouseWheel>", self.on_preview_ctrl_wheel)
        self.preview.bind("<MouseWheel>", self.on_preview_mouse_wheel)
        self.preview.bind("<ButtonPress-1>", self.start_pan_preview)
        self.preview.bind("<B1-Motion>", self.pan_preview)
        self.preview.bind("<ButtonRelease-1>", self.finish_preview_drag)
        self.bind("<F5>", lambda _e: self._ocr_current_via_panel())
        self.bind("<F6>", lambda _e: self._ocr_all_via_panel())
        self.bind("<Control-s>", lambda _e: self.save())
        self.bind("<Control-h>", lambda _e: self.open_find_replace())
        self.bind("<Control-f>", lambda _e: (
            self.ocr_panel._toggle_search_bar()
            if self._current_mode == "ocr" and hasattr(self, "ocr_panel")
            else self.open_find_in_page()
        ))
        self.bind("<Control-Left>", lambda _e: self.goto_page(-1))
        self.bind("<Control-Right>", lambda _e: self.goto_page(1))

    def new_project(self) -> None:
        if not self.confirm_unsaved():
            return
        name = self.simple_name_dialog("Yeni proje adı", "Metin Atölyesi")
        if name:
            self.project = create_project(name)
            self.corrections = CorrectionsStore(self.project.root)
            self.dirty = False
            self._refresh_all()
            self._sync_ocr_panel()

    def open_project(self) -> None:
        if not self.confirm_unsaved():
            return
        path = filedialog.askopenfilename(title="Proje aç", filetypes=[("Metin Atölyesi Projesi", "project.json"), ("JSON", "*.json")])
        if path:
            self.project = load_project(path)
            self.corrections = CorrectionsStore(self.project.root)
            self.dirty = False
            self._refresh_all()
            self._sync_ocr_panel()

    def load_source(self) -> None:
        path = filedialog.askopenfilename(
            title="PDF veya gorsel yukle",
            filetypes=[("PDF/Gorsel", "*.pdf *.png *.jpg *.jpeg *.tif *.tiff"), ("Tum dosyalar", "*.*")],
        )
        if not path:
            return
        self.load_sources([path])

    def load_sources_dialog(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Toplu PDF veya görsel yükle",
            filetypes=[("PDF/Görsel", "*.pdf *.png *.jpg *.jpeg *.tif *.tiff"), ("Tüm dosyalar", "*.*")],
        )
        if paths:
            self.load_sources(paths)

    def load_sources(self, paths) -> None:
        if not paths:
            return
        self.project.pages.clear()
        first_pdf = None
        loaded = 0
        try:
            for raw_path in paths:
                source = Path(raw_path)
                if not source.exists():
                    continue
                if source.suffix.lower() == ".pdf":
                    if first_pdf is None:
                        first_pdf = source
                    self.load_pdf_pages(source, append=True)
                    loaded += 1
                elif source.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
                    self.load_image(source, append=True)
                    loaded += 1
            if first_pdf:
                self.project.source_path = str(first_pdf)
                self._add_recent_file(str(first_pdf))
            elif paths:
                self.project.source_path = str(Path(paths[0]))
            self.project.current_page = 0
            self.preview_pages = []
            self._mark_dirty()
            self._refresh_all()
            self._sync_ocr_panel()
            self.status_var.set(f"{loaded} dosya yüklendi.")
        except Exception as exc:
            messagebox.showerror("Yükleme sorunu", str(exc))

    def _setup_drag_drop(self) -> None:
        if not DND_FILES:
            self.status_var.set("Sürükle-bırak modülü yok; Toplu Yükle düğmesi kullanılabilir.")
            return
        try:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self.on_files_dropped)
            self.preview.drop_target_register(DND_FILES)
            self.preview.dnd_bind("<<Drop>>", self.on_files_dropped)
        except Exception:
            self.status_var.set("Sürükle-bırak etkinleştirilemedi; Toplu Yükle düğmesi kullanılabilir.")

    def on_files_dropped(self, event) -> None:
        paths = self.tk.splitlist(event.data)
        self.load_sources(paths)

    def load_single_source_old(self, path: str) -> None:
        source = Path(path)
        self.project.source_path = str(source)
        try:
            if source.suffix.lower() == ".pdf":
                self.load_pdf_pages(source)
            else:
                self.load_image(source)
            self._mark_dirty()
            self._refresh_all()
        except Exception as exc:
            messagebox.showerror("Yukleme sorunu", str(exc))

    def load_pdf_pages(self, source: Path, append: bool = False) -> None:
        if not append:
            self.project.pages.clear()
        image_dir = self.project.images_dir / f"{len(self.project.pages) + 1:04d}_{source.stem}"
        if image_dir.exists():
            shutil.rmtree(image_dir, ignore_errors=True)
        for image_path in images_from_pdf(source, image_dir):
            idx = len(self.project.pages)
            self.project.pages.append(PageRecord(page_index=idx, label=str(idx + 1), source_path=str(source), image_path=str(image_path)))
        if not append:
            self.project.current_page = 0

    def load_image(self, source: Path, append: bool = False) -> None:
        if not append:
            self.project.pages.clear()
        dest = self.project.images_dir / f"{len(self.project.pages) + 1:04d}_{source.name}"
        shutil.copy2(source, dest)
        idx = len(self.project.pages)
        self.project.pages.append(PageRecord(page_index=idx, label=str(idx + 1), source_path=str(source), image_path=str(dest)))
        if not append:
            self.project.current_page = 0

    def run_ocr_current(self) -> None:
        page = self.current_page()
        if not page or not page.image_path:
            messagebox.showinfo("OCR", "Önce PDF veya görsel yükleyin.")
            return
        try:
            image_path = Path(page.image_path)
            work_dir = self.project.images_dir
            if self.ocr_preprocess_var.get() == "çoklu deneme":
                text, suspicious = run_multi_mode_ocr(
                    image_path,
                    work_dir,
                    lang=self.ocr_lang_var.get(),
                    engine=self.ocr_engine_var.get(),
                    deskew=self.ocr_deskew_var.get(),
                )
            else:
                preprocessed = work_dir / f"{image_path.stem}_ocr.png"
                preprocess_image(image_path, preprocessed, self.ocr_preprocess_var.get())
                if self.ocr_confidence_var.get():
                    from metin_atolyesi.core.ocr import ocr_image_with_confidence
                    text, suspicious = ocr_image_with_confidence(preprocessed, self.ocr_lang_var.get())
                else:
                    text, suspicious = ocr_image(preprocessed, self.ocr_lang_var.get(), self.ocr_engine_var.get())
            text = self.corrections.apply(text)
            text = self.apply_ocr_corrections_to_text(text)
            suspicious = self.apply_ocr_references(text, suspicious)
            page.text = text
            page.suspicious = suspicious
            self._mark_dirty()
            self._refresh_text()
            self._refresh_suspicious()
            self.status_var.set(f"OCR tamamlandı: {len(suspicious)} şüpheli okuma adayı.")
        except Exception as exc:
            messagebox.showerror("OCR sorunu", str(exc))

    def run_ocr_scope(self) -> None:
        if self.ocr_scope_var.get() == "tüm sayfalar":
            self.run_ocr_all_threaded()
        else:
            self.run_ocr_current()

    def apply_ocr_references(self, text: str, suspicious: list[dict[str, object]]) -> list[dict[str, object]]:
        for wrong, correct in self.ocr_corrections.items():
            if wrong:
                text = text.replace(wrong, correct)
        enriched = list(suspicious)
        if self.ocr_dictionary:
            for match in __import__("re").finditer(r"\S+", text):
                word = match.group(0).strip(".,;:()[]{}").lower()
                if len(word) > 3 and word not in self.ocr_dictionary and not any(item.get("start") == match.start() for item in enriched):
                    enriched.append({"word": match.group(0), "start": match.start(), "end": match.end(), "confidence": 0.7, "level": "uncertain"})
        return enriched

    def apply_ocr_corrections_to_text(self, text: str) -> str:
        for wrong, correct in self.ocr_corrections.items():
            if wrong:
                text = text.replace(wrong, correct)
        return text

    def run_command(self) -> None:
        command = self.command_var.get().strip()
        if not command:
            return
        page = self.current_page()
        text = self.text.get("1.0", tk.END).strip()
        if command.lower().startswith(("ai:", "yapay zeka:", "yz:")):
            output = run_local_ai(command, text, self.examples.get("1.0", tk.END).strip())
            self.text.delete("1.0", tk.END)
            self.text.insert("1.0", output)
            if page:
                page.text = output
                page.suspicious = find_suspicious_words(output)
            self._mark_dirty()
            self._refresh_suspicious()
            self.status_var.set("Yerel yapay zeka komutu calistirildi." if local_ai_available() else "Ollama bulunamadi.")
            return
        output, items, report = apply_command(text, command)
        if "metne" not in command.lower() and output:
            self.text.delete("1.0", tk.END)
            self.text.insert("1.0", output)
        if items:
            self.project.vocabulary.extend(items)
            self._refresh_vocab()
        if page:
            page.text = self.text.get("1.0", tk.END).strip()
            page.suspicious = find_suspicious_words(page.text)
        self._mark_dirty()
        self._refresh_suspicious()
        self.status_var.set(report)

    def show_text_context_menu(self, event) -> None:
        menu = tk.Menu(self, tearoff=0)
        try:
            selected = self.text.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            selected = ""
        if selected.strip():
            menu.add_command(label="Doğru okunuşu öğret", command=lambda: self.teach_ocr_reading(selected.strip()))
            menu.add_command(label="Kopyala", command=lambda: self.clipboard_append(selected))
        else:
            menu.add_command(label="Önce metinde bir kelime seçin", state=tk.DISABLED)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def teach_ocr_reading(self, wrong_text: str) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("OCR okuma öğret")
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(dialog, text=f"Seçili okuma: {wrong_text}").pack(anchor=tk.W, padx=12, pady=(12, 4))
        var = tk.StringVar(value=wrong_text)
        ttk.Entry(dialog, textvariable=var, width=48).pack(padx=12, pady=6)

        scope_var = tk.StringVar(value="project")
        scope_frame = ttk.Frame(dialog)
        scope_frame.pack(padx=12, pady=(0, 4))
        ttk.Radiobutton(scope_frame, text="Bu proje", variable=scope_var, value="project").pack(side=tk.LEFT)
        ttk.Radiobutton(scope_frame, text="Tüm projeler (global)", variable=scope_var, value="global").pack(side=tk.LEFT, padx=8)

        def save() -> None:
            correct = var.get().strip()
            if correct:
                self.corrections.teach(wrong_text, correct, scope=scope_var.get())
                self.ocr_corrections[wrong_text] = correct
                content = self.text.get("1.0", tk.END)
                self.text.delete("1.0", tk.END)
                self.text.insert("1.0", content.replace(wrong_text, correct))
                self._sync_current_text()
                self.status_var.set(f"OCR düzeltmesi öğrenildi: {wrong_text} → {correct}")
            dialog.destroy()

        ttk.Button(dialog, text="Öğret ve Metinde Düzelt", command=save).pack(pady=(6, 12))
        self.wait_window(dialog)

    def extract_items(self) -> None:
        page = self.current_page()
        text = self.text.get("1.0", tk.END).strip()
        location = page.label if page else ""
        items = extract_vocabulary(text, location=location)
        if not items:
            messagebox.showinfo("Madde baslari", "Bu metinde otomatik madde basi bulunamadi.")
            return
        self.project.vocabulary.extend(items)
        self._mark_dirty()
        self._refresh_vocab()
        self.status_var.set(f"{len(items)} madde adayi tabloya eklendi.")

    def save(self) -> None:
        self._sync_from_widgets()
        self.project.batch_size = int(self.batch_var.get())
        save_project(self.project)
        self.dirty = False
        self.status_var.set(f"Kaydedildi: {self.project.data_path}")

    def export_word(self) -> None:
        self._sync_from_widgets()
        path = filedialog.asksaveasfilename(defaultextension=".docx", initialdir=str(EXPORTS_DIR), filetypes=[("Word", "*.docx")])
        if path:
            exporters.export_word(self.project, Path(path))
            self.status_var.set(f"Word aktarildi: {path}")

    def export_excel(self) -> None:
        self._sync_from_widgets()
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", initialdir=str(EXPORTS_DIR), filetypes=[("Excel", "*.xlsx")])
        if path:
            exporters.export_excel(self.project, Path(path))
            self.status_var.set(f"Excel aktarildi: {path}")

    def export_txt(self) -> None:
        self._sync_from_widgets()
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialdir=str(EXPORTS_DIR), filetypes=[("Metin", "*.txt")])
        if path:
            exporters.export_txt(self.project, Path(path))
            self.status_var.set(f"Metin aktarildi: {path}")

    def split_pdf_dialog(self) -> None:
        if not self.project.source_path or Path(self.project.source_path).suffix.lower() != ".pdf":
            messagebox.showinfo("PDF böl", "Önce bir PDF yükleyin.")
            return
        try:
            out_dir = EXPORTS_DIR / f"{Path(self.project.source_path).stem}_bolunmus"
            outputs = pdf_tools.split_pdf(Path(self.project.source_path), out_dir, int(self.pdf_split_var.get()))
            if hasattr(self, "pdf_info"):
                self.pdf_info.insert(tk.END, f"\n{len(outputs)} PDF oluşturuldu: {out_dir}\n")
            self.status_var.set(f"PDF bölme tamamlandı: {len(outputs)} dosya → {out_dir}")
            messagebox.showinfo("PDF Bölündü", f"{len(outputs)} PDF oluşturuldu:\n{out_dir}")
        except Exception as exc:
            messagebox.showerror("PDF sorunu", str(exc))

    def preview_split_pdf(self, out: Path) -> Path:
        source = self.current_pdf_path()
        if not source:
            raise RuntimeError("PDF yok.")
        out_dir = out.parent / "bolunmus_on_izleme"
        outputs = pdf_tools.split_pdf(source, out_dir, int(self.pdf_split_var.get()))
        if not outputs:
            raise RuntimeError("Ön izleme PDF'i üretilemedi.")
        return outputs[0]

    def open_split_tool(self) -> None:
        self.pdf_tool_dialog(
            "PDF'yi Sayfalara Ayır",
            [("Her dosyada sayfa", self.pdf_split_var, "int")],
            lambda out: self.preview_split_pdf(out),
            self.split_pdf_dialog,
        )

    def open_double_page_split_tool(self) -> None:
        self.pdf_tool_dialog(
            "Çift Sayfayı Tek Sayfa Yap",
            [("Sayfa sırası", self.double_split_order_var, "combo:sağ sayfa önce|sol sayfa önce"), ("Çıktı adı", self.pdf_output_name_var, "text")],
            lambda out: pdf_tools.split_double_pages_to_single(self.current_pdf_path(), out, right_page_first="sağ" in self.double_split_order_var.get()),
            self.apply_double_page_split,
        )

    def apply_double_page_split(self) -> None:
        source = self.current_pdf_path()
        if not source:
            return
        try:
            out = self.output_pdf_path("cift_sayfa_tek_sayfa")
            pdf_tools.split_double_pages_to_single(source, out, right_page_first="sağ" in self.double_split_order_var.get())
            self.use_pdf_output(out, "Çift sayfalar tek sayfaya ayrıldı")
        except Exception as exc:
            messagebox.showerror("PDF sorunu", str(exc))

    def open_extract_tool(self) -> None:
        self.pdf_tool_dialog(
            "Sayfa Çıkar",
            [("Seçili sayfalar (örn. 1,3-5,8)", self.pdf_pages_var, "text"), ("Çıktı adı", self.pdf_output_name_var, "text")],
            lambda out: pdf_tools.extract_pages(self.current_pdf_path(), out, self.selected_pdf_pages()),
            self.export_selected_pages,
        )

    def open_delete_tool(self) -> None:
        self.pdf_tool_dialog(
            "Sayfa Sil",
            [("Silinecek sayfalar (örn. 2,4-6)", self.pdf_pages_var, "text"), ("Çıktı adı", self.pdf_output_name_var, "text")],
            lambda out: pdf_tools.delete_pages(self.current_pdf_path(), out, self.selected_pdf_pages()),
            self.delete_selected_pages,
        )

    def open_compress_tool(self) -> None:
        self.pdf_tool_dialog(
            "PDF'yi Küçült",
            [("DPI", self.pdf_dpi_var, "int"), ("Kalite", self.pdf_quality_var, "int"), ("Çıktı adı", self.pdf_output_name_var, "text")],
            lambda out: pdf_tools.compress_pdf(self.current_pdf_path(), out, int(self.pdf_dpi_var.get()), int(self.pdf_quality_var.get())),
            self.compress_current_pdf,
        )

    def open_crop_tool(self) -> None:
        fields = [
            ("Seçili sayfalar", self.pdf_pages_var, "text"),
            ("Sol mm", self.crop_left_var, "float"),
            ("Üst mm", self.crop_top_var, "float"),
            ("Sağ mm", self.crop_right_var, "float"),
            ("Alt mm", self.crop_bottom_var, "float"),
        ]
        self.pdf_tool_dialog(
            "PDF Kırp",
            fields,
            lambda out: pdf_tools.crop_pdf(self.current_pdf_path(), out, self.crop_left_var.get(), self.crop_top_var.get(), self.crop_right_var.get(), self.crop_bottom_var.get(), self.selected_pdf_pages()),
            self.crop_current_pdf,
        )
        ttk.Button(self.pdf_inline_settings, text="Ekrandan Elle Kırpma Alanı Seç", command=self.enable_crop_selection).grid(row=6, column=0, sticky=tk.W, padx=4, pady=4)

    def open_page_number_tool(self) -> None:
        self.pdf_tool_dialog(
            "Sayfa Numarası Ekle",
            self.number_fields(),
            lambda out: self._write_page_numbers_to(out),
            self.add_page_numbers,
            color_command=self.choose_number_color,
        )

    def open_folio_number_tool(self) -> None:
        fields = self.number_fields() + [
            ("İlk harf", self.folio_first_side_var, "text"),
            ("İkinci harf", self.folio_second_side_var, "text"),
            ("Her sayfada", self.folio_per_page_var, "combo:tek varak|çift varak"),
            ("Satır sayısı", self.folio_lines_var, "int"),
        ]
        self.pdf_tool_dialog(
            "Varak Numarası Ekle",
            fields,
            lambda out: self._write_folio_numbers_to(out),
            self.add_folio_numbers,
            color_command=self.choose_number_color,
        )

    def open_markup_tool(self) -> None:
        self.preview_edit_mode = True
        self.pdf_tool_dialog(
            "PDF Üzerinde Çalış",
            [field for field in self.markup_fields() if field[0] != "Araç"],
            lambda out: self._write_markup_to(out),
            self.apply_markup,
            color_command=self.choose_markup_color,
            image_command=self.choose_markup_image,
        )
        self.add_markup_toolbox()

    def add_markup_toolbox(self) -> None:
        tools = [
            ("✍", "serbest çizim"),
            ("—", "çizgi"),
            ("▭", "form"),
            ("▰", "vurgu"),
            ("T", "metin"),
            ("🖼", "resim"),
            ("W", "filigran"),
            ("▯", "kapatıcı kalem"),
            ("↶", "geri al"),
            ("↷", "ileri al"),
        ]
        row = 0
        frame = ttk.Frame(self.pdf_inline_settings)
        frame.grid(row=row, column=2, columnspan=2, sticky=tk.W, padx=8)
        for symbol, tool in tools:
            if tool == "geri al":
                cmd = self.undo_preview_markup
            elif tool == "ileri al":
                cmd = self.redo_preview_markup
            else:
                cmd = lambda t=tool: self.set_markup_tool(t)
            ttk.Button(frame, text=symbol, width=3, command=cmd).pack(side=tk.LEFT, padx=2)

    def set_markup_tool(self, tool: str) -> None:
        self.mark_kind_var.set(tool)
        self.preview_edit_mode = True
        self.preview.configure(cursor="crosshair")

    def open_pdf_ocr_tool(self) -> None:
        fields = [
            ("OCR kapsamı", self.ocr_scope_var, "combo:geçerli sayfa|tüm sayfalar"),
            ("OCR motoru", self.ocr_engine_var, "combo:otomatik|windows|tesseract|rapidocr"),
            ("Dil", self.ocr_lang_var, "combo:tur+eng|tur|eng|ara|ota"),
            ("Görüntü ön işlemi", self.ocr_preprocess_var, "combo:çoklu deneme|zorlu|dengeli|temiz|adaptif|deskew|gürültü"),
        ]
        self.pdf_tool_dialog(
            "PDF OCR",
            fields,
            lambda out: self.preview_ocr_to_pdf(out),
            self.run_ocr_scope,
        )
        row = len(fields) + 4
        ttk.Checkbutton(self.pdf_inline_settings, text="Eğik sayfayı otomatik düzelt (deskew)", variable=self.ocr_deskew_var).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=4, pady=2)
        row += 1
        ttk.Checkbutton(self.pdf_inline_settings, text="Kelime bazlı güven skoru (Tesseract)", variable=self.ocr_confidence_var).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=4, pady=2)
        row += 1
        ttk.Button(self.pdf_inline_settings, text="Toplu OCR Başlat (arka plan)", command=self.run_ocr_all_threaded).grid(row=row, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Button(self.pdf_inline_settings, text="OCR Düzeltmelerini Düzenle", command=self.open_corrections_editor).grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)
        row += 1
        ttk.Button(self.pdf_inline_settings, text="Okunmuş Referans Metin Yükle", command=self.load_ocr_reference).grid(row=row, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Button(self.pdf_inline_settings, text="Tarihi Sözlük / Maddebaşı Yükle", command=self.load_ocr_dictionary).grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)
        row += 1
        ttk.Label(self.pdf_inline_settings, text="Belirsiz okumalar sarı, hatalı/çok şüpheli okumalar kırmızı gösterilir.").grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=4)

    def preview_ocr_to_pdf(self, out: Path) -> Path:
        source = self.current_pdf_path()
        if not source:
            raise RuntimeError("PDF yok.")
        return pdf_tools.extract_pages(source, out, [self.project.current_page + 1])

    def load_ocr_reference(self) -> None:
        path = filedialog.askopenfilename(title="Okunmuş referans metni yükle", filetypes=[("Metin", "*.txt"), ("Tüm dosyalar", "*.*")])
        if not path:
            return
        self.ocr_reference_text = Path(path).read_text(encoding="utf-8", errors="ignore")
        self.status_var.set("OCR referans metni yüklendi.")

    def load_ocr_dictionary(self) -> None:
        paths = filedialog.askopenfilenames(title="Tarihi sözlük / maddebaşı listesi yükle", filetypes=[("Metin/CSV", "*.txt *.csv"), ("Tüm dosyalar", "*.*")])
        count = 0
        for path in paths:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                word = line.split(",")[0].split("\t")[0].strip()
                if word:
                    self.ocr_dictionary.add(word.lower())
                    count += 1
        self.status_var.set(f"{count} sözlük/maddebaşı kaydı OCR referansına eklendi.")

    def open_watermark_tool(self) -> None:
        self.mark_kind_var.set("filigran")
        self.open_markup_tool()

    def open_whiteout_tool(self) -> None:
        self.mark_kind_var.set("filigranı kapat")
        self.open_markup_tool()

    def open_rotate_tool(self) -> None:
        self.pdf_tool_dialog(
            "Sayfa Döndür",
            [("Seçili sayfalar", self.pdf_pages_var, "text"), ("Yön", self.pdf_rotate_direction_var, "combo:sağa 90|sola 90|180"), ("Çıktı adı", self.pdf_output_name_var, "text")],
            lambda out: pdf_tools.rotate_pages(self.current_pdf_path(), out, self.selected_pdf_pages(), self.rotation_angle()),
            self.rotate_current_pdf,
        )

    def open_orientation_tool(self) -> None:
        self.pdf_tool_dialog(
            "Yatay / Dikey Format",
            [("Seçili sayfalar", self.pdf_pages_var, "text"), ("Format", self.pdf_orientation_var, "combo:dikey|yatay"), ("Çıktı adı", self.pdf_output_name_var, "text")],
            lambda out: pdf_tools.set_page_orientation(self.current_pdf_path(), out, self.pdf_orientation_var.get(), self.selected_pdf_pages()),
            self.apply_orientation_pdf,
        )

    def apply_orientation_pdf(self) -> None:
        source = self.current_pdf_path()
        if not source:
            return
        try:
            out = self.output_pdf_path("format_degisti")
            pdf_tools.set_page_orientation(source, out, self.pdf_orientation_var.get(), self.selected_pdf_pages())
            self.use_pdf_output(out, "Yatay/dikey format uygulandı")
        except Exception as exc:
            messagebox.showerror("PDF sorunu", str(exc))

    def open_reorder_tool(self) -> None:
        source = self.current_pdf_path()
        if not source:
            return
        total = pdf_tools.page_count(source)
        order_var = tk.StringVar(value=",".join(str(i) for i in range(1, total + 1)))

        def preview(out: Path) -> Path:
            order = pdf_tools.parse_page_ranges(order_var.get(), total)
            return pdf_tools.reorder_pages(source, out, order)

        def apply() -> None:
            try:
                order = pdf_tools.parse_page_ranges(order_var.get(), total)
                out = self.output_pdf_path("siralandı")
                pdf_tools.reorder_pages(source, out, order)
                self.use_pdf_output(out, "Sayfa sırası değiştirildi")
            except Exception as exc:
                messagebox.showerror("PDF sorunu", str(exc))

        self.pdf_tool_dialog("Sayfaları Sırala", [("Yeni sıra", order_var, "multiline")], preview, apply)

    def open_merge_tool(self) -> None:
        paths = filedialog.askopenfilenames(title="Birleştirilecek PDFleri seç", filetypes=[("PDF", "*.pdf")])
        if not paths:
            return
        selected = [Path(p) for p in paths]

        def preview(out: Path) -> Path:
            return pdf_tools.merge_pdfs(selected, out)

        def apply() -> None:
            try:
                out = self.output_pdf_path("birlestirildi")
                pdf_tools.merge_pdfs(selected, out)
                self.use_pdf_output(out, "PDFler birleştirildi")
            except Exception as exc:
                messagebox.showerror("PDF sorunu", str(exc))

        self.pdf_tool_dialog("PDFleri Birleştir", [("Çıktı adı", self.pdf_output_name_var, "text")], preview, apply)

    def pdf_tool_dialog(self, title: str, fields: list[tuple[str, object, str]], preview_action, apply_action, color_command=None, image_command=None) -> None:
        source = self.current_pdf_path()
        if not source:
            return
        for child in self.pdf_inline_settings.winfo_children():
            child.destroy()
        ttk.Label(self.pdf_inline_settings, text=title, style="Header.TLabel").grid(row=0, column=0, columnspan=4, sticky=tk.W, pady=(0, 6))
        form = self.pdf_inline_settings
        for row, (label, var, kind) in enumerate(fields):
            ui_row = row // 2 + 1
            base_col = (row % 2) * 2
            ttk.Label(form, text=label).grid(row=ui_row, column=base_col, sticky=tk.W, padx=4, pady=4)
            if kind.startswith("combo:"):
                values = kind.split(":", 1)[1].split("|")
                ttk.Combobox(form, textvariable=var, values=values, state="readonly", width=22).grid(row=ui_row, column=base_col + 1, sticky=tk.W, padx=4, pady=4)
            elif kind == "multiline":
                box_frame = ttk.Frame(form)
                box_frame.grid(row=ui_row, column=base_col + 1, sticky=tk.NSEW, padx=4, pady=4)
                text_box = tk.Text(box_frame, width=34, height=6, wrap=tk.WORD)
                scroll = ttk.Scrollbar(box_frame, orient=tk.VERTICAL, command=text_box.yview)
                text_box.configure(yscrollcommand=scroll.set)
                text_box.insert("1.0", var.get())
                text_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                scroll.pack(side=tk.RIGHT, fill=tk.Y)
                text_box.bind("<KeyRelease>", lambda _e, v=var, w=text_box: v.set(w.get("1.0", tk.END).strip()))
            else:
                ttk.Entry(form, textvariable=var, width=24).grid(row=ui_row, column=base_col + 1, sticky=tk.W, padx=4, pady=4)
        button_row = (len(fields) + 1) // 2 + 1
        if color_command:
            ttk.Button(form, text="Renk Seç", command=color_command).grid(row=button_row, column=0, sticky=tk.W, padx=4, pady=6)
        if image_command:
            ttk.Button(form, text="Resim Seç", command=image_command).grid(row=button_row, column=1, sticky=tk.W, padx=4, pady=6)

        def do_apply() -> None:
            """Uygula: işlemi geçici PDF'de çalıştırıp önizlemede göster."""
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    out = Path(temp_dir) / "on_izleme.pdf"
                    preview_pdf = preview_action(out)
                    images = list(images_from_pdf(preview_pdf, Path(temp_dir) / "images"))
                    # PDF modundaysak pdf_preview canvas'ını güncelle
                    if self._current_mode == "pdf" and hasattr(self, "pdf_preview"):
                        self._show_pdf_tool_preview(images)
                    else:
                        self.show_preview_pages(images)
                    self.status_var.set(
                        "Uygulama sonucu önizlemede gösterildi. "
                        "Kaydetmek için 'Kaydet' düğmesini kullanın."
                    )
            except Exception as exc:
                messagebox.showerror("Uygulama sorunu", str(exc))

        def do_save() -> None:
            """Kaydet: işlemi dışa aktar klasörüne kaydet."""
            apply_action()

        def do_save_as() -> None:
            """Farklı Kaydet: kullanıcının seçtiği konuma kaydet."""
            path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                initialdir=str(EXPORTS_DIR),
                filetypes=[("PDF", "*.pdf")],
                title="Farklı Kaydet",
            )
            if not path:
                return
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    tmp_out = Path(temp_dir) / "kaydet_tmp.pdf"
                    preview_action(tmp_out)
                    shutil.copy2(tmp_out, path)
                self._add_recent_file(path)
                self.status_var.set(f"Farklı kaydedildi: {path}")
                messagebox.showinfo("Kaydedildi", f"PDF şu konuma kaydedildi:\n{path}")
            except Exception as exc:
                messagebox.showerror("Kayıt hatası", str(exc))

        buttons = ttk.Frame(form)
        buttons.grid(row=button_row + 1, column=0, columnspan=4, sticky=tk.W, pady=(10, 0))
        ttk.Button(buttons, text="Uygula", command=do_apply).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Kaydet", command=do_save).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Farklı Kaydet", command=do_save_as).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Temizle", command=self.clear_pdf_inline_settings).pack(side=tk.LEFT, padx=4)

    def clear_pdf_inline_settings(self) -> None:
        for child in self.pdf_inline_settings.winfo_children():
            child.destroy()
        ttk.Label(self.pdf_inline_settings, text="Bir PDF aracı seçin; ayarlar burada görünecek.").grid(row=0, column=0, sticky=tk.W)

    def number_fields(self) -> list[tuple[str, object, str]]:
        return [
            ("Format", self.num_format_var, "text"),
            ("Sayfa düzeni", self.page_number_layout_var, "combo:tek sayfa|çift sayfa"),
            ("Yazı tipi", self.num_font_var, "combo:Calibri - Regular|Helvetica|Times-Roman|Courier"),
            ("Yazı boyutu", self.num_size_var, "int"),
            ("Konum", self.num_position_var, "combo:alt, orta|alt, sol|alt, sağ|üst, orta|üst, sol|üst, sağ|orta"),
            ("Açı", self.num_angle_var, "float"),
            ("Kenardan uzaklık mm", self.num_x_var, "float"),
            ("Alttan/üstten uzaklık mm", self.num_y_var, "float"),
            ("İlk sayfa", self.num_first_page_var, "int"),
            ("Numarayı kaç artır/azalt", self.num_offset_var, "int"),
            ("Seçili sayfalar", self.pdf_pages_var, "text"),
        ]

    def markup_fields(self) -> list[tuple[str, object, str]]:
        return [
            ("Araç", self.mark_kind_var, "combo:metin|çizgi|serbest çizim|form|vurgu|resim|filigran|filigranı kapat|kapatıcı kalem"),
            ("Metin", self.mark_text_var, "text"),
            ("X mm", self.mark_x_var, "float"),
            ("Y mm", self.mark_y_var, "float"),
            ("Genişlik mm", self.mark_w_var, "float"),
            ("Yükseklik mm", self.mark_h_var, "float"),
            ("Çizgi kalınlığı", self.mark_line_var, "float"),
            ("Seçili sayfalar", self.pdf_pages_var, "text"),
        ]

    def selected_pdf_pages(self) -> list[int]:
        if not self.project.source_path or Path(self.project.source_path).suffix.lower() != ".pdf":
            return []
        total = pdf_tools.page_count(Path(self.project.source_path))
        text = self.pdf_pages_var.get().strip()
        if not text:
            return list(range(1, total + 1))
        return pdf_tools.parse_page_ranges(text, total)

    def current_pdf_path(self) -> Path | None:
        if self.project.source_path and Path(self.project.source_path).suffix.lower() == ".pdf":
            return Path(self.project.source_path)
        messagebox.showinfo("PDF", "Önce bir PDF yükleyin.")
        return None

    def output_pdf_path(self, suffix: str) -> Path:
        source = Path(self.project.source_path) if self.project.source_path else Path("metin_atolyesi.pdf")
        name = self.pdf_output_name_var.get().strip() or f"{source.stem}_{suffix}.pdf"
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        if name == "duzenlenmis.pdf":
            name = f"{source.stem}_{suffix}.pdf"
        return EXPORTS_DIR / name

    def use_pdf_output(self, out_path: Path, note: str) -> None:
        self.project.source_path = str(out_path)
        self.project.images_dir.mkdir(exist_ok=True)
        self.load_pdf_pages(out_path)
        self.preview_pages = []
        self._mark_dirty()
        self._refresh_all()
        self.last_saved_pdf = out_path
        self._add_recent_file(str(out_path))
        if hasattr(self, "saved_pdf_var"):
            self.saved_pdf_var.set(f"PDF şu konuma kaydedildi: {out_path}")
        if hasattr(self, "pdf_info"):
            self.pdf_info.insert(tk.END, f"\n{note}: {out_path}\n")
        # PDF modundaysa önizlemeyi güncelle
        if self._current_mode == "pdf":
            self.after(50, self._refresh_pdf_frame_preview)
        self.status_var.set(note)
        messagebox.showinfo("PDF Kaydedildi", f"PDF şu konuma kaydedildi:\n{out_path}")

    def show_saved_pdf_folder(self) -> None:
        target = self.last_saved_pdf or (Path(self.project.source_path) if self.project.source_path else EXPORTS_DIR)
        folder = target.parent if target and target.suffix.lower() == ".pdf" else EXPORTS_DIR
        try:
            os.startfile(folder)
        except Exception as exc:
            messagebox.showerror("Klasörde göster", str(exc))

    def reload_current_pdf(self) -> None:
        source = self.current_pdf_path()
        if not source:
            return
        try:
            self.load_pdf_pages(source)
            self.preview_pages = []
            self._refresh_all()
            self.status_var.set("Son kaydedilen PDF yeniden yüklendi.")
        except Exception as exc:
            messagebox.showerror("PDF sorunu", str(exc))

    def export_selected_pages(self) -> None:
        source = self.current_pdf_path()
        if not source:
            return
        pages = self.selected_pdf_pages()
        if not pages:
            messagebox.showinfo("PDF", "Dışarı aktarılacak sayfa seçilmedi.")
            return
        try:
            out = self.output_pdf_path("secilen_sayfalar")
            pdf_tools.extract_pages(source, out, pages)
            self.use_pdf_output(out, "Seçili sayfalar dışarı aktarıldı")
        except Exception as exc:
            messagebox.showerror("PDF sorunu", str(exc))

    def delete_selected_pages(self) -> None:
        source = self.current_pdf_path()
        if not source:
            return
        pages = self.selected_pdf_pages()
        if not pages:
            messagebox.showinfo("PDF", "Silinecek sayfa seçilmedi.")
            return
        if not messagebox.askyesno("Sayfa sil", f"{len(pages)} sayfa çıkarılsın mı?"):
            return
        try:
            out = self.output_pdf_path("sayfa_silindi")
            pdf_tools.delete_pages(source, out, pages)
            self.use_pdf_output(out, "Seçili sayfalar çıkarıldı")
        except Exception as exc:
            messagebox.showerror("PDF sorunu", str(exc))

    def rotate_current_pdf(self) -> None:
        source = self.current_pdf_path()
        if not source:
            return
        try:
            out = self.output_pdf_path("donduruldu")
            pdf_tools.rotate_pages(source, out, self.selected_pdf_pages(), self.rotation_angle())
            self.use_pdf_output(out, "Sayfa döndürme uygulandı")
        except Exception as exc:
            messagebox.showerror("PDF sorunu", str(exc))

    def rotation_angle(self) -> int:
        value = self.pdf_rotate_direction_var.get()
        if "sola" in value:
            return -90
        if "180" in value:
            return 180
        return 90

    def merge_pdfs_dialog(self) -> None:
        paths = filedialog.askopenfilenames(title="Birleştirilecek PDFleri seç", filetypes=[("PDF", "*.pdf")])
        if not paths:
            return
        try:
            out = self.output_pdf_path("birlestirildi")
            pdf_tools.merge_pdfs([Path(p) for p in paths], out)
            self.use_pdf_output(out, "PDFler birleştirildi")
        except Exception as exc:
            messagebox.showerror("PDF sorunu", str(exc))

    def reorder_pages_dialog(self) -> None:
        source = self.current_pdf_path()
        if not source:
            return
        total = pdf_tools.page_count(source)
        dialog = tk.Toplevel(self)
        dialog.title("Sayfaların Yerini Değiştir / Düzenle")
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(dialog, text=f"Yeni sıralamayı yazın. Örnek: 2,1,3-5   Toplam sayfa: {total}").pack(padx=12, pady=(12, 6))
        var = tk.StringVar(value=",".join(str(i) for i in range(1, total + 1)))
        ttk.Entry(dialog, textvariable=var, width=70).pack(padx=12, pady=6)

        def apply() -> None:
            try:
                order = pdf_tools.parse_page_ranges(var.get(), total)
                out = self.output_pdf_path("siralandı")
                pdf_tools.reorder_pages(source, out, order)
                dialog.destroy()
                self.use_pdf_output(out, "Sayfa sırası değiştirildi")
            except Exception as exc:
                messagebox.showerror("PDF sorunu", str(exc))

        buttons = ttk.Frame(dialog)
        buttons.pack(pady=12)
        ttk.Button(buttons, text="Uygula", command=apply).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Vazgeç", command=dialog.destroy).pack(side=tk.LEFT, padx=4)
        self.wait_window(dialog)

    def compress_current_pdf(self) -> None:
        source = self.current_pdf_path()
        if not source:
            return
        try:
            out = self.output_pdf_path("kucultuldu")
            pdf_tools.compress_pdf(source, out, int(self.pdf_dpi_var.get()), int(self.pdf_quality_var.get()))
            self.use_pdf_output(out, "PDF küçültüldü")
        except Exception as exc:
            messagebox.showerror("PDF sorunu", str(exc))

    def crop_current_pdf(self) -> None:
        source = self.current_pdf_path()
        if not source:
            return
        try:
            pages = self.selected_pdf_pages()
            out = self.output_pdf_path("kirpildi")
            pdf_tools.crop_pdf(
                source,
                out,
                self.crop_left_var.get(),
                self.crop_top_var.get(),
                self.crop_right_var.get(),
                self.crop_bottom_var.get(),
                pages,
            )
            self.use_pdf_output(out, "PDF kırpıldı")
        except Exception as exc:
            messagebox.showerror("PDF sorunu", str(exc))

    def add_page_numbers(self) -> None:
        source = self.current_pdf_path()
        if not source:
            return
        try:
            out = self.output_pdf_path("sayfa_numarali")
            self._write_page_numbers_to(out)
            self.use_pdf_output(out, "Sayfa numarası eklendi")
        except Exception as exc:
            messagebox.showerror("PDF sorunu", str(exc))

    def _write_page_numbers_to(self, out: Path) -> Path:
        source = self.current_pdf_path()
        if not source:
            raise RuntimeError("PDF yok.")
        return pdf_tools.add_overlay(
            source,
            out,
            mode="page",
            text_format=self.num_format_var.get(),
            first_page=int(self.num_first_page_var.get()),
            offset=int(self.num_offset_var.get()),
            position=self.num_position_var.get(),
            x_mm=self.num_x_var.get(),
            y_mm=self.num_y_var.get(),
            font_name=self.num_font_var.get().split(" - ")[0],
            font_size=int(self.num_size_var.get()),
            color=self.num_color_var.get(),
            angle=self.num_angle_var.get(),
            folios_per_pdf_page=2 if "çift" in self.page_number_layout_var.get() else 1,
            selected_pages=self.selected_pdf_pages(),
        )

    def add_folio_numbers(self) -> None:
        source = self.current_pdf_path()
        if not source:
            return
        try:
            out = self.output_pdf_path("varak_numarali")
            self._write_folio_numbers_to(out)
            self.use_pdf_output(out, "Varak numarası eklendi")
        except Exception as exc:
            messagebox.showerror("PDF sorunu", str(exc))

    def _write_folio_numbers_to(self, out: Path) -> Path:
        source = self.current_pdf_path()
        if not source:
            raise RuntimeError("PDF yok.")
        return pdf_tools.add_overlay(
            source,
            out,
            mode="folio",
            first_page=int(self.num_first_page_var.get()),
            offset=int(self.num_offset_var.get()),
            position=self.num_position_var.get(),
            x_mm=self.num_x_var.get(),
            y_mm=self.num_y_var.get(),
            font_name=self.num_font_var.get().split(" - ")[0],
            font_size=int(self.num_size_var.get()),
            color=self.num_color_var.get(),
            angle=self.num_angle_var.get(),
            folio_first_side=self.folio_first_side_var.get() or "a",
            folio_second_side=self.folio_second_side_var.get() or "b",
            folios_per_pdf_page=2 if "çift" in self.folio_per_page_var.get() else 1,
            line_count=self.folio_lines_var.get() or None,
            selected_pages=self.selected_pdf_pages(),
        )

    def choose_number_color(self) -> None:
        color = colorchooser.askcolor(color=self.num_color_var.get())[1]
        if color:
            self.num_color_var.set(color)

    def choose_markup_color(self) -> None:
        color = colorchooser.askcolor(color=self.mark_color_var.get())[1]
        if color:
            self.mark_color_var.set(color)

    def choose_markup_image(self) -> None:
        path = filedialog.askopenfilename(title="Resim seç", filetypes=[("Resim", "*.png *.jpg *.jpeg *.tif *.tiff"), ("Tüm dosyalar", "*.*")])
        if path:
            self.mark_image_path = Path(path)
            self.mark_text_var.set(Path(path).name)

    def apply_markup(self) -> None:
        source = self.current_pdf_path()
        if not source:
            return
        try:
            out = self.output_pdf_path("isaretlendi")
            self._write_markup_to(out)
            self.use_pdf_output(out, "PDF üzerinde işlem uygulandı")
        except Exception as exc:
            messagebox.showerror("PDF sorunu", str(exc))

    def _write_markup_to(self, out: Path) -> Path:
        source = self.current_pdf_path()
        if not source:
            raise RuntimeError("PDF yok.")
        kind_map = {"metin": "text", "çizgi": "line", "serbest çizim": "line", "form": "rect", "vurgu": "rect", "resim": "image", "filigran": "text", "filigranı kapat": "whiteout", "kapatıcı kalem": "whiteout"}
        kind = kind_map.get(self.mark_kind_var.get(), "text")
        if self.mark_kind_var.get() == "filigran":
            return pdf_tools.add_overlay(
                source,
                out,
                mode="page",
                text_format=self.mark_text_var.get() or "FİLİGRAN",
                position="orta",
                x_mm=0,
                y_mm=0,
                font_size=int(self.num_size_var.get()),
                color=self.mark_color_var.get(),
                angle=45,
                opacity=0.25,
                selected_pages=self.selected_pdf_pages(),
            )
        return pdf_tools.add_simple_markup(
            source,
            out,
            kind=kind,
            text=self.mark_text_var.get(),
            image_path=self.mark_image_path,
            page_numbers=self.selected_pdf_pages(),
            x_mm=self.mark_x_var.get(),
            y_mm=self.mark_y_var.get(),
            width_mm=self.mark_w_var.get(),
            height_mm=self.mark_h_var.get(),
            color=self.mark_color_var.get(),
            line_width=self.mark_line_var.get(),
            font_size=int(self.num_size_var.get()),
        )

    def apply_folio_labels(self) -> None:
        for page in self.project.pages:
            page.label = pdf_tools.folio_label(
                page.page_index,
                first_side=self.folio_first_side_var.get() or "a",
                second_side=self.folio_second_side_var.get() or "b",
                folios_per_pdf_page=2 if "çift" in self.folio_per_page_var.get() else 1,
                line_count=self.folio_lines_var.get() or None,
            )
        self._mark_dirty()
        self._refresh_page_label()
        self.status_var.set("Varak etiketleri uygulandi.")

    def toggle_orientation(self) -> None:
        current = self.paned.cget("orient")
        self.paned.configure(orient=tk.VERTICAL if current == tk.HORIZONTAL else tk.HORIZONTAL)
        self.project.split_orientation = "horizontal" if current == tk.HORIZONTAL else "vertical"
        self._mark_dirty()

    def goto_page(self, delta: int) -> None:
        if not self.project.pages:
            return
        self._sync_current_text()
        self.project.current_page = max(0, min(len(self.project.pages) - 1, self.project.current_page + delta))
        self._refresh_all()

    def current_page(self) -> PageRecord | None:
        if not self.project.pages:
            return None
        self.project.current_page = max(0, min(len(self.project.pages) - 1, self.project.current_page))
        return self.project.pages[self.project.current_page]

    def _refresh_all(self) -> None:
        self.title(f"{APP_DISPLAY_NAME} - {self.project.name}")
        self.batch_var.set(self.project.batch_size)
        self.examples.delete("1.0", tk.END)
        self.examples.insert("1.0", self.project.reading_examples)
        self.examples.edit_modified(False)
        self._refresh_preview()
        self._refresh_text()
        self._refresh_vocab()
        self._refresh_suspicious()
        self._refresh_page_label()

    def _refresh_preview(self) -> None:
        self.preview.delete("all")
        if self.preview_pages:
            self._draw_preview_image(self.preview_pages[self.preview_page_index])
            return
        page = self.current_page()
        if not page or not page.image_path or not Path(page.image_path).exists():
            self.preview.create_text(20, 20, text="PDF veya gorsel yukleyin.", anchor=tk.NW, fill="#666")
            return
        self._draw_preview_image(Path(page.image_path))

    def _draw_preview_image(self, image_path: Path) -> None:
        image = Image.open(image_path)
        self.preview_original = image.copy()
        self.update_idletasks()
        width = max(300, self.preview.winfo_width() - 20)
        height = max(300, self.preview.winfo_height() - 20)
        if self.fit_preview_to_window:
            image.thumbnail((width, height))
        else:
            image.thumbnail((int(width * self.preview_zoom), int(height * self.preview_zoom)))
        self.preview_image = ImageTk.PhotoImage(image)
        self.preview_display_size = (image.width, image.height)
        self.preview.create_image(10, 10, image=self.preview_image, anchor=tk.NW)
        self.preview.configure(scrollregion=(0, 0, image.width + 20, image.height + 20))

    def show_preview_pages(self, images: list[Path]) -> None:
        cache_dir = self.project.root / "preview_cache"
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []
        for index, image_path in enumerate(images):
            dest = cache_dir / f"preview_{index + 1:04d}{image_path.suffix or '.png'}"
            shutil.copy2(image_path, dest)
            copied.append(dest)
        self.preview_pages = copied
        self.preview_page_index = 0
        self._refresh_preview()

    def zoom_preview(self, factor: float) -> None:
        self.fit_preview_to_window = False
        self.preview_zoom = max(0.25, min(6.0, self.preview_zoom * factor))
        self._refresh_preview()

    def fit_preview(self) -> None:
        self.fit_preview_to_window = True
        self.preview_zoom = 1.0
        self._refresh_preview()

    def on_preview_ctrl_wheel(self, event) -> None:
        self.zoom_preview(1.12 if event.delta > 0 else 0.89)
        return "break"

    def on_preview_mouse_wheel(self, event) -> None:
        if self.preview_pages:
            self.preview_page_index = max(0, min(len(self.preview_pages) - 1, self.preview_page_index + ( -1 if event.delta > 0 else 1)))
            self._refresh_preview()
            return "break"
        self.goto_page(-1 if event.delta > 0 else 1)
        return "break"

    def on_window_mouse_wheel(self, event) -> None:
        if self.focus_get() in {self.text, self.examples}:
            return
        if self.preview_pages:
            self.on_preview_mouse_wheel(event)
            return "break"
        self.goto_page(-1 if event.delta > 0 else 1)
        return "break"

    def set_hand_cursor(self) -> None:
        self.preview.configure(cursor="hand2")
        self.status_var.set("El aracı açık: sayfayı fareyle sürükleyebilirsiniz. Ctrl + fare tekeri yakınlaştırır.")

    def start_pan_preview(self, event) -> None:
        self.pan_start = (event.x, event.y)
        self.preview_drag_points = [(event.x, event.y)]
        if self.preview_edit_mode and self.preview.cget("cursor") != "hand2":
            tool = self.mark_kind_var.get()
            color = self.mark_color_var.get()
            if tool in {"form", "vurgu", "filigranı kapat", "kapatıcı kalem"}:
                fill = "#ffff66" if tool == "vurgu" else ("#ffffff" if "kapat" in tool else "")
                self.preview_drag_item = self.preview.create_rectangle(event.x, event.y, event.x, event.y, outline=color, fill=fill, stipple="gray25" if tool == "vurgu" else "")
            elif tool in {"çizgi", "serbest çizim"}:
                self.preview_drag_item = self.preview.create_line(event.x, event.y, event.x, event.y, fill=color, width=max(1, int(self.mark_line_var.get())))
            if self.preview_drag_item:
                self.preview_canvas_items.append(self.preview_drag_item)
                self.preview_redo_items.clear()
            return "break"

    def pan_preview(self, event) -> None:
        if self.preview_edit_mode and self.preview_drag_item and self.preview.cget("cursor") != "hand2":
            tool = self.mark_kind_var.get()
            self.preview_drag_points.append((event.x, event.y))
            if tool == "serbest çizim":
                coords = [value for point in self.preview_drag_points for value in point]
                self.preview.coords(self.preview_drag_item, *coords)
            else:
                x0, y0 = self.preview_drag_points[0]
                self.preview.coords(self.preview_drag_item, x0, y0, event.x, event.y)
            return "break"
        if not self.pan_start:
            return
        x0, y0 = self.pan_start
        self.preview.scan_mark(x0, y0)
        self.preview.scan_dragto(event.x, event.y, gain=1)
        self.pan_start = (event.x, event.y)

    def finish_preview_drag(self, event) -> None:
        if self.preview_edit_mode and self.preview_drag_points and self.preview.cget("cursor") != "hand2":
            x0, y0 = self.preview_drag_points[0]
            if abs(event.x - x0) > 6 and abs(event.y - y0) > 6:
                if self.crop_select_mode:
                    self.set_crop_from_preview_selection(x0, y0, event.x, event.y)
                    self.crop_select_mode = False
                    self.preview_edit_mode = False
                    self.preview.configure(cursor="")
                    self.preview_drag_item = None
                    self.preview_drag_points = []
                    return "break"
                menu = tk.Menu(self, tearoff=0)
                menu.add_command(label="Kopyala", command=lambda: self.copy_preview_selection(x0, y0, event.x, event.y))
                try:
                    menu.tk_popup(event.x_root, event.y_root)
                finally:
                    menu.grab_release()
            self.preview_drag_item = None
            self.preview_drag_points = []

    def enable_crop_selection(self) -> None:
        self.crop_select_mode = True
        self.preview_edit_mode = True
        self.mark_kind_var.set("form")
        self.preview.configure(cursor="crosshair")
        self.status_var.set("Kırpma için sol ön izlemede korunacak alanı fareyle seçin.")

    def set_crop_from_preview_selection(self, x1: int, y1: int, x2: int, y2: int) -> None:
        source = self.current_pdf_path()
        page = self.current_page()
        if not source or not page:
            return
        from pypdf import PdfReader

        reader = PdfReader(str(source))
        page_index = max(0, min(len(reader.pages) - 1, self.project.current_page))
        pdf_page = reader.pages[page_index]
        page_w_mm = float(pdf_page.mediabox.width) * 25.4 / 72
        page_h_mm = float(pdf_page.mediabox.height) * 25.4 / 72
        img_w, img_h = self.preview_display_size
        left_px = max(0, min(x1, x2) - 10)
        right_px = max(0, img_w - (max(x1, x2) - 10))
        top_px = max(0, min(y1, y2) - 10)
        bottom_px = max(0, img_h - (max(y1, y2) - 10))
        self.crop_left_var.set(round(left_px / img_w * page_w_mm, 2))
        self.crop_right_var.set(round(right_px / img_w * page_w_mm, 2))
        self.crop_top_var.set(round(top_px / img_h * page_h_mm, 2))
        self.crop_bottom_var.set(round(bottom_px / img_h * page_h_mm, 2))
        self.status_var.set("Kırpma ölçüleri seçilen alana göre dolduruldu. Ön İzleme veya Kaydet / Uygula yapabilirsiniz.")

    def copy_preview_selection(self, x1: int, y1: int, x2: int, y2: int) -> None:
        text = f"Seçili alan: {min(x1,x2)},{min(y1,y2)} - {max(x1,x2)},{max(y1,y2)}"
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("Seçili alan bilgisi kopyalandı.")

    def undo_preview_markup(self) -> None:
        if not self.preview_canvas_items:
            return
        item = self.preview_canvas_items.pop()
        self.preview.itemconfigure(item, state="hidden")
        self.preview_redo_items.append(item)

    def redo_preview_markup(self) -> None:
        if not self.preview_redo_items:
            return
        item = self.preview_redo_items.pop()
        self.preview.itemconfigure(item, state="normal")
        self.preview_canvas_items.append(item)

    def _refresh_text(self) -> None:
        page = self.current_page()
        self.text.delete("1.0", tk.END)
        if page:
            self.text.insert("1.0", page.text)
            self._highlight_suspicious(page.suspicious or find_suspicious_words(page.text))
        self.text.edit_modified(False)

    def _highlight_suspicious(self, suspicious: list[dict[str, object]]) -> None:
        self.text.tag_remove("suspicious", "1.0", tk.END)
        self.text.tag_remove("uncertain", "1.0", tk.END)
        content = self.text.get("1.0", tk.END)
        for item in suspicious:
            word = str(item.get("word", ""))
            if not word:
                continue
            start = content.find(word)
            if start >= 0:
                tag = "uncertain" if item.get("level") == "uncertain" or float(item.get("confidence", 0)) >= 0.5 else "suspicious"
                self.text.tag_add(tag, f"1.0+{start}c", f"1.0+{start + len(word)}c")

    def _refresh_vocab(self) -> None:
        for iid in self.vocab.get_children():
            self.vocab.delete(iid)
        for item in self.project.vocabulary:
            self.vocab.insert("", tk.END, values=(item.headword, item.origin, item.meaning, item.usage, item.suffixes, item.location, item.note))

    def _refresh_suspicious(self) -> None:
        self.suspicious_list.delete(0, tk.END)
        page = self.current_page()
        if not page:
            return
        page.suspicious = page.suspicious or find_suspicious_words(page.text)
        for item in page.suspicious:
            prefix = "Belirsiz: " if item.get("level") == "uncertain" else "Şüpheli: "
            self.suspicious_list.insert(tk.END, prefix + str(item.get("word", "")))

    def _refresh_page_label(self) -> None:
        total = len(self.project.pages)
        if not total:
            self.page_var.set("0/0")
            return
        page = self.current_page()
        self.page_var.set(f"{self.project.current_page + 1}/{total} - {page.label if page else ''}")

    def _sync_current_text(self) -> None:
        page = self.current_page()
        if page:
            page.text = self.text.get("1.0", tk.END).strip()
            page.suspicious = find_suspicious_words(page.text)

    def _sync_vocab_from_tree(self) -> None:
        items: list[VocabularyItem] = []
        for iid in self.vocab.get_children():
            values = self.vocab.item(iid, "values")
            items.append(VocabularyItem(*values[:7]))
        self.project.vocabulary = items

    def _sync_from_widgets(self) -> None:
        self._sync_current_text()
        self._sync_vocab_from_tree()
        self.project.reading_examples = self.examples.get("1.0", tk.END).strip()

    def add_vocab_row(self) -> None:
        self.project.vocabulary.append(VocabularyItem(location=self.current_page().label if self.current_page() else ""))
        self._mark_dirty()
        self._refresh_vocab()

    def edit_vocab_row(self, _event=None) -> None:
        selected = self.vocab.selection()
        if not selected:
            return
        iid = selected[0]
        values = list(self.vocab.item(iid, "values"))
        labels = ["Madde basi", "Koken", "Anlam", "Kullanim", "Ek", "Sayfa/Varak", "Not"]
        dialog = tk.Toplevel(self)
        dialog.title("Dizin satiri duzenle")
        dialog.transient(self)
        dialog.grab_set()
        vars_: list[tk.StringVar] = []
        for row, label in enumerate(labels):
            ttk.Label(dialog, text=label).grid(row=row, column=0, sticky=tk.W, padx=10, pady=5)
            var = tk.StringVar(value=values[row] if row < len(values) else "")
            vars_.append(var)
            ttk.Entry(dialog, textvariable=var, width=72).grid(row=row, column=1, sticky=tk.EW, padx=10, pady=5)
        dialog.columnconfigure(1, weight=1)

        def ok() -> None:
            self.vocab.item(iid, values=[v.get() for v in vars_])
            self._sync_vocab_from_tree()
            self._mark_dirty()
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.grid(row=len(labels), column=0, columnspan=2, pady=10)
        ttk.Button(buttons, text="Kaydet", command=ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons, text="Vazgec", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        self.wait_window(dialog)

    def delete_vocab_row(self) -> None:
        selected = set(self.vocab.selection())
        kept: list[VocabularyItem] = []
        for iid in self.vocab.get_children():
            values = self.vocab.item(iid, "values")
            if iid not in selected:
                kept.append(VocabularyItem(*values[:7]))
        self.project.vocabulary = kept
        self._mark_dirty()
        self._refresh_vocab()

    # ------------------------------------------------------------------
    # Otomatik kayıt
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # OCR panel köprü metodları
    # ------------------------------------------------------------------

    def _on_ocr_text_saved(self, page_index: int, text: str) -> None:
        """OCR panelinden metin kaydedildiğinde projeyi güncelle."""
        self._mark_dirty()
        self._refresh_text()
        self._refresh_suspicious()

    def _ocr_current_via_panel(self) -> None:
        """F5: OCR moduna geç ve geçerli sayfayı işle."""
        self._set_mode("ocr")
        if hasattr(self, "ocr_panel"):
            # Mod geçişi tamamlanana kadar kısa bekle
            self.after(120, lambda: self._trigger_ocr_panel("görünen"))

    def _ocr_all_via_panel(self) -> None:
        """F6: OCR moduna geç ve tüm sayfaları işle."""
        self._set_mode("ocr")
        if hasattr(self, "ocr_panel"):
            self.after(120, lambda: self._trigger_ocr_panel("tümü"))

    def _trigger_ocr_panel(self, scope: str) -> None:
        """OCR panelinde kapsam ayarla ve başlat."""
        if not hasattr(self, "ocr_panel"):
            return
        try:
            self.ocr_panel._scope_var.set(scope)
            self.ocr_panel._start_ocr()
        except Exception:
            pass

    def _sync_ocr_panel(self) -> None:
        """Proje değiştiğinde OCR panelini güncelle."""
        if hasattr(self, "ocr_panel"):
            self.ocr_panel.set_project(self.project, self.corrections)

    def _start_autosave(self, interval_ms: int = 120_000) -> None:
        def _save() -> None:
            if self.dirty:
                try:
                    self._sync_from_widgets()
                    save_project(self.project)
                    self.dirty = False
                    self.status_var.set("Otomatik kaydedildi.")
                except Exception:
                    pass
            self._autosave_id = self.after(interval_ms, _save)

        self._autosave_id = self.after(interval_ms, _save)

    # ------------------------------------------------------------------
    # Bul / Değiştir
    # ------------------------------------------------------------------

    def open_find_replace(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Bul / Değiştir")
        dialog.transient(self)
        dialog.resizable(False, False)
        find_var = tk.StringVar()
        replace_var = tk.StringVar()
        case_var = tk.BooleanVar(value=False)
        all_pages_var = tk.BooleanVar(value=False)
        ttk.Label(dialog, text="Bul:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=6)
        ttk.Entry(dialog, textvariable=find_var, width=42).grid(row=0, column=1, columnspan=2, padx=4, pady=6)
        ttk.Label(dialog, text="Değiştir:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=6)
        ttk.Entry(dialog, textvariable=replace_var, width=42).grid(row=1, column=1, columnspan=2, padx=4, pady=6)
        ttk.Checkbutton(dialog, text="Büyük/küçük harf duyarlı", variable=case_var).grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=10)
        ttk.Checkbutton(dialog, text="Tüm sayfalarda değiştir", variable=all_pages_var).grid(row=2, column=2, sticky=tk.W, padx=4)
        result_var = tk.StringVar()
        ttk.Label(dialog, textvariable=result_var, foreground="#555").grid(row=3, column=0, columnspan=3, padx=10, pady=4)

        def do_find() -> None:
            import re
            find = find_var.get()
            if not find:
                return
            content = self.text.get("1.0", tk.END)
            flags = 0 if case_var.get() else re.IGNORECASE
            match = re.search(re.escape(find), content, flags)
            if match:
                self.text.tag_remove("sel", "1.0", tk.END)
                start = f"1.0+{match.start()}c"
                end = f"1.0+{match.end()}c"
                self.text.tag_add("sel", start, end)
                self.text.see(start)
                result_var.set(f"Bulundu: karakter {match.start()}")
            else:
                result_var.set("Bulunamadı.")

        def do_replace() -> None:
            import re
            find = find_var.get()
            replace = replace_var.get()
            if not find:
                return
            flags = 0 if case_var.get() else re.IGNORECASE
            if all_pages_var.get():
                count = 0
                for page in self.project.pages:
                    new_text, n = re.subn(re.escape(find), replace, page.text, flags=flags)
                    if n:
                        page.text = new_text
                        count += n
                self._refresh_text()
                self._mark_dirty()
                result_var.set(f"{count} değiştirme yapıldı (tüm sayfalar).")
            else:
                content = self.text.get("1.0", tk.END)
                new_content, n = re.subn(re.escape(find), replace, content, flags=flags)
                if n:
                    self.text.delete("1.0", tk.END)
                    self.text.insert("1.0", new_content)
                    self._sync_current_text()
                    self._mark_dirty()
                result_var.set(f"{n} değiştirme yapıldı.")

        buttons = ttk.Frame(dialog)
        buttons.grid(row=4, column=0, columnspan=3, pady=10)
        ttk.Button(buttons, text="Bul", command=do_find).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Değiştir (Tümü)", command=do_replace).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Kapat", command=dialog.destroy).pack(side=tk.LEFT, padx=4)

    def open_find_in_page(self) -> None:
        """Aktif sayfada basit arama (seçimi vurgular)."""
        import tkinter.simpledialog as sd
        find = sd.askstring("Sayfada Ara", "Aranacak metin:", parent=self)
        if not find:
            return
        import re
        content = self.text.get("1.0", tk.END)
        self.text.tag_remove("sel", "1.0", tk.END)
        matches = list(re.finditer(re.escape(find), content, re.IGNORECASE))
        for m in matches:
            self.text.tag_add("sel", f"1.0+{m.start()}c", f"1.0+{m.end()}c")
        if matches:
            self.text.see(f"1.0+{matches[0].start()}c")
            self.status_var.set(f"{len(matches)} eşleşme bulundu.")
        else:
            self.status_var.set("Bulunamadı.")

    # ------------------------------------------------------------------
    # OCR düzeltme editörü
    # ------------------------------------------------------------------

    def open_corrections_editor(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("OCR Düzeltmeleri")
        dialog.transient(self)
        dialog.geometry("680x480")
        tree = ttk.Treeview(dialog, columns=("wrong", "correct", "scope"), show="headings")
        tree.heading("wrong", text="Yanlış okuma")
        tree.heading("correct", text="Doğru okuma")
        tree.heading("scope", text="Kapsam")
        tree.column("wrong", width=220)
        tree.column("correct", width=220)
        tree.column("scope", width=90)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)

        def refresh_tree() -> None:
            for iid in tree.get_children():
                tree.delete(iid)
            for wrong, correct, scope in self.corrections.all_entries():
                tree.insert("", tk.END, values=(wrong, correct, scope))

        refresh_tree()

        def delete_selected() -> None:
            for iid in tree.selection():
                vals = tree.item(iid, "values")
                if vals:
                    self.corrections.forget(vals[0])
            refresh_tree()

        def add_entry() -> None:
            sub = tk.Toplevel(dialog)
            sub.title("Düzeltme Ekle")
            sub.transient(dialog)
            w_var = tk.StringVar()
            c_var = tk.StringVar()
            sc_var = tk.StringVar(value="project")
            ttk.Label(sub, text="Yanlış:").grid(row=0, column=0, padx=8, pady=6, sticky=tk.W)
            ttk.Entry(sub, textvariable=w_var, width=36).grid(row=0, column=1, padx=8)
            ttk.Label(sub, text="Doğru:").grid(row=1, column=0, padx=8, pady=6, sticky=tk.W)
            ttk.Entry(sub, textvariable=c_var, width=36).grid(row=1, column=1, padx=8)
            ttk.Label(sub, text="Kapsam:").grid(row=2, column=0, padx=8, sticky=tk.W)
            ttk.Combobox(sub, textvariable=sc_var, values=["project", "global"], state="readonly", width=12).grid(row=2, column=1, padx=8, pady=4, sticky=tk.W)

            def save_entry() -> None:
                if w_var.get().strip():
                    self.corrections.teach(w_var.get().strip(), c_var.get().strip(), sc_var.get())
                    refresh_tree()
                sub.destroy()

            ttk.Button(sub, text="Ekle", command=save_entry).grid(row=3, column=0, columnspan=2, pady=10)

        btns = ttk.Frame(dialog)
        btns.pack(fill=tk.X, padx=10, pady=(0, 8))
        ttk.Button(btns, text="Yeni Ekle", command=add_entry).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Seçileni Sil", command=delete_selected).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Kapat", command=dialog.destroy).pack(side=tk.RIGHT, padx=4)

    def export_corrections(self) -> None:
        import json
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            Path(path).write_text(json.dumps(self.corrections.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            self.status_var.set(f"Düzeltmeler dışa aktarıldı: {path}")

    def import_corrections(self) -> None:
        import json
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        count = self.corrections.import_from_dict(data)
        self.status_var.set(f"{count} düzeltme içe aktarıldı.")

    # ------------------------------------------------------------------
    # Toplu OCR (thread)
    # ------------------------------------------------------------------

    def run_ocr_all_threaded(self) -> None:
        if self._ocr_thread and self._ocr_thread.is_alive():
            messagebox.showinfo("OCR", "Toplu OCR zaten çalışıyor.")
            return
        if not messagebox.askyesno("Toplu OCR", f"{len(self.project.pages)} sayfa okunacak. Devam?"):
            return
        prog_win = tk.Toplevel(self)
        prog_win.title("Toplu OCR İlerlemesi")
        prog_win.transient(self)
        prog_win.resizable(False, False)
        prog_var = tk.DoubleVar(value=0)
        label_var = tk.StringVar(value="Başlıyor…")
        ttk.Label(prog_win, textvariable=label_var, width=55).pack(padx=16, pady=(12, 4))
        bar = ttk.Progressbar(prog_win, variable=prog_var, maximum=100, length=380)
        bar.pack(padx=16, pady=(0, 12))
        cancelled = {"value": False}
        ttk.Button(prog_win, text="İptal", command=lambda: cancelled.__setitem__("value", True)).pack(pady=(0, 10))

        def run() -> None:
            total = len(self.project.pages)
            for i, page in enumerate(self.project.pages):
                if cancelled["value"]:
                    break
                if not page.image_path or not Path(page.image_path).exists():
                    continue
                label_var.set(f"Sayfa {i + 1}/{total}: {Path(page.image_path).name}")
                prog_var.set((i / total) * 100)
                try:
                    image_path = Path(page.image_path)
                    text, suspicious = run_multi_mode_ocr(
                        image_path,
                        self.project.images_dir,
                        lang=self.ocr_lang_var.get(),
                        engine=self.ocr_engine_var.get(),
                        deskew=self.ocr_deskew_var.get(),
                    )
                    text = self.corrections.apply(text)
                    text = self.apply_ocr_corrections_to_text(text)
                    page.text = text
                    page.suspicious = suspicious
                except Exception:
                    pass
            prog_var.set(100)
            label_var.set("Tamamlandı." if not cancelled["value"] else "İptal edildi.")
            self.after(0, self._on_batch_ocr_done)
            self.after(1500, prog_win.destroy)

        self._ocr_thread = threading.Thread(target=run, daemon=True)
        self._ocr_thread.start()

    def _on_batch_ocr_done(self) -> None:
        self._mark_dirty()
        self._refresh_all()
        self.status_var.set("Toplu OCR tamamlandı.")

    # ------------------------------------------------------------------
    # Metin katmanı ve aranabilir PDF
    # ------------------------------------------------------------------

    def import_text_layer(self) -> None:
        source = Path(self.project.source_path) if self.project.source_path else None
        if not source or source.suffix.lower() != ".pdf":
            messagebox.showinfo("Metin Katmanı", "Önce bir PDF yükleyin.")
            return
        if not has_text_layer(source):
            if not messagebox.askyesno("Metin Katmanı", "Bu PDF'de kullanılabilir metin katmanı bulunamadı. Yine de almayı deneyelim mi?"):
                return
        texts = extract_text_layer(source)
        count = 0
        for i, page in enumerate(self.project.pages):
            if i < len(texts) and texts[i].strip():
                page.text = texts[i]
                page.suspicious = []
                count += 1
        self._mark_dirty()
        self._refresh_all()
        self.status_var.set(f"{count} sayfanın metni PDF metin katmanından alındı.")

    def export_searchable_pdf(self) -> None:
        self._sync_from_widgets()
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialdir=str(EXPORTS_DIR),
            filetypes=[("PDF", "*.pdf")],
            title="Aranabilir PDF Kaydet",
        )
        if not path:
            return
        try:
            out = create_searchable_pdf(self.project, Path(path))
            self.status_var.set(f"Aranabilir PDF oluşturuldu: {out}")
            messagebox.showinfo("Başarılı", f"Aranabilir PDF kaydedildi:\n{out}")
        except Exception as exc:
            messagebox.showerror("PDF hatası", str(exc))

    def on_text_modified(self, _event=None) -> None:
        if self.text.edit_modified():
            self._mark_dirty()
            self.text.edit_modified(False)

    def on_examples_modified(self, _event=None) -> None:
        if self.examples.edit_modified():
            self._mark_dirty()
            self.examples.edit_modified(False)

    def _mark_dirty(self) -> None:
        self.dirty = True

    def confirm_unsaved(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("Kaydedilmemis degisiklik", "Degisiklikleri kaydetmek ister misiniz?")
        if answer is None:
            return False
        if answer:
            self.save()
        return True

    def on_close(self) -> None:
        # Kapanmadan önce veri reposunu push et
        try:
            from metin_atolyesi.core.github_sync import get_sync
            get_sync().push_now()
        except Exception:
            pass
        if not self.dirty:
            self.destroy()
            return
        if self.confirm_unsaved():
            self.destroy()

    def _startup_sync(self) -> None:
        """Başlangıçta veri reposunu arka planda güncelle."""
        try:
            from metin_atolyesi.core.github_sync import get_sync
            sync = get_sync(on_status=lambda msg: self.status_var.set(msg))
            if sync.available:
                sync.pull(blocking=False)
        except Exception:
            pass

    def show_dependencies(self) -> None:
        lines = []
        for status in collect_status():
            state = "Hazir" if status.available else "Eksik"
            lines.append(f"{status.name}: {state} - {status.note}")
        messagebox.showinfo("Bilesenler", "\n".join(lines) + "\n\nEksikler:\n" + missing_dependency_text())

    # -----------------------------------------------------------------------
    # Claude API ayarları
    # -----------------------------------------------------------------------

    def open_claude_settings(self) -> None:
        """Claude API anahtarı giriş penceresi."""
        from metin_atolyesi.core.claude_ocr import get_api_key, set_api_key

        dlg = tk.Toplevel(self)
        dlg.title("Claude API Ayarları")
        dlg.geometry("500x420")
        dlg.minsize(460, 380)
        dlg.transient(self)
        dlg.grab_set()

        # ── Başlık (koyu şerit) ───────────────────────────────────────────
        header = tk.Frame(dlg, bg="#1e1e2e")
        header.pack(fill=tk.X)
        tk.Label(
            header, text="  ⚡  Claude API Ayarları",
            bg="#1e1e2e", fg="#d8daf0",
            font=("Segoe UI", 11, "bold"), pady=10,
        ).pack(anchor=tk.W)

        # ── İçerik alanı ─────────────────────────────────────────────────
        body = ttk.Frame(dlg, padding=16)
        body.pack(fill=tk.BOTH, expand=True)

        # Açıklama
        ttk.Label(
            body,
            text="Claude'u OCR motoru olarak kullanmak için API anahtarınızı girin.\n"
                 "Anahtar yalnızca bu bilgisayarda saklanır.",
            wraplength=440, justify=tk.LEFT,
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        ttk.Separator(body).grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(0, 10))

        # API Anahtarı
        ttk.Label(body, text="API Anahtarı (sk-ant-...):").grid(
            row=2, column=0, sticky=tk.W, pady=4)
        key_var = tk.StringVar(value=get_api_key())
        key_entry = ttk.Entry(body, textvariable=key_var, width=44, show="•")
        key_entry.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=(0, 4))
        key_entry.focus_set()

        show_var = tk.BooleanVar(value=False)
        def toggle_show():
            key_entry.configure(show="" if show_var.get() else "•")
        ttk.Checkbutton(body, text="Anahtarı göster",
                        variable=show_var, command=toggle_show).grid(
            row=4, column=0, sticky=tk.W, pady=(0, 10))

        # Model seçimi
        ttk.Label(body, text="Model:").grid(row=5, column=0, sticky=tk.W, pady=(0, 2))
        from metin_atolyesi.core import claude_ocr as _co
        # get_api_key() zaten config'den _default_model'i yükler
        get_api_key()
        model_var = tk.StringVar(value=_co._default_model or "claude-opus-4-5")
        model_cb = ttk.Combobox(
            body, textvariable=model_var, width=28, state="readonly",
            values=["claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-4-5"],
        )
        model_cb.grid(row=6, column=0, sticky=tk.W, pady=(0, 4))

        ttk.Label(
            body,
            text="opus = En yüksek kalite  |  sonnet = Dengeli  |  haiku = Hızlı/Ucuz",
            foreground="#888", font=("Segoe UI", 9),
        ).grid(row=7, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        ttk.Separator(body).grid(row=8, column=0, columnspan=2, sticky=tk.EW, pady=(0, 10))

        # Sonuç etiketi
        result_var = tk.StringVar(value="")
        ttk.Label(body, textvariable=result_var,
                  foreground="#0066aa", font=("Segoe UI", 9)).grid(
            row=9, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        # Düğmeler
        btn_row = ttk.Frame(body)
        btn_row.grid(row=10, column=0, columnspan=2, sticky=tk.EW)

        def do_test() -> None:
            key = key_var.get().strip()
            if not key:
                result_var.set("⚠  Anahtar boş.")
                return
            result_var.set("⏳  Test ediliyor…")
            dlg.update()
            try:
                import anthropic
                c = anthropic.Anthropic(api_key=key)
                c.messages.create(
                    model=model_var.get(), max_tokens=5,
                    messages=[{"role": "user", "content": "hi"}],
                )
                result_var.set("✅  Bağlantı başarılı!")
            except Exception as exc:
                short = str(exc)[:120]
                result_var.set(f"❌  {short}")

        def do_save() -> None:
            key = key_var.get().strip()
            from metin_atolyesi.core import claude_ocr as _co
            _co._default_model = model_var.get()
            set_api_key(key)
            result_var.set("💾  Kaydedildi.")
            dlg.after(900, dlg.destroy)

        ttk.Button(btn_row, text="🔗 Bağlantıyı Test Et",
                   command=do_test).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="💾 Kaydet",
                   command=do_save).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="İptal",
                   command=dlg.destroy).pack(side=tk.RIGHT)

        body.columnconfigure(0, weight=1)
        self.wait_window(dlg)

    # -----------------------------------------------------------------------
    # El Yazması Öğretme Sihirbazı
    # -----------------------------------------------------------------------

    def open_manuscript_wizard(self) -> None:
        from metin_atolyesi.ui.manuscript_wizard import open_wizard
        open_wizard(self)

    def open_manuscript_library(self) -> None:
        from metin_atolyesi.ui.manuscript_wizard import open_library_viewer
        open_library_viewer(self)

    # -----------------------------------------------------------------------
    # HuggingFace ayarları
    # -----------------------------------------------------------------------

    def open_hf_settings(self) -> None:
        """HuggingFace token ve kullanıcı adı giriş penceresi."""
        from metin_atolyesi.core.hf_store import save_hf_config, _load_hf_config

        dlg = tk.Toplevel(self)
        dlg.title("HuggingFace Ayarları")
        dlg.geometry("520x440")
        dlg.minsize(480, 400)
        dlg.transient(self)
        dlg.grab_set()

        # Başlık
        header = tk.Frame(dlg, bg="#ff9500")
        header.pack(fill=tk.X)
        tk.Label(header, text="  🤗  HuggingFace Veri Deposu",
                 bg="#ff9500", fg="white",
                 font=("Segoe UI", 11, "bold"), pady=10).pack(anchor=tk.W)

        body = ttk.Frame(dlg, padding=16)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=1)

        # Açıklama
        ttk.Label(body,
                  text="Orijinal PDF'leri HuggingFace'te saklamak için\n"
                       "kullanıcı adınızı ve token'ınızı girin.\n"
                       "Token: huggingface.co/settings/tokens → Write yetkisi",
                  wraplength=460, justify=tk.LEFT).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        ttk.Separator(body).grid(row=1, column=0, columnspan=2,
                                 sticky=tk.EW, pady=(0, 10))

        cfg = _load_hf_config()

        # Kullanıcı adı
        ttk.Label(body, text="HuggingFace kullanıcı adı:").grid(
            row=2, column=0, sticky=tk.W, pady=4)
        user_var = tk.StringVar(value=cfg.get("username", ""))
        ttk.Entry(body, textvariable=user_var, width=30).grid(
            row=3, column=0, sticky=tk.EW, pady=(0, 10))

        # Token
        ttk.Label(body, text="Access Token (hf_...):").grid(
            row=4, column=0, sticky=tk.W, pady=4)
        token_var = tk.StringVar(value=cfg.get("token", ""))
        token_entry = ttk.Entry(body, textvariable=token_var, width=44, show="•")
        token_entry.grid(row=5, column=0, columnspan=2, sticky=tk.EW, pady=(0, 4))

        show_var = tk.BooleanVar(value=False)
        def toggle_show():
            token_entry.configure(show="" if show_var.get() else "•")
        ttk.Checkbutton(body, text="Token'ı göster",
                        variable=show_var, command=toggle_show).grid(
            row=6, column=0, sticky=tk.W, pady=(0, 10))

        ttk.Separator(body).grid(row=7, column=0, columnspan=2,
                                 sticky=tk.EW, pady=(0, 10))

        result_var = tk.StringVar(value="")
        ttk.Label(body, textvariable=result_var,
                  foreground="#0066aa", font=("Segoe UI", 9)).grid(
            row=8, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        btn_row = ttk.Frame(body)
        btn_row.grid(row=9, column=0, columnspan=2, sticky=tk.EW)

        def do_test():
            token = token_var.get().strip()
            user  = user_var.get().strip()
            if not token or not user:
                result_var.set("⚠  Kullanıcı adı ve token gerekli.")
                return
            result_var.set("⏳  Test ediliyor…")
            dlg.update()
            try:
                from huggingface_hub import HfApi
                api  = HfApi(token=token)
                info = api.whoami()
                result_var.set(f"✅  Bağlantı başarılı! ({info.get('name', user)})")
            except Exception as exc:
                result_var.set(f"❌  {str(exc)[:100]}")

        def do_save():
            save_hf_config(token_var.get().strip(), user_var.get().strip())
            # HFStore singleton'ı sıfırla
            import metin_atolyesi.core.hf_store as _hf
            _hf._hf_instance = None
            result_var.set("💾  Kaydedildi.")
            dlg.after(900, dlg.destroy)

        ttk.Button(btn_row, text="🔗 Bağlantıyı Test Et",
                   command=do_test).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="💾 Kaydet",
                   command=do_save).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="İptal",
                   command=dlg.destroy).pack(side=tk.RIGHT)

        self.wait_window(dlg)

    def simple_name_dialog(self, title: str, default: str) -> str | None:
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(dialog, text=title).pack(padx=14, pady=(14, 6))
        var = tk.StringVar(value=default)
        entry = ttk.Entry(dialog, textvariable=var, width=38)
        entry.pack(padx=14, pady=6)
        result: dict[str, str | None] = {"value": None}

        def ok() -> None:
            result["value"] = var.get().strip()
            dialog.destroy()

        ttk.Button(dialog, text="Tamam", command=ok).pack(pady=(6, 14))
        entry.focus_set()
        self.wait_window(dialog)
        return result["value"]

    # -----------------------------------------------------------------------
    # Son açılan dosyalar
    # -----------------------------------------------------------------------

    def _load_recent_files(self) -> None:
        import json
        try:
            if self._config_path.exists():
                data = json.loads(self._config_path.read_text(encoding="utf-8"))
                self.recent_files = [
                    f for f in data.get("recent_files", []) if Path(f).exists()
                ][:10]
        except Exception:
            self.recent_files = []

    def _save_recent_files(self) -> None:
        import json
        try:
            existing: dict = {}
            if self._config_path.exists():
                try:
                    existing = json.loads(self._config_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            existing["recent_files"] = self.recent_files[:10]
            self._config_path.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def _add_recent_file(self, path: str) -> None:
        path = str(path)
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:10]
        self._save_recent_files()
        if hasattr(self, "_recent_menu"):
            self._refresh_recent_menu()

    def _refresh_recent_menu(self) -> None:
        if not hasattr(self, "_recent_menu"):
            return
        try:
            self._recent_menu.delete(0, tk.END)
        except Exception:
            return
        if not self.recent_files:
            self._recent_menu.add_command(label="(Son açılan PDF yok)", state=tk.DISABLED)
            return
        for path in self.recent_files:
            self._recent_menu.add_command(
                label=Path(path).name,
                command=lambda p=path: self.load_sources([p]),
            )

    def _show_recent_pdf_menu(self) -> None:
        """'Son Açılanlar ▾' düğmesine basılınca açılır menü göster."""
        if not hasattr(self, "_recent_menu"):
            return
        try:
            # Düğmenin konumunu bul
            btn = self.focus_get()
            x = self.winfo_pointerx()
            y = self.winfo_pointery()
            self._recent_menu.tk_popup(x, y)
        finally:
            try:
                self._recent_menu.grab_release()
            except Exception:
                pass

    # -----------------------------------------------------------------------
    # PDF kayıt / farklı kayıt
    # -----------------------------------------------------------------------

    def save_pdf_dialog(self) -> None:
        """Mevcut işlenmiş PDF'yi orijinal kaynak konumuna yaz."""
        if not self.last_saved_pdf or not self.last_saved_pdf.exists():
            messagebox.showinfo("Dosyada Kaydet", "Önce bir PDF işlemi uygulayın.")
            return
        source = Path(self.project.source_path) if self.project.source_path else None
        if not source:
            messagebox.showinfo("Dosyada Kaydet", "Kaynak PDF bulunamadı.")
            return
        try:
            shutil.copy2(self.last_saved_pdf, source)
            self.status_var.set(f"PDF kaydedildi: {source}")
            messagebox.showinfo("Kaydedildi", f"PDF şu konuma kaydedildi:\n{source}")
        except Exception as exc:
            messagebox.showerror("Kayıt hatası", str(exc))

    def save_pdf_as_dialog(self) -> None:
        """Son kaydedilen (veya yüklenen) PDF'yi seçilen konuma kopyala."""
        source = self.last_saved_pdf or (
            Path(self.project.source_path) if self.project.source_path else None
        )
        if not source or not source.exists():
            messagebox.showinfo("Farklı Kaydet", "Kaydedilecek PDF yok.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialfile=source.name,
            filetypes=[("PDF", "*.pdf")],
            title="Farklı Kaydet",
        )
        if path:
            try:
                shutil.copy2(source, path)
                self._add_recent_file(path)
                self.status_var.set(f"Farklı kaydedildi: {path}")
                messagebox.showinfo("Kaydedildi", f"PDF şu konuma kaydedildi:\n{path}")
            except Exception as exc:
                messagebox.showerror("Kayıt hatası", str(exc))

    # -----------------------------------------------------------------------
    # PDF modu önizleme yardımcıları
    # -----------------------------------------------------------------------

    def _refresh_pdf_frame_preview(self) -> None:
        """PDF moduna geçince aktif sayfayı pdf_preview canvas'ına çiz."""
        if not hasattr(self, "pdf_preview"):
            return
        if self._pdf_preview_pages:
            idx = min(self._pdf_preview_page_index, len(self._pdf_preview_pages) - 1)
            self._draw_pdf_preview_image(self._pdf_preview_pages[idx])
            return
        page = self.current_page()
        if not page or not page.image_path or not Path(page.image_path).exists():
            self.pdf_preview.delete("all")
            self.pdf_preview.create_text(
                20, 20, text="PDF veya görsel yükleyin.", anchor=tk.NW, fill="#666"
            )
            return
        self._draw_pdf_preview_image(Path(page.image_path))

    def _draw_pdf_preview_image(self, image_path: Path) -> None:
        """pdf_preview canvas'ına görüntü çiz."""
        if not hasattr(self, "pdf_preview"):
            return
        try:
            image = Image.open(image_path)
            self.update_idletasks()
            cw = max(200, self.pdf_preview.winfo_width() - 10)
            ch = max(200, self.pdf_preview.winfo_height() - 10)
            w = int(cw * self._pdf_preview_zoom)
            h = int(ch * self._pdf_preview_zoom)
            image.thumbnail((w, h), Image.LANCZOS)
            self._pdf_preview_image = ImageTk.PhotoImage(image)
            self.pdf_preview.delete("all")
            self.pdf_preview.create_image(5, 5, image=self._pdf_preview_image, anchor=tk.NW)
            self.pdf_preview.configure(
                scrollregion=(0, 0, image.width + 10, image.height + 10)
            )
        except Exception as exc:
            self.pdf_preview.delete("all")
            self.pdf_preview.create_text(10, 10, text=str(exc), anchor=tk.NW, fill="red")

    def _show_pdf_tool_preview(self, images: list[Path]) -> None:
        """PDF araç işleminin sonucunu pdf_preview canvas'ında göster."""
        if not images:
            return
        cache_dir = self.project.root / "pdf_preview_cache"
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []
        for i, img in enumerate(images):
            dest = cache_dir / f"pdfprev_{i + 1:04d}{img.suffix or '.png'}"
            shutil.copy2(img, dest)
            copied.append(dest)
        self._pdf_preview_pages = copied
        self._pdf_preview_page_index = 0
        if copied:
            self._draw_pdf_preview_image(copied[0])

    def _zoom_pdf_preview(self, factor: float) -> None:
        self._pdf_preview_zoom = max(0.25, min(6.0, self._pdf_preview_zoom * factor))
        self._refresh_pdf_frame_preview()

    def _fit_pdf_preview(self) -> None:
        self._pdf_preview_zoom = 1.0
        self._pdf_preview_pages = []
        self._refresh_pdf_frame_preview()

    def _pdf_preview_nav(self, delta: int) -> None:
        if self._pdf_preview_pages:
            self._pdf_preview_page_index = max(
                0, min(len(self._pdf_preview_pages) - 1, self._pdf_preview_page_index + delta)
            )
            self._draw_pdf_preview_image(self._pdf_preview_pages[self._pdf_preview_page_index])
        else:
            self.goto_page(delta)
