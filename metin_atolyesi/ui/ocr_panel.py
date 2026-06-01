"""Metin Atölyesi — Tam OCR Çalışma Paneli.

Sekmeye gömülen, kendi içinde bütünlüklü bir OCR ortamı:
  • Üst kısım : tüm OCR ayarları
  • Orta kısım: sol PDF / sağ düzenlenebilir metin (paralel kaydırma)
  • Alt kısım : durum çubuğu
"""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, font as tkfont, messagebox, ttk
from typing import Callable

from PIL import Image, ImageTk

from metin_atolyesi.core.corrections_store import CorrectionsStore
from metin_atolyesi.core.ocr import (
    images_from_pdf,
    ocr_image,
    ocr_image_with_confidence,
    preprocess_image,
    run_multi_mode_ocr,
)
from metin_atolyesi.core.text_tools import find_suspicious_words, find_uncertain_words

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

LANG_PRESETS: list[tuple[str, str]] = [
    ("Türkçe",                       "tur"),
    ("İngilizce",                    "eng"),
    ("Türkçe + İngilizce",           "tur+eng"),
    ("EAT (Eski Anadolu Türkçesi)",  "tur"),
    ("Osmanlıca (Arap harfli)",      "ara"),
    ("Karahanlıca",                  "tur"),
    ("Çağatayca",                    "tur+ara"),
    ("Memlük Türkçesi",              "tur+ara"),
    ("Arapça",                       "ara"),
    ("Farsça",                       "fas"),
    ("Almanca",                      "deu"),
    ("Fransızca",                    "fra"),
    ("Özel (elle yaz)…",             "__custom__"),
]

LAYOUT_LABELS: list[str] = [
    "Tek sütun – Düzyazı",
    "Tek sütun – Beyit / Şiir",
    "İki sütun – Düzyazı",
    "İki sütun – Beyit",
    "Tablo / Dizin",
    "Karışık düzen",
]

LAYOUT_PSM: dict[str, int] = {
    "Tek sütun – Düzyazı":  6,
    "Tek sütun – Beyit / Şiir": 4,
    "İki sütun – Düzyazı":  3,
    "İki sütun – Beyit":    3,
    "Tablo / Dizin":        6,
    "Karışık düzen":        3,
}

TOOLTIPS: dict[str, str] = {
    "dil": (
        "OCR için kullanılacak dil.\n"
        "• Türkçe: Türkiye Türkçesi yazmaları\n"
        "• EAT: 13-15. yy Eski Anadolu Türkçesi\n"
        "• Osmanlıca: Arap harfli yazımlar ('ara' modeli)\n"
        "• Çağatayca/Memlük: karma model kullanır\n"
        "• Özel: tur+eng gibi elle girin"
    ),
    "motor": (
        "OCR motoru:\n"
        "• Otomatik: Çalışan en iyi motoru sırayla dener\n"
        "• Tesseract: Çok dilli, güven skoru verir\n"
        "• Windows OCR: Windows yerleşik, kurulum gerekmez\n"
        "• RapidOCR: Hafif alternatif (pip install rapidocr-onnxruntime)\n"
        "• EasyOCR: Arapça desteği (pip install easyocr)\n"
        "• Transkribus 📜: HTR derin öğrenme, Osmanlıca için en iyi açık kaynak\n"
        "  UNESCO & devlet arşivleri standardı — hesap gerekli\n"
        "• Claude ⚡: AI destekli, el yazması için en yüksek kalite"
    ),
    "mod": (
        "Görüntü ön işleme:\n"
        "• Çoklu deneme: 3 farklı mod dener, en iyiyi alır\n"
        "• Adaptif: Farklı aydınlık bölgeler için\n"
        "• Zorlu: Soluk, düşük kontrastlı metinler\n"
        "• Temiz: Zaten iyi kaliteli görüntüler\n"
        "• Deskew: Eğik sayfayı düzeltir\n"
        "• Gürültü gider: Kirli zemin temizler"
    ),
    "deskew": (
        "Tarama sırasında eğilen sayfaları otomatik düzeltir.\n"
        "Harflerin yatay olmaması OCR kalitesini belirgin düşürür."
    ),
    "güven": (
        "Tesseract'tan her kelime için ayrı güven skoru alır.\n"
        "Düşük güvenli kelimeler sarı/turuncu vurgulanır."
    ),
    "düzen": (
        "Sayfadaki metin yapısı:\n"
        "• Düzyazı: Normal paragraf metni\n"
        "• Beyit: Her dize ayrı satır (şiir)\n"
        "• İki sütun: Yan yana sütunlu sayfa\n"
        "• Tablo/Dizin: Sütunlu yapılar\n"
        "• Karışık: Birden fazla metin bloğu"
    ),
    "alan": (
        "Sayfanın yalnızca belirli bir bölgesinin OCR'ini yapar.\n"
        "Üst/alt bilgi, sayfa numarası, kenar notu gibi\n"
        "istenmeyen alanları dışarıda bırakmak için kullanın.\n"
        "Sol PDF görüntüsünde fareyle çizin."
    ),
    "kenar": (
        "Sayfanın kenarlarından kırpılacak miktarlar (mm).\n"
        "OCR yapılacak alanı daraltarak sayfa numarası,\n"
        "bölüm başlığı, alt bilgi gibi gereksiz kısımları\n"
        "metne girmesini engelleyin."
    ),
}

SUSPICIOUS_COLOR  = "#fff176"   # Sarı — şüpheli okuma
UNCERTAIN_COLOR   = "#ffe0b2"   # Turuncu — belirsiz okuma
USER_HIGHLIGHT    = "#b3e5fc"   # Mavi — kullanıcı vurgusu


# ---------------------------------------------------------------------------
# Tooltip yardımcısı
# ---------------------------------------------------------------------------

class _Tooltip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self._widget = widget
        self._text = text
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event=None) -> None:
        if self._tip:
            return
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tip = tk.Toplevel(self._widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(
            self._tip, text=self._text, justify=tk.LEFT,
            background="#fffde7", relief=tk.SOLID, borderwidth=1,
            font=("Segoe UI", 9), wraplength=320, padx=6, pady=4,
        )
        lbl.pack()

    def _hide(self, _event=None) -> None:
        if self._tip:
            self._tip.destroy()
            self._tip = None


def tip(widget: tk.Widget, key: str) -> None:
    if key in TOOLTIPS:
        _Tooltip(widget, TOOLTIPS[key])


# ---------------------------------------------------------------------------
# Ana panel
# ---------------------------------------------------------------------------

class OcrPanel(ttk.Frame):
    """Tam OCR çalışma alanı — bütün OCR işlevleri bu sekmede."""

    def __init__(self, master, project, corrections: CorrectionsStore,
                 on_text_saved: Callable | None = None) -> None:
        super().__init__(master)
        self.project = project
        self.corrections = corrections
        self.on_text_saved = on_text_saved   # (page_index, text) → None

        # Durum
        self._ocr_thread: threading.Thread | None = None
        self._cancel_flag = threading.Event()
        self._paused_flag = threading.Event()
        self._syncing_scroll = False
        self._ocr_region: tuple[float, float, float, float] | None = None  # mm (L,T,R,B)
        self._region_draw_mode = False
        self._region_start: tuple[int, int] | None = None
        self._region_rect_id: int | None = None
        self._preview_image: ImageTk.PhotoImage | None = None
        self._preview_original: Image.Image | None = None
        self._zoom = 1.0
        self._fit_mode = True
        self._hand_mode = False
        self._pan_start: tuple[int, int] | None = None
        self._user_fmt_tags: list[str] = []  # kullanıcının uyguladığı format etiketleri

        # Görünüm modu
        self._view_mode_var = tk.StringVar(value="tek_sayfa")
        self._filmstrip_images: list = []          # ImageTk referansları (GC koruması)
        self._filmstrip_page_tops: list[int] = []  # her sayfanın canvas'taki y başlangıcı
        self._filmstrip_total_h: int = 0
        self._fs_debounce_id: str | None = None    # scroll sonrası sayfa tespiti

        # El Yazması meta (wizard'dan veya kütüphaneden aktarılır)
        self._ms_meta: dict = {}
        self._ms_bar_visible = tk.BooleanVar(value=False)
        self._on_open_wizard_cb: Callable | None = None  # main_window'dan atanır
        self._doc_mode_var = tk.StringVar(value="normal")
        self._ms_summary_var = tk.StringVar(value="")

        self._build()
        self._setup_text_tags()

    # -----------------------------------------------------------------------
    # Yapı
    # -----------------------------------------------------------------------

    def _build(self) -> None:
        # Üst ayarlar paneli (kompakt — 2+1 satır)
        self._settings_frame = ttk.Frame(self, padding=(6, 4, 6, 2))
        self._settings_frame.pack(fill=tk.X)
        self._build_settings()

        # El Yazması meta çubuğu — genişletilebilir
        self._ms_bar_frame = ttk.Frame(self, padding=(6, 0, 6, 2))
        self._ms_bar_frame.pack(fill=tk.X)
        self._build_ms_meta_bar()

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=6)

        # Orta: paralel görünüm
        self._paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self._paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=(4, 0))
        left_frame  = ttk.Frame(self._paned)
        right_frame = ttk.Frame(self._paned)
        self._paned.add(left_frame,  weight=1)
        self._paned.add(right_frame, weight=1)
        self._build_pdf_pane(left_frame)
        self._build_text_pane(right_frame)

        # Alt durum çubuğu
        status_bar = ttk.Frame(self)
        status_bar.pack(fill=tk.X, padx=6, pady=(0, 4))
        self._status_var = tk.StringVar(value="Hazır")
        ttk.Label(status_bar, textvariable=self._status_var,
                  style="Status.TLabel").pack(side=tk.LEFT)
        self._page_var = tk.StringVar(value="0/0")
        ttk.Label(status_bar, textvariable=self._page_var).pack(side=tk.RIGHT)

    # -----------------------------------------------------------------------
    # Ayarlar paneli
    # -----------------------------------------------------------------------

    def _build_settings(self) -> None:
        """Kompakt 2 satır: Üst = dil/motor/ön işlem + başlat/durdur,
                            Alt  = kapsam/düzen + kenar kırpma/alan seç."""
        sf = self._settings_frame

        # ── Satır 1: Dil · Motor · Ön işlem · Deskew · Güven | ▶ ⏸ ⏹ Progress ──
        r1 = ttk.Frame(sf)
        r1.pack(fill=tk.X, pady=(0, 3))

        ttk.Label(r1, text="Dil:").pack(side=tk.LEFT)
        self._lang_display_var = tk.StringVar(value="Türkçe + İngilizce")
        self._lang_code_var    = tk.StringVar(value="tur+eng")
        lang_labels = [lbl for lbl, _ in LANG_PRESETS]
        lang_cb = ttk.Combobox(r1, textvariable=self._lang_display_var,
                               values=lang_labels, state="readonly", width=20)
        lang_cb.pack(side=tk.LEFT, padx=(2, 6))
        lang_cb.bind("<<ComboboxSelected>>", self._on_lang_select)
        tip(lang_cb, "dil")

        self._custom_lang_var = tk.StringVar(value="tur")
        self._custom_lang_entry = ttk.Entry(r1, textvariable=self._custom_lang_var, width=12)
        self._custom_lang_entry.pack(side=tk.LEFT, padx=(0, 6))
        self._custom_lang_entry.pack_forget()

        ttk.Label(r1, text="Motor:").pack(side=tk.LEFT)
        self._engine_var = tk.StringVar(value="otomatik")
        engine_cb = ttk.Combobox(
            r1, textvariable=self._engine_var,
            values=["otomatik", "tesseract", "windows", "rapidocr", "easyocr",
                    "transkribus 📜", "claude ⚡"],
            state="readonly", width=15,
        )
        engine_cb.pack(side=tk.LEFT, padx=(2, 6))
        engine_cb.bind("<<ComboboxSelected>>", self._on_engine_select)
        tip(engine_cb, "motor")

        ttk.Label(r1, text="Ön işlem:").pack(side=tk.LEFT)
        self._preprocess_var = tk.StringVar(value="çoklu deneme")
        pre_cb = ttk.Combobox(
            r1, textvariable=self._preprocess_var, state="readonly", width=14,
            values=["çoklu deneme", "adaptif", "zorlu", "dengeli", "temiz",
                    "deskew", "gürültü gider"],
        )
        pre_cb.pack(side=tk.LEFT, padx=(2, 6))
        tip(pre_cb, "mod")

        self._deskew_var = tk.BooleanVar(value=False)
        dsk_cb = ttk.Checkbutton(r1, text="Deskew", variable=self._deskew_var)
        dsk_cb.pack(side=tk.LEFT, padx=(0, 3))
        tip(dsk_cb, "deskew")

        self._confidence_var = tk.BooleanVar(value=True)
        conf_cb = ttk.Checkbutton(r1, text="Güven", variable=self._confidence_var)
        conf_cb.pack(side=tk.LEFT, padx=(0, 4))
        tip(conf_cb, "güven")

        # Ayırıcı + OCR kontrol düğmeleri + ilerleme çubuğu (sağ)
        ttk.Separator(r1, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        self._btn_start = ttk.Button(r1, text="▶ Başlat",   command=self._start_ocr,  width=10)
        self._btn_start.pack(side=tk.LEFT, padx=(0, 2))
        self._btn_pause = ttk.Button(r1, text="⏸ Duraklat", command=self._pause_ocr,  width=10,
                                     state=tk.DISABLED)
        self._btn_pause.pack(side=tk.LEFT, padx=2)
        self._btn_stop  = ttk.Button(r1, text="⏹ Durdur",  command=self._stop_ocr,   width=10,
                                     state=tk.DISABLED)
        self._btn_stop.pack(side=tk.LEFT, padx=2)
        self._progress_var = tk.DoubleVar(value=0)
        self._progress_bar = ttk.Progressbar(r1, variable=self._progress_var,
                                             maximum=100, length=160)
        self._progress_bar.pack(side=tk.LEFT, padx=(8, 4))
        self._progress_lbl = tk.StringVar(value="")
        ttk.Label(r1, textvariable=self._progress_lbl, width=10).pack(side=tk.LEFT)

        # ── Satır 2: Kapsam · Sayfa No · Düzen | Kenar kırpma · Alan seçimi ──
        r2 = ttk.Frame(sf)
        r2.pack(fill=tk.X, pady=(0, 2))

        ttk.Label(r2, text="Sayfalar:").pack(side=tk.LEFT)
        self._scope_var = tk.StringVar(value="tümü")
        for val, lbl in [("tümü", "Tümü"), ("görünen", "Görünen"), ("seçim", "Seçim")]:
            ttk.Radiobutton(r2, text=lbl, variable=self._scope_var, value=val,
                            command=self._on_scope_change).pack(side=tk.LEFT, padx=2)
        self._page_sel_var = tk.StringVar(value="")
        self._page_sel_entry = ttk.Entry(r2, textvariable=self._page_sel_var, width=12)
        self._page_sel_entry.pack(side=tk.LEFT, padx=(2, 6))
        self._page_sel_entry.configure(state=tk.DISABLED)

        ttk.Label(r2, text="Düzen:").pack(side=tk.LEFT)
        self._layout_var = tk.StringVar(value="Tek sütun – Düzyazı")
        layout_cb = ttk.Combobox(r2, textvariable=self._layout_var,
                                 values=LAYOUT_LABELS, state="readonly", width=18)
        layout_cb.pack(side=tk.LEFT, padx=(2, 6))
        tip(layout_cb, "düzen")

        ttk.Separator(r2, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Label(r2, text="Kenar (mm):").pack(side=tk.LEFT)
        tip(ttk.Label(r2, text="❓"), "kenar")
        self._crop_left   = tk.DoubleVar(value=0)
        self._crop_top    = tk.DoubleVar(value=0)
        self._crop_right  = tk.DoubleVar(value=0)
        self._crop_bottom = tk.DoubleVar(value=0)
        for short, var in [("S", self._crop_left), ("Ü", self._crop_top),
                           ("Sa", self._crop_right), ("A", self._crop_bottom)]:
            ttk.Label(r2, text=f" {short}:").pack(side=tk.LEFT)
            ttk.Spinbox(r2, from_=0, to=100, textvariable=var,
                        increment=1, width=4).pack(side=tk.LEFT)

        ttk.Button(r2, text="🔲 Alan",  command=self._enable_region_select).pack(side=tk.LEFT, padx=(8, 2))
        ttk.Button(r2, text="✖ Temizle", command=self._clear_region).pack(side=tk.LEFT, padx=2)
        tip(ttk.Label(r2, text=" ❓"), "alan")

    # -----------------------------------------------------------------------
    # El Yazması meta çubuğu
    # -----------------------------------------------------------------------

    def _build_ms_meta_bar(self) -> None:
        """OCR öncesi belge türü ve el yazması yapılandırma çubuğu."""
        bf = self._ms_bar_frame

        # ── Satır: Belge türü radyoları | ayırıcı | toggle | özet ─────────
        header_row = ttk.Frame(bf)
        header_row.pack(fill=tk.X, pady=(2, 0))

        ttk.Label(header_row, text="Belge türü:").pack(side=tk.LEFT)
        ttk.Radiobutton(
            header_row, text="Normal PDF  (makale / kitap / tez)",
            variable=self._doc_mode_var, value="normal",
            command=self._on_doc_mode_change,
        ).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Radiobutton(
            header_row, text="El Yazması",
            variable=self._doc_mode_var, value="manuscript",
            command=self._on_doc_mode_change,
        ).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Separator(header_row, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        self._ms_toggle_btn = ttk.Button(
            header_row, text="⚙ El Yazması Ayarları  ▼",
            command=self._toggle_ms_bar, width=26, state=tk.DISABLED,
        )
        self._ms_toggle_btn.pack(side=tk.LEFT)

        # Aktif kriter özeti
        self._ms_summary_lbl = ttk.Label(
            header_row, textvariable=self._ms_summary_var,
            foreground="#2a7a2a", font=("Segoe UI", 9, "italic"))
        self._ms_summary_lbl.pack(side=tk.LEFT, padx=(12, 0))

        # ── Genişletilebilir içerik (başlangıçta gizli, sağa dayalı) ─────
        self._ms_detail_frame = ttk.Frame(bf)
        self._build_ms_detail(self._ms_detail_frame)

    def _build_ms_detail(self, parent: ttk.Frame) -> None:
        """Genişletilmiş el yazması ayarları satırı."""
        # Satır 1: Eser adı + Ana alanlar
        r1 = ttk.Frame(parent)
        r1.pack(fill=tk.X, pady=(4, 2))

        ttk.Label(r1, text="Eser Adı:").pack(side=tk.LEFT)
        self._ms_eser_var = tk.StringVar()
        ttk.Entry(r1, textvariable=self._ms_eser_var, width=24).pack(
            side=tk.LEFT, padx=(2, 8))

        ttk.Label(r1, text="Alan:").pack(side=tk.LEFT)
        self._ms_alan_var = tk.StringVar(value="Osmanlıca")
        try:
            from metin_atolyesi.core.manuscript_library import ALANLAR
            alan_vals = ALANLAR
        except Exception:
            alan_vals = ["Osmanlıca", "Arapça", "Farsça", "Türkçe"]
        ttk.Combobox(r1, textvariable=self._ms_alan_var,
                     values=alan_vals, state="readonly", width=14).pack(
            side=tk.LEFT, padx=(2, 8))

        ttk.Label(r1, text="Dönem:").pack(side=tk.LEFT)
        self._ms_donem_var = tk.StringVar(value="Belirsiz")
        try:
            from metin_atolyesi.core.manuscript_library import DONEMLER
            donem_vals = DONEMLER
        except Exception:
            donem_vals = ["Belirsiz", "13. yy", "14. yy", "15. yy", "16. yy",
                          "17. yy", "18. yy", "19. yy"]
        ttk.Combobox(r1, textvariable=self._ms_donem_var,
                     values=donem_vals, state="readonly", width=12).pack(
            side=tk.LEFT, padx=(2, 8))

        # Satır 2: Yazı türü + Hareke + Aksiyonlar
        r2 = ttk.Frame(parent)
        r2.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(r2, text="Yazı Türü:").pack(side=tk.LEFT)
        self._ms_yazi_var = tk.StringVar(value="Nesih")
        try:
            from metin_atolyesi.core.manuscript_library import YAZI_TURLERI
            yazi_vals = YAZI_TURLERI
        except Exception:
            yazi_vals = ["Nesih", "Talik", "Sülüs", "Rika", "Divani", "Küfi"]
        ttk.Combobox(r2, textvariable=self._ms_yazi_var,
                     values=yazi_vals, state="readonly", width=12).pack(
            side=tk.LEFT, padx=(2, 8))

        ttk.Label(r2, text="Hareke:").pack(side=tk.LEFT)
        self._ms_hareke_var = tk.StringVar(value="Harekesiz")
        try:
            from metin_atolyesi.core.manuscript_library import HAREKE_DURUMLARI
            hareke_vals = HAREKE_DURUMLARI
        except Exception:
            hareke_vals = ["Harekesiz", "Tam harekeli", "Kısmen harekeli"]
        ttk.Combobox(r2, textvariable=self._ms_hareke_var,
                     values=hareke_vals, state="readonly", width=16).pack(
            side=tk.LEFT, padx=(2, 12))

        ttk.Separator(r2, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        # Kütüphaneden yükle
        ttk.Button(r2, text="📚 Kütüphaneden Yükle",
                   command=self._load_ms_from_library).pack(side=tk.LEFT, padx=2)

        # Tam sihirbaz
        ttk.Button(r2, text="📜 Tam Yapılandır…",
                   command=self._open_ms_wizard).pack(side=tk.LEFT, padx=2)

        # Ayarları uygula butonu
        ttk.Button(r2, text="✓ Uygula",
                   command=self._apply_ms_meta).pack(side=tk.LEFT, padx=2)

    def _on_doc_mode_change(self) -> None:
        """Normal PDF / El Yazması modu seçimi değişince."""
        is_ms = (self._doc_mode_var.get() == "manuscript")
        self._ms_toggle_btn.configure(state=tk.NORMAL if is_ms else tk.DISABLED)
        if not is_ms:
            # Normal PDF → detail paneli kapat ve ms_meta'yı temizle
            if self._ms_bar_visible.get():
                self._ms_detail_frame.pack_forget()
                self._ms_bar_visible.set(False)
                self._ms_toggle_btn.configure(text="⚙ El Yazması Ayarları  ▼")
            self._ms_meta = {}
            self._ms_summary_var.set("")
        else:
            # El Yazması → mevcut meta varsa özeti güncelle
            self._update_ms_summary()

    def _toggle_ms_bar(self) -> None:
        """El yazması ayarları detayını aç/kapat (sağa dayalı — row 3)."""
        if self._ms_bar_visible.get():
            self._ms_detail_frame.pack_forget()
            self._ms_bar_visible.set(False)
            self._ms_toggle_btn.configure(text="⚙ El Yazması Ayarları  ▼")
        else:
            self._ms_detail_frame.pack(side=tk.RIGHT, anchor=tk.NE)
            self._ms_bar_visible.set(True)
            self._ms_toggle_btn.configure(text="⚙ El Yazması Ayarları  ▲")

    def _apply_ms_meta(self) -> None:
        """Arayüzdeki değerleri _ms_meta sözlüğüne işle ve Claude OCR'e hazırla."""
        self._ms_meta.update({
            "eser_adi":  self._ms_eser_var.get().strip(),
            "alan":      self._ms_alan_var.get(),
            "donem":     self._ms_donem_var.get(),
            "yazi_turu": self._ms_yazi_var.get(),
            "hareke":    self._ms_hareke_var.get(),
        })
        # El Yazması moduna otomatik geç
        if hasattr(self, "_doc_mode_var"):
            self._doc_mode_var.set("manuscript")
            self._ms_toggle_btn.configure(state=tk.NORMAL)
        self._update_ms_summary()

    def _update_ms_summary(self) -> None:
        """Aktif kriterleri özetler; Claude OCR bu bilgileri kullanacak."""
        m = self._ms_meta
        if not m or self._doc_mode_var.get() != "manuscript":
            self._ms_summary_var.set("")
            return

        parts: list[str] = []
        if eser := m.get("eser_adi", ""):
            parts.append(eser)
        if yazi := m.get("yazi_turu", ""):
            parts.append(yazi)
        if hareke := m.get("hareke", ""):
            parts.append(hareke)

        # Ek kriterler sayısı
        ekstra = 0
        if m.get("imla_secimler"):
            ekstra += len(m["imla_secimler"])
        if m.get("trans_isaretleri"):
            ekstra += len([t for t in m["trans_isaretleri"] if t.get("isaret")])
        if m.get("aktarim_ilkeleri"):
            ekstra += 1
        if m.get("imla_serbest"):
            ekstra += 1

        ozet = "  |  ".join(parts) if parts else "Yapılandırıldı"
        if ekstra:
            ozet += f"  +{ekstra} ek kriter"
        ozet += "  ✓ Claude OCR'e uygulanacak"
        self._ms_summary_var.set(ozet)

    def set_manuscript_meta(self, meta: dict) -> None:
        """Wizard veya kütüphaneden gelen meta verisini uygular.

        Tüm kriterler (imla, yapı, paleografi, transkripsiyon işaretleri…)
        `_ms_meta`'da saklanır ve Claude OCR çağrısında prompt'a eklenir.
        """
        self._ms_meta = dict(meta)

        # Belge modunu el yazmasına geçir
        if hasattr(self, "_doc_mode_var"):
            self._doc_mode_var.set("manuscript")
            self._ms_toggle_btn.configure(state=tk.NORMAL)

        # Kompakt UI alanlarını güncelle
        if hasattr(self, "_ms_eser_var"):
            self._ms_eser_var.set(meta.get("eser_adi", ""))
            self._ms_alan_var.set(meta.get("alan", "Osmanlıca"))
            self._ms_donem_var.set(meta.get("donem", "Belirsiz"))
            self._ms_yazi_var.set(meta.get("yazi_turu", "Nesih"))
            self._ms_hareke_var.set(meta.get("hareke", "Harekesiz"))

        self._update_ms_summary()

    def _load_ms_from_library(self) -> None:
        """El yazması kütüphanesinden mevcut bir eseri yükler."""
        try:
            from metin_atolyesi.core.manuscript_library import get_library
        except ImportError:
            from tkinter import messagebox
            messagebox.showwarning("Hata", "Kütüphane modülü yüklenemedi.",
                                   parent=self.winfo_toplevel())
            return

        lib = get_library()
        entries = lib.list_entries()
        if not entries:
            from tkinter import messagebox
            messagebox.showinfo("Kütüphane Boş",
                                "Henüz öğrenilmiş el yazması yok.\n"
                                "'📜 El Yazması Öğret' butonuyla bir eser ekleyin.",
                                parent=self.winfo_toplevel())
            return

        # Seçim penceresi
        dlg = tk.Toplevel(self.winfo_toplevel())
        dlg.title("El Yazması Seç")
        dlg.geometry("520x340")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()

        ttk.Label(dlg, text="Kütüphanedeki eserlerden birini seçin:",
                  style="Header.TLabel").pack(anchor=tk.W, padx=12, pady=(10, 4))

        lb_frame = ttk.Frame(dlg)
        lb_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        sb = ttk.Scrollbar(lb_frame)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        lb = tk.Listbox(lb_frame, yscrollcommand=sb.set,
                        font=("Segoe UI", 10), activestyle="none",
                        selectmode=tk.SINGLE)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.configure(command=lb.yview)

        for e in entries:
            lb.insert(tk.END, f"  {e.get('eser_adi', '—')}  "
                              f"[{e.get('yazi_turu', '')}]  "
                              f"{e.get('donem', '')}")

        def _apply():
            sel = lb.curselection()
            if not sel:
                return
            entry = entries[sel[0]]
            self.set_manuscript_meta(entry)
            dlg.destroy()

        btn_row = ttk.Frame(dlg)
        btn_row.pack(fill=tk.X, padx=12, pady=(4, 10))
        ttk.Button(btn_row, text="✓ Seç", command=_apply).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="İptal", command=dlg.destroy).pack(side=tk.RIGHT)
        lb.bind("<Double-Button-1>", lambda _: _apply())

    def _open_ms_wizard(self) -> None:
        """Tam sihirbaz moduna geçer (main_window üzerinden)."""
        if self._on_open_wizard_cb:
            self._on_open_wizard_cb()

    # -----------------------------------------------------------------------
    # PDF bölmesi (sol)
    # -----------------------------------------------------------------------

    def _build_pdf_pane(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent)
        header.pack(fill=tk.X)
        ttk.Label(header, text="PDF Görüntüsü", style="Header.TLabel").pack(side=tk.LEFT)

        nav = ttk.Frame(parent)
        nav.pack(fill=tk.X, pady=(2, 0))
        ttk.Button(nav, text="◀", width=3, command=lambda: self._go_page(-1)).pack(side=tk.LEFT)
        ttk.Button(nav, text="▶", width=3, command=lambda: self._go_page(1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav, text="−", width=3, command=lambda: self._zoom_by(0.85)).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav, text="+", width=3, command=lambda: self._zoom_by(1.18)).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav, text="Sığdır", width=6, command=self._fit_page).pack(side=tk.LEFT, padx=2)

        # İmleç modu
        self._cursor_mode = tk.StringVar(value="hand")
        ttk.Radiobutton(nav, text="✋", variable=self._cursor_mode,
                        value="hand",   command=self._update_cursor, width=3).pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(nav, text="↖",  variable=self._cursor_mode,
                        value="select", command=self._update_cursor, width=3).pack(side=tk.LEFT, padx=2)

        # Görünüm modu
        ttk.Separator(nav, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Label(nav, text="Görünüm:").pack(side=tk.LEFT)
        for val, lbl in [("tek_sayfa", "📄 Tek Sayfa"), ("film_seridi", "🎞 Film Şeridi")]:
            ttk.Radiobutton(
                nav, text=lbl, variable=self._view_mode_var, value=val,
                command=self._on_view_mode_change,
            ).pack(side=tk.LEFT, padx=(2, 0))

        canvas_frame = ttk.Frame(parent)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        self._canvas = tk.Canvas(canvas_frame, bg="#f0f0f0",
                                 highlightthickness=1, highlightbackground="#ccc")
        self._canvas_vscroll_widget = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        hscroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        self._canvas.configure(yscrollcommand=self._on_canvas_yscroll,
                               xscrollcommand=hscroll.set)
        self._canvas_vscroll_widget.configure(command=self._canvas_yview_cmd)
        hscroll.configure(command=self._canvas.xview)
        hscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self._canvas_vscroll_widget.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._canvas.bind("<ButtonPress-1>",   self._on_canvas_press)
        self._canvas.bind("<B1-Motion>",        self._on_canvas_drag)
        self._canvas.bind("<ButtonRelease-1>",  self._on_canvas_release)
        self._canvas.bind("<Control-MouseWheel>", self._on_ctrl_wheel)
        self._canvas.bind("<MouseWheel>",       self._on_canvas_wheel)

    def _on_canvas_yscroll(self, *args) -> None:
        self._canvas_vscroll_widget.set(*args) if hasattr(self, "_canvas_vscroll_widget") else None
        if self._view_mode_var.get() == "film_seridi":
            return   # film şeridinde metin eşzamanlaması yok
        if not self._syncing_scroll:
            self._syncing_scroll = True
            frac = float(args[0]) if len(args) >= 1 else self._canvas.yview()[0]
            self._text.yview_moveto(frac)
            self._syncing_scroll = False

    def _canvas_yview_cmd(self, *args) -> None:
        self._canvas.yview(*args)
        if self._view_mode_var.get() == "film_seridi":
            return
        if not self._syncing_scroll:
            self._syncing_scroll = True
            self._text.yview_moveto(self._canvas.yview()[0])
            self._syncing_scroll = False

    # -----------------------------------------------------------------------
    # Metin bölmesi (sağ)
    # -----------------------------------------------------------------------

    def _build_text_pane(self, parent: ttk.Frame) -> None:
        self._text_pane_header = ttk.Label(
            parent, text="OCR Metni (Düzenlenebilir)", style="Header.TLabel")
        self._text_pane_header.pack(anchor=tk.W)

        # ── Satır içi Bul / Değiştir çubuğu (Ctrl+F ile aç/kapat) ─────────
        self._search_bar = ttk.Frame(parent)
        # (başlangıçta gizli — Ctrl+F ile açılır)

        sb = self._search_bar
        ttk.Label(sb, text="Ara:").pack(side=tk.LEFT, padx=(0, 2))
        self._search_find_var = tk.StringVar()
        find_entry = ttk.Entry(sb, textvariable=self._search_find_var, width=18)
        find_entry.pack(side=tk.LEFT, padx=(0, 2))
        find_entry.bind("<Return>", lambda _e: self._search_find_next())
        find_entry.bind("<Escape>", lambda _e: self._toggle_search_bar())
        self._find_entry = find_entry

        ttk.Button(sb, text="◀", width=2,
                   command=lambda: self._search_find_next(backward=True)).pack(side=tk.LEFT, padx=1)
        ttk.Button(sb, text="▶", width=2,
                   command=self._search_find_next).pack(side=tk.LEFT, padx=1)

        ttk.Separator(sb, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Label(sb, text="Değiştir:").pack(side=tk.LEFT, padx=(0, 2))
        self._search_replace_var = tk.StringVar()
        ttk.Entry(sb, textvariable=self._search_replace_var, width=18).pack(side=tk.LEFT, padx=(0, 2))

        ttk.Button(sb, text="Değiştir",        command=self._search_replace_one).pack(side=tk.LEFT, padx=1)
        ttk.Button(sb, text="Tümünü Değiştir", command=self._search_replace_all).pack(side=tk.LEFT, padx=1)

        self._search_status_var = tk.StringVar(value="")
        ttk.Label(sb, textvariable=self._search_status_var,
                  foreground="#666", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=6)

        ttk.Button(sb, text="✕", width=2,
                   command=self._toggle_search_bar).pack(side=tk.RIGHT, padx=2)

        # ── Biçim araç çubuğu ────────────────────────────────────────────
        fmt_bar = ttk.Frame(parent)
        fmt_bar.pack(fill=tk.X, pady=(2, 2))
        self._build_format_toolbar(fmt_bar)

        # ── Metin alanı ────────────────────────────────────────────────────
        txt_frame = ttk.Frame(parent)
        txt_frame.pack(fill=tk.BOTH, expand=True)
        self._text = tk.Text(
            txt_frame, wrap=tk.WORD, undo=True,
            font=("Segoe UI", 11), spacing1=2, spacing3=4,
            relief=tk.FLAT, borderwidth=1,
        )
        self._text_vscroll = ttk.Scrollbar(txt_frame, orient=tk.VERTICAL,
                                           command=self._text_yview_cmd)
        self._text.configure(yscrollcommand=self._on_text_yscroll)
        self._text_vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._text.bind("<Button-3>", self._show_text_menu)
        self._text.bind("<<Modified>>", self._on_text_modified)
        self._text.bind("<Control-f>", lambda _e: (self._toggle_search_bar(), "break")[1])

        # ── Aksiyon çubuğu ──────────────────────────────────────────────
        act_bar = ttk.Frame(parent)
        act_bar.pack(fill=tk.X, pady=(2, 0))
        ttk.Button(act_bar, text="💾 Değişiklikleri Kaydet",
                   command=self._save_text).pack(side=tk.LEFT, padx=2)
        ttk.Button(act_bar, text="✅ Sayfadaki Vurguları Kaldır",
                   command=self._clear_page_highlights).pack(side=tk.LEFT, padx=2)
        ttk.Button(act_bar, text="✅ Tüm Vurguları Kaldır",
                   command=self._clear_all_highlights).pack(side=tk.LEFT, padx=2)

    def _text_yview_cmd(self, *args) -> None:
        self._text.yview(*args)
        if not self._syncing_scroll:
            self._syncing_scroll = True
            self._canvas.yview_moveto(self._text.yview()[0])
            self._syncing_scroll = False

    def _on_text_yscroll(self, *args) -> None:
        self._text_vscroll.set(*args)
        if not self._syncing_scroll:
            self._syncing_scroll = True
            self._canvas.yview_moveto(float(args[0]))
            self._syncing_scroll = False

    # -----------------------------------------------------------------------
    # Biçim araç çubuğu
    # -----------------------------------------------------------------------

    def _build_format_toolbar(self, parent: ttk.Frame) -> None:
        # Yazı tipi
        available_fonts = list(tkfont.families())
        available_fonts.sort()
        preferred = ["Segoe UI", "Arial", "Times New Roman", "Courier New", "Calibri"]
        ordered = [f for f in preferred if f in available_fonts] + \
                  [f for f in available_fonts if f not in preferred]
        self._font_family = tk.StringVar(value="Segoe UI")
        ttk.Combobox(parent, textvariable=self._font_family,
                     values=ordered, width=16).pack(side=tk.LEFT, padx=1)

        # Yazı boyutu
        self._font_size = tk.IntVar(value=11)
        ttk.Spinbox(parent, from_=6, to=72, textvariable=self._font_size,
                    width=4, command=self._apply_font).pack(side=tk.LEFT, padx=1)
        self._font_family.trace_add("write", lambda *_: self._apply_font())

        # Stil düğmeleri
        for symbol, tag in [("B", "fmt_bold"), ("İ", "fmt_italic"), ("A̲", "fmt_underline")]:
            ttk.Button(parent, text=symbol, width=3,
                       command=lambda t=tag: self._toggle_fmt_tag(t)).pack(side=tk.LEFT, padx=1)

        ttk.Separator(parent, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)

        # Yazı rengi
        self._fg_color = "#000000"
        self._btn_fg = tk.Button(parent, text="A", fg="#000000", width=2,
                                 font=("Segoe UI", 9, "bold"),
                                 command=self._choose_fg_color,
                                 relief=tk.FLAT, borderwidth=1)
        self._btn_fg.pack(side=tk.LEFT, padx=1)

        # Vurgu rengi (kullanıcı)
        self._hl_color = "#b3e5fc"
        self._btn_hl = tk.Button(parent, text="▌", bg="#b3e5fc", width=2,
                                 command=self._choose_hl_color,
                                 relief=tk.FLAT, borderwidth=1)
        self._btn_hl.pack(side=tk.LEFT, padx=1)

        ttk.Separator(parent, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)

        # Hizalama
        for symbol, align in [("≡", "left"), ("☰", "center"), ("≡", "right")]:
            ttk.Button(parent, text=symbol, width=3,
                       command=lambda a=align: self._apply_alignment(a)).pack(side=tk.LEFT, padx=1)

        ttk.Separator(parent, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)

        # Satır aralığı
        ttk.Label(parent, text="Aralık:").pack(side=tk.LEFT)
        self._line_spacing = tk.DoubleVar(value=1.0)
        ttk.Spinbox(parent, from_=0.8, to=3.0, increment=0.1,
                    textvariable=self._line_spacing,
                    width=4, command=self._apply_line_spacing).pack(side=tk.LEFT, padx=1)

    # -----------------------------------------------------------------------
    # Text etiketleri
    # -----------------------------------------------------------------------

    def _setup_text_tags(self) -> None:
        self._text.tag_configure("suspicious",
                                 background=SUSPICIOUS_COLOR, borderwidth=1,
                                 relief=tk.SOLID)
        self._text.tag_configure("uncertain",
                                 background=UNCERTAIN_COLOR)
        self._text.tag_configure("confirmed",
                                 background="")
        self._text.tag_configure("user_highlight",
                                 background=USER_HIGHLIGHT)
        self._text.tag_configure("fmt_bold",
                                 font=("Segoe UI", 11, "bold"))
        self._text.tag_configure("fmt_italic",
                                 font=("Segoe UI", 11, "italic"))
        self._text.tag_configure("fmt_underline",
                                 underline=True)
        self._text.tag_configure("align_center", justify=tk.CENTER)
        self._text.tag_configure("align_right",  justify=tk.RIGHT)
        self._text.tag_configure("align_left",   justify=tk.LEFT)
        # Seçim önceliği
        self._text.tag_raise("suspicious")
        self._text.tag_raise("uncertain")
        self._text.tag_raise("sel")

    # -----------------------------------------------------------------------
    # Biçimlendirme uygulama
    # -----------------------------------------------------------------------

    def _apply_font(self) -> None:
        family = self._font_family.get()
        size   = self._font_size.get()
        self._text.configure(font=(family, size))

    def _toggle_fmt_tag(self, tag: str) -> None:
        try:
            s = self._text.index(tk.SEL_FIRST)
            e = self._text.index(tk.SEL_LAST)
        except tk.TclError:
            return
        if tag in self._text.tag_names(s):
            self._text.tag_remove(tag, s, e)
        else:
            self._text.tag_add(tag, s, e)

    def _choose_fg_color(self) -> None:
        color = colorchooser.askcolor(color=self._fg_color, title="Yazı Rengi")[1]
        if not color:
            return
        self._fg_color = color
        self._btn_fg.configure(fg=color)
        try:
            s = self._text.index(tk.SEL_FIRST)
            e = self._text.index(tk.SEL_LAST)
            tag = f"fg_{color.replace('#','')}"
            self._text.tag_configure(tag, foreground=color)
            self._text.tag_add(tag, s, e)
        except tk.TclError:
            pass

    def _choose_hl_color(self) -> None:
        color = colorchooser.askcolor(color=self._hl_color, title="Vurgu Rengi")[1]
        if not color:
            return
        self._hl_color = color
        self._btn_hl.configure(bg=color)
        try:
            s = self._text.index(tk.SEL_FIRST)
            e = self._text.index(tk.SEL_LAST)
            tag = f"usrhl_{color.replace('#','')}"
            self._text.tag_configure(tag, background=color)
            self._text.tag_add(tag, s, e)
        except tk.TclError:
            pass

    def _apply_alignment(self, align: str) -> None:
        try:
            s = self._text.index(tk.SEL_FIRST)
            e = self._text.index(tk.SEL_LAST)
        except tk.TclError:
            s = self._text.index(tk.INSERT + " linestart")
            e = self._text.index(tk.INSERT + " lineend")
        for t in ("align_left", "align_center", "align_right"):
            self._text.tag_remove(t, s, e)
        self._text.tag_add(f"align_{align}", s, e)

    def _apply_line_spacing(self) -> None:
        sp = int(self._line_spacing.get() * 4)
        self._text.configure(spacing1=sp, spacing3=sp)

    # -----------------------------------------------------------------------
    # Sağ tık menüsü
    # -----------------------------------------------------------------------

    def _show_text_menu(self, event: tk.Event) -> None:
        menu = tk.Menu(self, tearoff=0)
        idx  = self._text.index(f"@{event.x},{event.y}")
        tags = self._text.tag_names(idx)

        if "suspicious" in tags or "uncertain" in tags:
            menu.add_command(label="✅ Okumayi Onayla (vurguyu kaldır)",
                             command=lambda: self._confirm_at(idx))
            menu.add_command(label="✏ Düzeltip Öğret…",
                             command=lambda: self._teach_from_idx(idx))
            menu.add_separator()

        menu.add_command(label="Kopyala",   command=lambda: self.event_generate("<<Copy>>"))
        menu.add_command(label="Kes",       command=lambda: self.event_generate("<<Cut>>"))
        menu.add_command(label="Yapıştır",  command=lambda: self.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="Tümünü Seç", command=lambda: self._text.tag_add("sel","1.0",tk.END))
        menu.add_separator()
        menu.add_command(label="🟡 Kullanıcı Vurgusu Ekle",
                         command=lambda: self._add_user_highlight())
        menu.add_command(label="✖ Seçimdeki Vurguları Kaldır",
                         command=lambda: self._remove_selection_highlights())
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _confirm_at(self, idx: str) -> None:
        word_start = self._text.index(idx + " wordstart")
        word_end   = self._text.index(idx + " wordend")
        self._text.tag_remove("suspicious", word_start, word_end)
        self._text.tag_remove("uncertain",  word_start, word_end)
        self._text.tag_add("confirmed",     word_start, word_end)

    def _teach_from_idx(self, idx: str) -> None:
        word_start = self._text.index(idx + " wordstart")
        word_end   = self._text.index(idx + " wordend")
        wrong = self._text.get(word_start, word_end).strip()
        if not wrong:
            return
        dlg = tk.Toplevel(self)
        dlg.title("Düzelt ve Öğret")
        dlg.transient(self)
        dlg.grab_set()
        ttk.Label(dlg, text=f"Yanlış okuma: {wrong}").pack(padx=12, pady=(12, 4))
        var = tk.StringVar(value=wrong)
        ttk.Entry(dlg, textvariable=var, width=48).pack(padx=12, pady=6)
        scope_var = tk.StringVar(value="project")
        f = ttk.Frame(dlg); f.pack(padx=12)
        ttk.Radiobutton(f, text="Bu proje",   variable=scope_var, value="project").pack(side=tk.LEFT)
        ttk.Radiobutton(f, text="Tüm projeler", variable=scope_var, value="global").pack(side=tk.LEFT, padx=8)

        def save() -> None:
            correct = var.get().strip()
            if correct and correct != wrong:
                self.corrections.teach(wrong, correct, scope_var.get())
                self._text.delete(word_start, word_end)
                self._text.insert(word_start, correct)
                self._text.tag_remove("suspicious", word_start, word_end)
            dlg.destroy()

        ttk.Button(dlg, text="Öğret ve Düzelt", command=save).pack(pady=(4, 12))
        self.wait_window(dlg)

    def _add_user_highlight(self) -> None:
        try:
            s = self._text.index(tk.SEL_FIRST)
            e = self._text.index(tk.SEL_LAST)
            self._text.tag_add("user_highlight", s, e)
        except tk.TclError:
            pass

    def _remove_selection_highlights(self) -> None:
        try:
            s = self._text.index(tk.SEL_FIRST)
            e = self._text.index(tk.SEL_LAST)
        except tk.TclError:
            return
        for tag in ("suspicious", "uncertain", "confirmed", "user_highlight"):
            self._text.tag_remove(tag, s, e)

    # -----------------------------------------------------------------------
    # Vurgu yönetimi
    # -----------------------------------------------------------------------

    def _clear_page_highlights(self) -> None:
        for tag in ("suspicious", "uncertain"):
            self._text.tag_remove(tag, "1.0", tk.END)
        self._status_var.set("Bu sayfadaki OCR vurguları kaldırıldı.")

    def _clear_all_highlights(self) -> None:
        if not messagebox.askyesno("Tüm Vurgular", "Tüm sayfalardaki OCR vurguları kaldırılsın mı?"):
            return
        for page in self.project.pages:
            page.suspicious = []
        self._clear_page_highlights()
        self._status_var.set("Tüm OCR vurguları kaldırıldı.")

    def _highlight_suspicious(self, items: list[dict]) -> None:
        self._text.tag_remove("suspicious", "1.0", tk.END)
        self._text.tag_remove("uncertain",  "1.0", tk.END)
        content = self._text.get("1.0", tk.END)
        for item in items:
            word = str(item.get("word", ""))
            if not word:
                continue
            start = 0
            while True:
                pos = content.find(word, start)
                if pos < 0:
                    break
                conf  = float(item.get("confidence", 0))
                level = item.get("level", "")
                tag   = "uncertain" if level == "uncertain" or conf >= 0.5 else "suspicious"
                self._text.tag_add(tag, f"1.0+{pos}c", f"1.0+{pos + len(word)}c")
                start = pos + len(word)

    # -----------------------------------------------------------------------
    # Satır içi Bul / Değiştir çubuğu
    # -----------------------------------------------------------------------

    def _toggle_search_bar(self) -> None:
        """Ctrl+F — Bul/Değiştir çubuğunu göster/gizle."""
        if self._search_bar.winfo_ismapped():
            self._search_bar.pack_forget()
            self._text.focus_set()
        else:
            # Başlık etiketinin hemen altına, biçim araç çubuğunun üstüne ekle
            self._search_bar.pack(
                after=self._text_pane_header,
                fill=tk.X, pady=(2, 2),
            )
            self._search_status_var.set("")
            self._find_entry.focus_set()
            self._find_entry.select_range(0, tk.END)

    def _search_find_next(self, backward: bool = False) -> None:
        """Metinde bir sonraki (veya bir önceki) eşleşmeyi seçer."""
        import re as _re
        pattern = self._search_find_var.get()
        if not pattern:
            return
        content = self._text.get("1.0", tk.END)
        try:
            flags = _re.IGNORECASE
            matches = list(_re.finditer(_re.escape(pattern), content, flags))
        except _re.error:
            self._search_status_var.set("Geçersiz arama")
            return
        if not matches:
            self._search_status_var.set("Bulunamadı")
            self._text.tag_remove("sel", "1.0", tk.END)
            return

        # Şu anda seçili konumu bul
        try:
            cur = self._text.index(tk.SEL_FIRST)
            cur_idx = self._text.count("1.0", cur)[0]
        except tk.TclError:
            cur_idx = 0

        if backward:
            cands = [m for m in matches if m.start() < cur_idx]
            hit = cands[-1] if cands else matches[-1]
        else:
            cands = [m for m in matches if m.start() > cur_idx]
            hit = cands[0] if cands else matches[0]

        self._text.tag_remove("sel", "1.0", tk.END)
        start = f"1.0+{hit.start()}c"
        end   = f"1.0+{hit.end()}c"
        self._text.tag_add("sel", start, end)
        self._text.see(start)
        idx = matches.index(hit) + 1
        self._search_status_var.set(f"{idx}/{len(matches)}")

    def _search_replace_one(self) -> None:
        """Seçili eşleşmeyi değiştir, sonrakine atla."""
        import re as _re
        pattern = self._search_find_var.get()
        replace = self._search_replace_var.get()
        if not pattern:
            return
        try:
            sel_start = self._text.index(tk.SEL_FIRST)
            sel_end   = self._text.index(tk.SEL_LAST)
            selected  = self._text.get(sel_start, sel_end)
            if _re.fullmatch(_re.escape(pattern), selected, _re.IGNORECASE):
                self._text.delete(sel_start, sel_end)
                self._text.insert(sel_start, replace)
        except tk.TclError:
            pass
        self._search_find_next()

    def _search_replace_all(self) -> None:
        """Geçerli sayfadaki tüm eşleşmeleri değiştir."""
        import re as _re
        pattern = self._search_find_var.get()
        replace = self._search_replace_var.get()
        if not pattern:
            return
        content = self._text.get("1.0", tk.END)
        try:
            new_content, count = _re.subn(_re.escape(pattern), replace, content, flags=_re.IGNORECASE)
        except _re.error:
            self._search_status_var.set("Geçersiz arama")
            return
        if count:
            self._text.delete("1.0", tk.END)
            self._text.insert("1.0", new_content)
        self._search_status_var.set(f"{count} değiştirme yapıldı" if count else "Eşleşme yok")

    # -----------------------------------------------------------------------
    # Bul / Değiştir (iletişim kutusu — eski, geriye uyumluluk için saklandı)
    # -----------------------------------------------------------------------

    def _open_find_replace(self) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("Bul / Değiştir")
        dlg.transient(self)
        dlg.resizable(False, False)
        find_var    = tk.StringVar()
        replace_var = tk.StringVar()
        case_var    = tk.BooleanVar(value=False)
        all_var     = tk.BooleanVar(value=False)
        msg_var     = tk.StringVar()

        for row, (lbl, var) in enumerate([("Bul:", find_var), ("Değiştir:", replace_var)]):
            ttk.Label(dlg, text=lbl).grid(row=row, column=0, padx=10, pady=6, sticky=tk.W)
            ttk.Entry(dlg, textvariable=var, width=44).grid(row=row, column=1, columnspan=2, padx=4, pady=6)

        ttk.Checkbutton(dlg, text="Büyük/küçük duyarlı", variable=case_var).grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=10)
        ttk.Checkbutton(dlg, text="Tüm sayfalarda",       variable=all_var).grid( row=2, column=2, sticky=tk.W)
        ttk.Label(dlg, textvariable=msg_var, foreground="#555").grid(row=3, column=0, columnspan=3, padx=10, pady=4)

        import re

        def do_find() -> None:
            find = find_var.get()
            if not find:
                return
            content = self._text.get("1.0", tk.END)
            flags   = 0 if case_var.get() else re.IGNORECASE
            m = re.search(re.escape(find), content, flags)
            if m:
                self._text.tag_remove("sel", "1.0", tk.END)
                self._text.tag_add("sel", f"1.0+{m.start()}c", f"1.0+{m.end()}c")
                self._text.see(f"1.0+{m.start()}c")
                msg_var.set(f"Bulundu: karakter {m.start()}")
            else:
                msg_var.set("Bulunamadı.")

        def do_replace() -> None:
            import re
            find    = find_var.get()
            replace = replace_var.get()
            if not find:
                return
            flags = 0 if case_var.get() else re.IGNORECASE
            if all_var.get():
                count = 0
                for page in self.project.pages:
                    new_t, n = re.subn(re.escape(find), replace, page.text, flags=flags)
                    if n:
                        page.text = new_t
                        count += n
                self._load_page()
                msg_var.set(f"{count} değiştirme yapıldı (tüm sayfalar).")
            else:
                content = self._text.get("1.0", tk.END)
                new_c, n = re.subn(re.escape(find), replace, content, flags=flags)
                if n:
                    self._text.delete("1.0", tk.END)
                    self._text.insert("1.0", new_c)
                msg_var.set(f"{n} değiştirme yapıldı.")

        btns = ttk.Frame(dlg)
        btns.grid(row=4, column=0, columnspan=3, pady=10)
        ttk.Button(btns, text="Bul",             command=do_find).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Tümünü Değiştir", command=do_replace).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Kapat",           command=dlg.destroy).pack(side=tk.LEFT, padx=4)

    # -----------------------------------------------------------------------
    # PDF görüntü / fare işlemi
    # -----------------------------------------------------------------------

    def _update_cursor(self) -> None:
        mode = self._cursor_mode.get()
        cursor = "hand2" if mode == "hand" else "arrow"
        self._canvas.configure(cursor=cursor)
        self._hand_mode = (mode == "hand")

    def _on_canvas_press(self, event: tk.Event) -> None:
        if self._region_draw_mode:
            self._region_start = (event.x, event.y)
            if self._region_rect_id:
                self._canvas.delete(self._region_rect_id)
        elif self._hand_mode:
            self._pan_start = (event.x, event.y)

    def _on_canvas_drag(self, event: tk.Event) -> None:
        if self._region_draw_mode and self._region_start:
            if self._region_rect_id:
                self._canvas.delete(self._region_rect_id)
            x0, y0 = self._region_start
            self._region_rect_id = self._canvas.create_rectangle(
                x0, y0, event.x, event.y,
                outline="#e53935", width=2, dash=(4, 2)
            )
        elif self._hand_mode and self._pan_start:
            x0, y0 = self._pan_start
            self._canvas.scan_mark(x0, y0)
            self._canvas.scan_dragto(event.x, event.y, gain=1)
            self._pan_start = (event.x, event.y)

    def _on_canvas_release(self, event: tk.Event) -> None:
        if self._region_draw_mode and self._region_start:
            x0, y0 = self._region_start
            x1, y1 = event.x, event.y
            self._store_region_mm(x0, y0, x1, y1)
            self._region_draw_mode = False
            self._canvas.configure(cursor="arrow")
            self._region_start = None
            self._status_var.set(
                f"OCR alanı seçildi. Sol={self._crop_left.get():.1f} "
                f"Üst={self._crop_top.get():.1f} "
                f"Sağ={self._crop_right.get():.1f} "
                f"Alt={self._crop_bottom.get():.1f} mm"
            )

    def _store_region_mm(self, x0: int, y0: int, x1: int, y1: int) -> None:
        if not self._preview_original:
            return
        cw = max(1, self._canvas.winfo_width())
        ch = max(1, self._canvas.winfo_height())
        img_w, img_h = self._preview_original.size
        # Canvas koordinatlarını görüntü piksel koordinatına çevir
        scale_x = img_w / cw
        scale_y = img_h / ch
        px0, py0 = min(x0, x1) * scale_x, min(y0, y1) * scale_y
        px1, py1 = max(x0, x1) * scale_x, max(y0, y1) * scale_y
        # Piksel → mm (72 dpi varsayım)
        dpi = 150
        def px_to_mm(px): return px * 25.4 / dpi
        left_mm   = px_to_mm(px0)
        top_mm    = px_to_mm(py0)
        right_mm  = px_to_mm(img_w - px1)
        bottom_mm = px_to_mm(img_h - py1)
        self._crop_left.set(round(left_mm, 1))
        self._crop_top.set(round(top_mm, 1))
        self._crop_right.set(round(right_mm, 1))
        self._crop_bottom.set(round(bottom_mm, 1))

    def _enable_region_select(self) -> None:
        self._region_draw_mode = True
        self._canvas.configure(cursor="crosshair")
        self._status_var.set("Fare ile OCR alanını seçin. Sol üstten sağ alta sürükleyin.")

    def _clear_region(self) -> None:
        for var in (self._crop_left, self._crop_top, self._crop_right, self._crop_bottom):
            var.set(0)
        if self._region_rect_id:
            self._canvas.delete(self._region_rect_id)
            self._region_rect_id = None
        self._status_var.set("OCR alanı seçimi temizlendi.")

    def _on_ctrl_wheel(self, event: tk.Event) -> None:
        self._zoom_by(1.12 if event.delta > 0 else 0.89)
        return "break"

    def _on_canvas_wheel(self, event: tk.Event) -> None:
        if self._view_mode_var.get() == "film_seridi":
            # Film şeridi: normal kaydır + 250 ms debounce ile sayfa tespiti
            self._canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
            if self._fs_debounce_id:
                self.after_cancel(self._fs_debounce_id)
            self._fs_debounce_id = self.after(250, self._on_filmstrip_scroll_end)
        else:
            # Tek sayfa: tekerlek = sayfa geçişi (aşağı = sonraki, yukarı = önceki)
            self._go_page(-1 if event.delta > 0 else 1)

    def _zoom_by(self, factor: float) -> None:
        self._fit_mode = False
        self._zoom = max(0.2, min(5.0, self._zoom * factor))
        self._draw_page()

    def _fit_page(self) -> None:
        self._fit_mode = True
        self._zoom = 1.0
        self._draw_page()

    def _go_page(self, delta: int) -> None:
        self._save_text(silent=True)
        if not self.project.pages:
            return
        new_idx = max(0, min(len(self.project.pages) - 1,
                             self.project.current_page + delta))
        self.project.current_page = new_idx
        self._load_page()

    # -----------------------------------------------------------------------
    # Sayfa yükleme & çizim
    # -----------------------------------------------------------------------

    def _load_page(self) -> None:
        self._draw_page()
        self._load_text()
        self._update_page_label()

    def _draw_page(self) -> None:
        if self._view_mode_var.get() == "film_seridi":
            if not self._filmstrip_page_tops:
                self._draw_filmstrip()   # ilk açılışta tam render
            else:
                # Sadece aktif sayfa vurgusunu güncelle ve scroll et
                self._canvas.delete("fs_highlight")
                self._filmstrip_update_highlight()
                self._filmstrip_scroll_to_page(self.project.current_page)
            return

        page = self._current_page()
        if not page or not page.image_path:
            self._canvas.delete("all")
            self._canvas.create_text(20, 20, text="Sayfa yok.", anchor=tk.NW, fill="#aaa")
            return
        img_path = Path(page.image_path)
        if not img_path.exists():
            return
        try:
            img = Image.open(img_path)
            self._preview_original = img.copy()
            self.update_idletasks()
            cw = max(300, self._canvas.winfo_width() - 4)
            ch = max(300, self._canvas.winfo_height() - 4)
            if self._fit_mode:
                img.thumbnail((cw, ch), Image.LANCZOS)
            else:
                new_w = int(img.width  * self._zoom)
                new_h = int(img.height * self._zoom)
                img = img.resize((new_w, new_h), Image.LANCZOS)
            self._preview_image = ImageTk.PhotoImage(img)
            self._canvas.delete("all")
            self._canvas.create_image(0, 0, image=self._preview_image, anchor=tk.NW)
            self._canvas.configure(scrollregion=(0, 0, img.width, img.height))
            # OCR alanı dikdörtgenini yeniden çiz
            if self._region_rect_id:
                self._canvas.delete(self._region_rect_id)
                self._region_rect_id = None
        except Exception as exc:
            self._canvas.delete("all")
            self._canvas.create_text(10, 10, text=str(exc), anchor=tk.NW, fill="red")

    # -----------------------------------------------------------------------
    # Film şeridi görünümü
    # -----------------------------------------------------------------------

    def _on_view_mode_change(self) -> None:
        """Görünüm modu değişince canvas'ı güncelle."""
        if self._view_mode_var.get() == "film_seridi":
            self._filmstrip_page_tops = []   # zorla tam render
            self._filmstrip_images = []
            self._draw_filmstrip()
        else:
            self._filmstrip_page_tops = []
            self._filmstrip_images = []
            self._draw_page()

    def _draw_filmstrip(self) -> None:
        """Tüm sayfaları canvas'ta dikey olarak göster (film şeridi)."""
        self._canvas.delete("all")
        self._filmstrip_images = []
        self._filmstrip_page_tops = []
        self._filmstrip_page_bottoms = []

        if not self.project.pages:
            self._canvas.create_text(20, 20, text="Sayfa yok.", anchor=tk.NW, fill="#aaa")
            return

        self.update_idletasks()
        cw = max(200, self._canvas.winfo_width() - 4)
        GAP  = 10   # sayfalar arası boşluk
        SEP_H = 20  # sayfa etiketi şeridinin yüksekliği

        y = GAP
        for i, page in enumerate(self.project.pages):
            self._filmstrip_page_tops.append(y)

            if page.image_path and Path(page.image_path).exists():
                try:
                    img = Image.open(page.image_path)
                    scale = cw / img.width
                    new_h = int(img.height * scale)
                    img = img.resize((cw, new_h), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self._filmstrip_images.append(photo)
                    self._canvas.create_image(0, y, image=photo, anchor=tk.NW)
                    page_h = new_h
                except Exception:
                    self._filmstrip_images.append(None)
                    self._canvas.create_rectangle(0, y, cw, y + 200,
                                                  outline="#ccc", fill="#f5f5f5")
                    self._canvas.create_text(cw // 2, y + 100, text="yüklenemedi",
                                             fill="#999", justify=tk.CENTER)
                    page_h = 200
            else:
                self._filmstrip_images.append(None)
                self._canvas.create_rectangle(0, y, cw, y + 200,
                                              outline="#ccc", fill="#f5f5f5")
                self._canvas.create_text(cw // 2, y + 100,
                                         text=f"Sayfa {i + 1}\n(görüntü yok)",
                                         fill="#999", justify=tk.CENTER)
                page_h = 200

            self._filmstrip_page_bottoms.append(y + page_h)
            y += page_h

            # Sayfa etiketi şeridi
            lbl = page.label or str(i + 1)
            self._canvas.create_rectangle(0, y, cw, y + SEP_H, fill="#e0e0e8", outline="")
            self._canvas.create_text(cw // 2, y + SEP_H // 2,
                                     text=f"― {lbl} ―",
                                     fill="#555", font=("Segoe UI", 8))
            y += SEP_H + GAP

        self._filmstrip_total_h = y
        self._canvas.configure(scrollregion=(0, 0, cw, y))

        # Aktif sayfa vurgusu
        self._filmstrip_update_highlight()
        # Aktif sayfaya kaydır
        self._filmstrip_scroll_to_page(self.project.current_page)

    def _filmstrip_update_highlight(self) -> None:
        """Aktif sayfanın etrafına mavi çerçeve çiz (tüm canvas'ı yeniden render etmeden)."""
        self._canvas.delete("fs_highlight")
        idx = self.project.current_page
        if (not self._filmstrip_page_tops or
                idx >= len(self._filmstrip_page_tops)):
            return
        top    = self._filmstrip_page_tops[idx]
        bottom = self._filmstrip_page_bottoms[idx] if hasattr(self, "_filmstrip_page_bottoms") else top + 200
        cw = max(200, self._canvas.winfo_width() - 4)
        self._canvas.create_rectangle(
            -2, top - 2, cw + 2, bottom + 2,
            outline="#0d6efd", width=3, tags="fs_highlight",
        )

    def _filmstrip_scroll_to_page(self, idx: int) -> None:
        """Film şeridinde belirli sayfayı görünür alana getir."""
        if not self._filmstrip_page_tops or self._filmstrip_total_h <= 0:
            return
        if idx >= len(self._filmstrip_page_tops):
            return
        top_y = self._filmstrip_page_tops[idx]
        frac  = max(0.0, (top_y - 10) / self._filmstrip_total_h)
        self._canvas.yview_moveto(frac)

    def _on_filmstrip_scroll_end(self) -> None:
        """Scroll durduktan 250 ms sonra hangi sayfa merkezde → onu aktif yap."""
        self._fs_debounce_id = None
        if not self._filmstrip_page_tops or self._filmstrip_total_h <= 0:
            return

        yv = self._canvas.yview()
        center_frac = (yv[0] + yv[1]) / 2
        center_y    = center_frac * self._filmstrip_total_h

        best_idx, best_dist = 0, float("inf")
        for i, top in enumerate(self._filmstrip_page_tops):
            dist = abs(top - center_y)
            if dist < best_dist:
                best_dist = dist
                best_idx  = i

        if best_idx != self.project.current_page:
            self._save_text(silent=True)
            self.project.current_page = best_idx
            self._load_text()
            self._update_page_label()
            self._filmstrip_update_highlight()

    # -----------------------------------------------------------------------

    def _load_text(self) -> None:
        page = self._current_page()
        self._text.edit_modified(False)
        self._text.delete("1.0", tk.END)
        if page and page.text:
            self._text.insert("1.0", page.text)
            if page.suspicious:
                self._highlight_suspicious(page.suspicious)
        self._text.edit_modified(False)

    def _current_page(self):
        if not self.project.pages:
            return None
        idx = max(0, min(len(self.project.pages) - 1, self.project.current_page))
        return self.project.pages[idx]

    def _update_page_label(self) -> None:
        total = len(self.project.pages)
        if not total:
            self._page_var.set("0/0")
            return
        idx  = self.project.current_page + 1
        page = self._current_page()
        lbl  = page.label if page else ""
        self._page_var.set(f"Sayfa {idx}/{total}  {lbl}")

    # -----------------------------------------------------------------------
    # Metin kaydetme
    # -----------------------------------------------------------------------

    def _on_text_modified(self, _event=None) -> None:
        if self._text.edit_modified():
            self._text.edit_modified(False)

    def _save_text(self, silent: bool = False) -> None:
        page = self._current_page()
        if not page:
            return
        page.text = self._text.get("1.0", tk.END).rstrip()
        if self.on_text_saved:
            self.on_text_saved(self.project.current_page, page.text)
        if not silent:
            self._status_var.set("Metin kaydedildi.")

    # -----------------------------------------------------------------------
    # OCR başlat / duraklat / durdur
    # -----------------------------------------------------------------------

    def _start_ocr(self) -> None:
        if self._ocr_thread and self._ocr_thread.is_alive():
            messagebox.showinfo("OCR", "Zaten çalışıyor.")
            return
        pages = self._resolve_pages()
        if not pages:
            messagebox.showinfo("OCR", "İşlenecek sayfa bulunamadı.")
            return
        self._cancel_flag.clear()
        self._paused_flag.clear()
        self._btn_start.configure(state=tk.DISABLED)
        self._btn_pause.configure(state=tk.NORMAL)
        self._btn_stop.configure(state=tk.NORMAL)
        self._progress_var.set(0)
        self._ocr_thread = threading.Thread(
            target=self._ocr_worker, args=(pages,), daemon=True
        )
        self._ocr_thread.start()

    def _pause_ocr(self) -> None:
        if self._paused_flag.is_set():
            self._paused_flag.clear()
            self._btn_pause.configure(text="⏸ Duraklat")
            self._status_var.set("OCR devam ediyor…")
        else:
            self._paused_flag.set()
            self._btn_pause.configure(text="▶ Devam Et")
            self._status_var.set("OCR duraklatıldı.")

    def _stop_ocr(self) -> None:
        self._cancel_flag.set()
        self._paused_flag.clear()
        self._status_var.set("OCR iptal ediliyor…")

    def _resolve_pages(self) -> list[int]:
        """Hangi sayfa indekslerinin OCR'leneceğini döndür (0-tabanlı)."""
        scope = self._scope_var.get()
        total = len(self.project.pages)
        if not total:
            return []
        if scope == "tümü":
            return list(range(total))
        if scope == "görünen":
            return [self.project.current_page]
        if scope == "seçim":
            raw = self._page_sel_var.get().strip()
            if not raw:
                return list(range(total))
            from metin_atolyesi.core.pdf_tools import parse_page_ranges
            nums = parse_page_ranges(raw, total)
            return [n - 1 for n in nums if 0 <= n - 1 < total]
        return [self.project.current_page]

    def _ocr_worker(self, page_indices: list[int]) -> None:
        total  = len(page_indices)
        lang   = self._lang_code_var.get()
        engine = self._engine_var.get()
        deskew = self._deskew_var.get()
        mode   = self._preprocess_var.get()
        use_conf = self._confidence_var.get()
        layout = self._layout_var.get()
        psm    = LAYOUT_PSM.get(layout, 6)
        crop   = (self._crop_left.get(), self._crop_top.get(),
                  self._crop_right.get(), self._crop_bottom.get())

        for step, idx in enumerate(page_indices):
            # İptal
            if self._cancel_flag.is_set():
                break
            # Duraklat
            while self._paused_flag.is_set():
                import time; time.sleep(0.2)
                if self._cancel_flag.is_set():
                    break

            page = self.project.pages[idx]
            img_path = Path(page.image_path) if page.image_path else None
            if not img_path or not img_path.exists():
                self.after(0, lambda s=step, t=total: self._update_progress(s, t, "Görüntü yok"))
                continue

            label = page.label or str(idx + 1)
            self.after(0, lambda s=step, t=total, lb=label:
                       self._update_progress(s, t, f"Sayfa {lb}…"))
            try:
                work_dir = self.project.images_dir
                # Kırpma uygula
                src = self._maybe_crop_image(img_path, work_dir, crop, idx)

                if engine == "claude":
                    # Claude kendi içinde en iyi sonucu üretiyor —
                    # ön işleme veya çoklu deneme gerekmiyor.
                    # El yazması modu aktifse meta kriterler prompt'a eklenir.
                    _is_manuscript = (
                        getattr(self, "_doc_mode_var", None) is not None
                        and self._doc_mode_var.get() == "manuscript"
                    )
                    text, suspicious = ocr_image(
                        src, lang, engine="claude", psm=psm,
                        manuscript_meta=self._ms_meta if (_is_manuscript and self._ms_meta) else None,
                    )
                elif engine == "transkribus":
                    # Transkribus kendi içinde HTR yapar — ön işlem gerektirmez
                    text, suspicious = ocr_image(src, lang, engine="transkribus")
                elif mode == "çoklu deneme":
                    text, suspicious = run_multi_mode_ocr(
                        src, work_dir, lang=lang, engine=engine,
                        deskew=deskew, psm=psm,
                    )
                elif use_conf and (engine in ("otomatik", "tesseract")):
                    text, suspicious = ocr_image_with_confidence(src, lang, psm=psm)
                else:
                    preprocessed = work_dir / f"page_{idx + 1:04d}_ocr.png"
                    preprocess_image(src, preprocessed, mode)
                    text, suspicious = ocr_image(preprocessed, lang, engine, psm=psm)

                text = self._post_process(text, layout)
                text = self.corrections.apply(text)
                page.text = text
                page.suspicious = suspicious

                # Aktif sayfaysa UI güncelle
                if idx == self.project.current_page:
                    self.after(0, self._load_page)

            except Exception as exc:
                page.text = f"[OCR HATASI: {exc}]"
                page.suspicious = []

            self.after(0, lambda s=step + 1, t=total, lb=label:
                       self._update_progress(s, t, f"Sayfa {lb} tamam"))

        self.after(0, self._ocr_done)

    def _maybe_crop_image(self, img_path: Path, work_dir: Path,
                           crop: tuple, idx: int) -> Path:
        left_mm, top_mm, right_mm, bottom_mm = crop
        if max(crop) < 0.5:
            return img_path
        from PIL import Image as PILImage
        img = PILImage.open(img_path)
        dpi = 150
        def mm_to_px(mm): return int(mm * dpi / 25.4)
        l = mm_to_px(left_mm)
        t = mm_to_px(top_mm)
        r = img.width  - mm_to_px(right_mm)
        b = img.height - mm_to_px(bottom_mm)
        r = max(l + 10, r)
        b = max(t + 10, b)
        cropped = img.crop((l, t, r, b))
        out = work_dir / f"page_{idx + 1:04d}_cropped.png"
        cropped.save(out)
        return out

    def _post_process(self, text: str, layout: str) -> str:
        """Düzene göre metin son işleme."""
        if "Beyit" in layout or "Şiir" in layout:
            # Her satırı koru, boş satırlarla beyitleri ayır
            lines = [ln.rstrip() for ln in text.splitlines()]
            return "\n".join(lines)
        if "Tablo" in layout or "Dizin" in layout:
            return text  # tabular yapıyı koru
        # Düzyazı: ardışık satır sonlarını boşluğa çevir,
        # ama paragraf aralarını (çift satır sonu) koru
        import re
        text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
        text = re.sub(r"  +", " ", text)
        return text.strip()

    def _update_progress(self, step: int, total: int, label: str) -> None:
        pct = (step / total) * 100 if total else 0
        self._progress_var.set(pct)
        self._progress_lbl.set(f"{step}/{total}")
        self._status_var.set(f"OCR: {label}")

    def _ocr_done(self) -> None:
        self._progress_var.set(100)
        self._progress_lbl.set("Tamamlandı")
        self._btn_start.configure(state=tk.NORMAL)
        self._btn_pause.configure(state=tk.DISABLED, text="⏸ Duraklat")
        self._btn_stop.configure(state=tk.DISABLED)
        self._load_page()
        # Bitti bildirimi
        page   = self._current_page()
        n_susp = len(page.suspicious) if page else 0
        messagebox.showinfo(
            "OCR Tamamlandı",
            f"OCR işlemi bitti.\n"
            f"Aktif sayfada {n_susp} şüpheli/belirsiz okuma bulundu.\n"
            f"Sarı vurgulu kelimeler metin bölmesinde gösterildi."
        )
        self._status_var.set(f"OCR tamamlandı — {n_susp} şüpheli okuma.")

    # -----------------------------------------------------------------------
    # Dil seçimi
    # -----------------------------------------------------------------------

    def _on_lang_select(self, _event=None) -> None:
        selected = self._lang_display_var.get()
        for lbl, code in LANG_PRESETS:
            if lbl == selected:
                if code == "__custom__":
                    self._custom_lang_entry.pack(side=tk.LEFT, before=self._custom_lang_entry)
                    self._custom_lang_entry.pack()
                    self._lang_code_var.set(self._custom_lang_var.get())
                else:
                    self._custom_lang_entry.pack_forget()
                    self._lang_code_var.set(code)
                break
        self._custom_lang_var.trace_add("write",
            lambda *_: self._lang_code_var.set(self._custom_lang_var.get()))

    def _on_engine_select(self, _event=None) -> None:
        """Motor seçiminde gerekli bileşen kontrolü."""
        eng = self._engine_var.get()

        if "claude" in eng:
            self._engine_var.set("claude")   # " ⚡" eki olmadan sakla
            from metin_atolyesi.core.claude_ocr import get_api_key
            if not get_api_key():
                messagebox.showwarning(
                    "Claude API Anahtarı",
                    "Claude motoru seçildi ancak API anahtarı henüz girilmemiş.\n\n"
                    "Dosya → ⚡ Claude API Ayarları menüsünden anahtarınızı girin.",
                )

        elif eng == "easyocr":
            import importlib.util
            if importlib.util.find_spec("easyocr") is None:
                messagebox.showinfo(
                    "EasyOCR Kurulu Değil",
                    "EasyOCR kurulmamış. Aşağıdaki komutu çalıştırın:\n\n"
                    "    pip install easyocr\n\n"
                    "Kurulum tamamlandıktan sonra uygulamayı yeniden başlatın.\n"
                    "Not: İlk kullanımda model dosyaları indirilir (~500 MB).",
                )

        elif eng == "tesseract":
            from metin_atolyesi.core.dependencies import find_tesseract, module_available
            if not module_available("pytesseract"):
                messagebox.showinfo(
                    "pytesseract Kurulu Değil",
                    "Tesseract motoru için pytesseract gerekli:\n\n"
                    "    pip install pytesseract\n\n"
                    "Ayrıca Tesseract programını da yükleyin:\n"
                    "https://github.com/UB-Mannheim/tesseract/wiki",
                )
            elif not find_tesseract():
                messagebox.showinfo(
                    "Tesseract Bulunamadı",
                    "pytesseract kurulu ama Tesseract programı bulunamadı.\n\n"
                    "https://github.com/UB-Mannheim/tesseract/wiki\n"
                    "adresinden indirip kurun (Türkçe dil paketini seçin).",
                )

        elif eng == "rapidocr":
            import importlib.util
            if importlib.util.find_spec("rapidocr_onnxruntime") is None:
                messagebox.showinfo(
                    "RapidOCR Kurulu Değil",
                    "RapidOCR kurulmamış:\n\n"
                    "    pip install rapidocr-onnxruntime",
                )

        elif "transkribus" in eng:
            self._engine_var.set("transkribus")   # emoji eki olmadan sakla
            # ⚠ Transkribus yeni API auth servisi bu ağdan erişilemiyor.
            # account.transkribus.eu DNS kaydı mevcut değil (global sorun).
            import webbrowser
            answer = messagebox.askokcancel(
                "Transkribus — Ağ Kısıtlaması",
                "⚠ Transkribus API'si bu ağdan erişilemiyor.\n\n"
                "Teknik neden: Transkribus'un kimlik doğrulama sunucusu\n"
                "(account.transkribus.eu) DNS'de kayıtlı değil.\n\n"
                "Alternatifler:\n"
                "  • Claude ⚡ seçin — Osmanlıca için en iyi sonuç\n"
                "  • Transkribus web: app.transkribus.ai\n\n"
                "Web arayüzünü açmak ister misiniz?",
            )
            if answer:
                webbrowser.open("https://app.transkribus.ai")
            self._engine_var.set("claude")  # Claude'a geç

    # -----------------------------------------------------------------------
    # Kapsam seçimi
    def _open_transkribus_settings(self) -> None:
        """Transkribus kimlik bilgileri ve model yapılandırma diyaloğu."""
        from metin_atolyesi.core.transkribus_ocr import (
            get_config, save_config, get_credit_info, OTTOMAN_MODELS, DEFAULT_MODEL_ID
        )

        dlg = tk.Toplevel(self.winfo_toplevel())
        dlg.title("Transkribus Ayarları")
        dlg.geometry("520x420")
        dlg.resizable(False, False)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()

        cfg = get_config()

        # ── Başlık ──────────────────────────────────────────────────────
        hdr = ttk.Frame(dlg)
        hdr.pack(fill=tk.X, padx=16, pady=(14, 6))
        ttk.Label(hdr, text="📜 Transkribus HTR Yapılandırması",
                  font=("Segoe UI", 12, "bold")).pack(anchor=tk.W)
        ttk.Label(hdr,
                  text="Osmanlıca el yazmaları için UNESCO & devlet arşivleri standardı.",
                  font=("Segoe UI", 9), foreground="#555").pack(anchor=tk.W)

        ttk.Separator(dlg, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=16, pady=6)

        # ── Form alanları ───────────────────────────────────────────────
        form = ttk.Frame(dlg)
        form.pack(fill=tk.X, padx=16, pady=4)

        ttk.Label(form, text="E-posta:", width=14, anchor=tk.W).grid(
            row=0, column=0, sticky=tk.W, pady=6)
        email_var = tk.StringVar(value=cfg["email"])
        ttk.Entry(form, textvariable=email_var, width=36).grid(
            row=0, column=1, sticky=tk.EW, pady=6)

        ttk.Label(form, text="Şifre:", width=14, anchor=tk.W).grid(
            row=1, column=0, sticky=tk.W, pady=6)
        pw_var = tk.StringVar(value=cfg["password"])
        ttk.Entry(form, textvariable=pw_var, show="•", width=36).grid(
            row=1, column=1, sticky=tk.EW, pady=6)

        ttk.Separator(form, orient=tk.HORIZONTAL).grid(
            row=2, column=0, columnspan=2, sticky=tk.EW, pady=8)

        ttk.Label(form, text="HTR Modeli:", width=14, anchor=tk.W).grid(
            row=3, column=0, sticky=tk.W, pady=6)
        model_names = list(OTTOMAN_MODELS.keys()) + ["Özel (ID gir)…"]
        model_var = tk.StringVar(value=model_names[0])
        model_cb = ttk.Combobox(form, textvariable=model_var,
                                values=model_names, state="readonly", width=34)
        model_cb.grid(row=3, column=1, sticky=tk.EW, pady=6)

        ttk.Label(form, text="Model ID:", width=14, anchor=tk.W).grid(
            row=4, column=0, sticky=tk.W, pady=6)
        mid_var = tk.IntVar(value=cfg["model_id"])
        mid_entry = ttk.Entry(form, textvariable=mid_var, width=10)
        mid_entry.grid(row=4, column=1, sticky=tk.W, pady=6)

        def _on_model_select(*_):
            name = model_var.get()
            if name in OTTOMAN_MODELS:
                mid_var.set(OTTOMAN_MODELS[name])
        model_cb.bind("<<ComboboxSelected>>", _on_model_select)

        form.columnconfigure(1, weight=1)

        # ── Kredi bilgisi ────────────────────────────────────────────────
        info_var = tk.StringVar(value="")
        info_lbl = ttk.Label(dlg, textvariable=info_var,
                             font=("Segoe UI", 9, "italic"), foreground="#2a7a2a")
        info_lbl.pack(padx=16, anchor=tk.W)

        def _test():
            try:
                save_config(email_var.get(), pw_var.get(), mid_var.get())
                # Önbelleği sıfırla
                import metin_atolyesi.core.transkribus_ocr as _t
                _t._session_id = ""
                info = get_credit_info()
                info_var.set(f"✓ Bağlantı başarılı — {info}")
            except Exception as e:
                info_var.set(f"✗ {e}")

        def _save():
            save_config(email_var.get(), pw_var.get(), mid_var.get())
            dlg.destroy()

        # ── Bağlantı linki ───────────────────────────────────────────────
        link_frm = ttk.Frame(dlg)
        link_frm.pack(fill=tk.X, padx=16, pady=(4, 2))
        ttk.Label(link_frm, text="Hesap açmak için:",
                  font=("Segoe UI", 9)).pack(side=tk.LEFT)
        link = ttk.Label(link_frm, text="https://app.transkribus.ai",
                         font=("Segoe UI", 9, "underline"), foreground="#0d6efd",
                         cursor="hand2")
        link.pack(side=tk.LEFT, padx=4)
        link.bind("<Button-1>", lambda _: __import__("webbrowser").open(
            "https://app.transkribus.ai"))

        ttk.Label(dlg,
                  text="Her sayfa işlemi ~1-2 kredi tüketir. Ücretsiz hesap ~500 kredi ile başlar.",
                  font=("Segoe UI", 8), foreground="#888").pack(padx=16, anchor=tk.W)

        # ── Düğmeler ────────────────────────────────────────────────────
        btn_row = ttk.Frame(dlg)
        btn_row.pack(fill=tk.X, padx=16, pady=(10, 14))
        ttk.Button(btn_row, text="🔌 Bağlantıyı Test Et", command=_test).pack(
            side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="✓ Kaydet", command=_save).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="İptal", command=dlg.destroy).pack(side=tk.RIGHT)

    # -----------------------------------------------------------------------

    def _on_scope_change(self) -> None:
        if self._scope_var.get() == "seçim":
            self._page_sel_entry.configure(state=tk.NORMAL)
        else:
            self._page_sel_entry.configure(state=tk.DISABLED)

    # -----------------------------------------------------------------------
    # Ayarları gizle / göster
    # -----------------------------------------------------------------------

    def _toggle_settings(self) -> None:
        if self._settings_visible:
            self._settings_frame.pack_forget()
            self._settings_visible = False
        else:
            self._settings_frame.pack(fill=tk.X, padx=6, pady=(6, 2),
                                      before=self._paned)
            self._settings_visible = True

    def _show_shortcuts(self) -> None:
        text = (
            "F5         → Geçerli sayfayı OCR ile oku\n"
            "F6         → Toplu OCR başlat\n"
            "Ctrl+S     → Projeyi kaydet\n"
            "Ctrl+H     → Bul / Değiştir\n"
            "Ctrl+←/→   → Sayfa değiştir\n"
            "Ctrl+B     → Kalın (seçili metin)\n"
            "Ctrl+I     → İtalik\n"
            "Ctrl+U     → Altı çizili\n"
            "Sağ tık    → OCR düzelt, onayla, vurgu menüsü\n"
            "Çift tık   → Kelime seç\n"
            "PDF: ✋     → El aracı (kaydır)\n"
            "PDF: ↖     → Seçim imleci\n"
            "🔲 Alan Seç → Fareyle OCR alanı çiz\n"
        )
        messagebox.showinfo("Kısayollar", text)

    # -----------------------------------------------------------------------
    # Dışarıdan çağrılan genel arayüz
    # -----------------------------------------------------------------------

    def set_project(self, project, corrections: CorrectionsStore | None = None) -> None:
        self.project = project
        if corrections:
            self.corrections = corrections
        self._load_page()

    def refresh(self) -> None:
        self._load_page()
        self._update_page_label()
