"""El Yazması Öğretme Sihirbazı — 6 adımlı profesyonel wizard."""
from __future__ import annotations

import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


def _fmt_dur(secs: float) -> str:
    """Saniyeyi 'X dk Y sn' formatına çevirir."""
    s = int(secs)
    m, s = divmod(s, 60)
    if m:
        return f"{m} dk {s} sn"
    return f"{s} sn"

from metin_atolyesi.core.manuscript_library import (
    ALANLAR, DONEMLER, HAREKE_DURUMLARI, IMLA_OZELLIKLERI,
    METIN_BOLUMLERI, YAZI_TURLERI,
    HarfFormu, ManuscriptMeta, MetinBolumu, VarakSatirBilgisi,
    get_library,
)

# ── Tema ──────────────────────────────────────────────────────────────────
_BG     = "#12121f"
_PANEL  = "#1a1a2e"
_CARD   = "#1e2a45"
_BORDER = "#2a3050"
_ACC1   = "#0d6efd"   # mavi
_ACC2   = "#e94560"   # kırmızı-pembe
_GREEN  = "#2ecc71"
_AMBER  = "#f39c12"
_FG     = "#e2e8f0"
_FG2    = "#8892b0"
_FG3    = "#4a5568"

_F      = ("Segoe UI", 10)
_FB     = ("Segoe UI", 10, "bold")
_FH     = ("Segoe UI", 12, "bold")
_FT     = ("Segoe UI", 14, "bold")
_FS     = ("Segoe UI", 9)
_FSB    = ("Segoe UI", 9, "bold")


# ── Widget yardımcıları ───────────────────────────────────────────────────

def _lbl(p, text, font=None, fg=None, bg=None, **kw):
    return tk.Label(p, text=text, font=font or _F,
                    fg=fg or _FG, bg=bg or _BG, **kw)

def _entry(p, var, width=32, show="", **kw):
    return tk.Entry(p, textvariable=var, width=width, show=show,
                    font=_F, bg="#1c2035", fg=_FG,
                    insertbackground=_FG, relief=tk.FLAT,
                    highlightbackground=_BORDER, highlightthickness=1, **kw)

def _combo(p, var, values, width=24):
    cb = ttk.Combobox(p, textvariable=var, values=values,
                      width=width, state="readonly", font=_F)
    return cb

def _spin(p, var, lo=1, hi=999, width=6):
    return tk.Spinbox(p, textvariable=var, from_=lo, to=hi, width=width,
                      font=_F, bg="#1c2035", fg=_FG,
                      buttonbackground="#2a3050", relief=tk.FLAT,
                      highlightbackground=_BORDER, highlightthickness=1)

def _btn(p, text, cmd, style="primary", **kw):
    colors = {
        "primary": (_ACC1, "white"),
        "danger":  (_ACC2, "white"),
        "ghost":   ("#2a3050", _FG),
        "success": ("#1a5c35", _GREEN),
    }
    bg, fg = colors.get(style, (_ACC1, "white"))
    b = tk.Button(p, text=text, command=cmd, font=_FB,
                  bg=bg, fg=fg, relief=tk.FLAT, bd=0,
                  padx=14, pady=7, cursor="hand2",
                  activebackground=_ACC2 if style=="danger" else "#1a5fcc",
                  activeforeground="white", **kw)
    return b

def _section(p, title, icon="▸"):
    """Bölüm başlığı — renkli şerit."""
    f = tk.Frame(p, bg=_CARD)
    tk.Label(f, text=f"  {icon}  {title}", bg=_CARD, fg=_FG,
             font=_FB, pady=7).pack(side=tk.LEFT, padx=4)
    return f

def _card(p, **kw):
    return tk.Frame(p, bg=_CARD,
                    highlightbackground=_BORDER, highlightthickness=1, **kw)

def _scrolled_frame(parent) -> tuple[tk.Canvas, tk.Frame]:
    """Kaydırılabilir iç çerçeve döndürür."""
    sb     = ttk.Scrollbar(parent, orient=tk.VERTICAL)
    canvas = tk.Canvas(parent, bg=_BG, highlightthickness=0,
                       yscrollcommand=sb.set)
    sb.configure(command=canvas.yview)
    frame  = tk.Frame(canvas, bg=_BG)
    win    = canvas.create_window((0, 0), window=frame, anchor=tk.NW)

    # Frame büyüdükçe → scrollregion güncelle
    frame.bind("<Configure>",
               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    # Canvas boyutu değişince → iç frame genişliği canvas ile eşleşsin
    canvas.bind("<Configure>",
                lambda e: canvas.itemconfig(win, width=e.width))

    # Fare tekerleği
    def _on_mousewheel(e):
        canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    sb.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    return canvas, frame


# ══════════════════════════════════════════════════════════════════════════
#  Ana Wizard
# ══════════════════════════════════════════════════════════════════════════

class ManuscriptWizard(tk.Toplevel):
    STEPS = [
        ("📄", "Kaynak"),
        ("📐", "Varak"),
        ("✒", "İmla"),
        ("📑", "Yapı"),
        ("🔤", "Paleografi"),
        ("✅", "Özet"),
    ]

    def __init__(self, parent):
        super().__init__(parent)
        self.title("El Yazması Öğretme Sihirbazı")
        self.geometry("820x680")
        self.minsize(760, 580)
        self.configure(bg=_BG)
        self.transient(parent)
        self.grab_set()
        self._step = 0
        self._init_vars()
        self._build_shell()
        self._show_step(0)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        # Fare tekerleği binding'ini temizle
        try:
            self.unbind_all("<MouseWheel>")
        except Exception:
            pass
        self.destroy()

    # ── Değişkenler ──────────────────────────────────────────────────────

    def _init_vars(self):
        # Adım 1
        self.ms_path_var    = tk.StringVar()
        self.trans_path_var = tk.StringVar()
        self.eser_adi_var   = tk.StringVar()
        self.yazar_var      = tk.StringVar()
        self.muellif_var    = tk.StringVar()
        self.tarih_var      = tk.StringVar()
        self.kutuphane_var  = tk.StringVar()
        self.demir_no_var   = tk.StringVar()
        self.tez_ref_var    = tk.StringVar()
        self.kaynak_turu_var = tk.StringVar(value="transkripsiyon")

        # Adım 2 — Varak
        self.ms_start_var   = tk.IntVar(value=1)
        self.ms_end_var     = tk.IntVar(value=10)
        self.tr_start_var   = tk.IntVar(value=1)
        self.tr_end_var     = tk.IntVar(value=10)
        self.sync_var       = tk.BooleanVar(value=True)
        self.toplam_varak_var = tk.IntVar(value=0)
        self.satir_min_var  = tk.IntVar(value=15)
        self.satir_max_var  = tk.IntVar(value=15)
        self.duzenli_var    = tk.BooleanVar(value=True)
        self.ilk_varak_satir_var = tk.IntVar(value=0)
        self.son_varak_satir_var = tk.IntVar(value=0)
        self.baslik_satir_var    = tk.IntVar(value=0)
        self.ozel_varaklar_var   = tk.StringVar()
        self.sutun_var      = tk.IntVar(value=1)
        self.varak_not_var  = tk.StringVar()

        # Adım 3 — İmla
        self.imla_vars: dict[str, tk.BooleanVar] = {}
        for grp_items in IMLA_OZELLIKLERI.values():
            for item in grp_items:
                self.imla_vars[item] = tk.BooleanVar(value=False)
        self.imla_serbest_var    = tk.StringVar()
        self.aktarim_ilk_var     = tk.StringVar()

        # Adım 4 — Metin yapısı
        self._bolum_rows: list[dict] = []   # dinamik satırlar

        # Adım 5 — Paleografi + alan
        self.alan_var       = tk.StringVar(value="Osmanlıca")
        self.donem_var      = tk.StringVar(value="Belirsiz")
        self.yazi_var       = tk.StringVar(value="Nesih")
        self.hareke_var     = tk.StringVar(value="Harekesiz")
        self.dil_var        = tk.StringVar(value="ara")
        self.guven_var      = tk.DoubleVar(value=0.9)
        self.ozel_not_var   = tk.StringVar()
        self._harf_rows: list[dict] = []

    # ── Kabuk ────────────────────────────────────────────────────────────

    def _build_shell(self):
        # Başlık
        top = tk.Frame(self, bg="#0d1117", height=52)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="  ✍  El Yazması Öğretme Sihirbazı",
                 bg="#0d1117", fg=_FG, font=_FT).pack(side=tk.LEFT, padx=16, pady=12)

        # Adım çubuğu
        self._bar = tk.Frame(self, bg=_PANEL, height=48)
        self._bar.pack(fill=tk.X)
        self._bar.pack_propagate(False)
        self._step_btns: list[tk.Label] = []
        for i, (icon, name) in enumerate(self.STEPS):
            f = tk.Frame(self._bar, bg=_PANEL)
            f.pack(side=tk.LEFT, expand=True, fill=tk.X)
            lbl = tk.Label(f, text=f"{icon} {i+1}. {name}",
                           bg=_PANEL, fg=_FG2, font=_FS, pady=14)
            lbl.pack()
            self._step_btns.append(lbl)
            if i < len(self.STEPS)-1:
                tk.Label(self._bar, text="│", bg=_PANEL,
                         fg=_FG3, font=_F).pack(side=tk.LEFT)

        # İçerik
        self._area = tk.Frame(self, bg=_BG)
        self._area.pack(fill=tk.BOTH, expand=True)

        # Alt navigasyon
        nav = tk.Frame(self, bg=_PANEL, height=58)
        nav.pack(fill=tk.X, side=tk.BOTTOM)
        nav.pack_propagate(False)

        self._btn_back = _btn(nav, "◀  Geri",  self._go_back, "ghost")
        self._btn_back.pack(side=tk.LEFT, padx=16, pady=10)
        self._btn_cancel = _btn(nav, "İptal", self.destroy, "ghost")
        self._btn_cancel.pack(side=tk.RIGHT, padx=16, pady=10)
        self._btn_next = _btn(nav, "İleri  ▶", self._go_next, "primary")
        self._btn_next.pack(side=tk.RIGHT, padx=(0,8), pady=10)

    def _update_bar(self):
        for i, lbl in enumerate(self._step_btns):
            if i < self._step:
                lbl.configure(fg=_GREEN, bg=_PANEL)
            elif i == self._step:
                lbl.configure(fg="white", bg=_ACC1)
            else:
                lbl.configure(fg=_FG2, bg=_PANEL)
        self._btn_back.configure(
            state=tk.NORMAL if self._step > 0 else tk.DISABLED)
        last = self._step == len(self.STEPS)-1
        self._btn_next.configure(
            text="✓  Öğrenmeyi Başlat" if last else "İleri  ▶",
            bg=_GREEN if last else _ACC1)

    def _show_step(self, n):
        for w in self._area.winfo_children():
            w.destroy()
        self._step = n
        self._update_bar()
        [self._s1, self._s2, self._s3, self._s4, self._s5, self._s6][n]()
        # Canvas'ın gerçek boyutunu alıp iç frame'i genişletmesi için
        self._area.update_idletasks()

    def _go_next(self):
        if not self._validate():
            return
        if self._step < len(self.STEPS)-1:
            self._show_step(self._step+1)
        else:
            self._start()

    def _go_back(self):
        if self._step > 0:
            self._show_step(self._step-1)

    def _validate(self) -> bool:
        if self._step == 0:
            if not self.ms_path_var.get():
                messagebox.showwarning("Eksik", "El yazması PDF seçin.", parent=self)
                return False
            if not self.trans_path_var.get():
                messagebox.showwarning("Eksik", "Transkripsiyon kaynağı seçin.", parent=self)
                return False
        if self._step == 1:
            if self.ms_start_var.get() >= self.ms_end_var.get():
                messagebox.showwarning("Hata",
                    "Başlangıç sayfası bitiş sayfasından küçük olmalı.", parent=self)
                return False
        return True

    # ════════════════════════════════════════════════════════════════
    #  ADIM 1 — Kaynak Seçimi
    # ════════════════════════════════════════════════════════════════

    # Desteklenen dosya türleri
    _FT_YAZI = [
        ("PDF / Görüntü",   "*.pdf *.tiff *.tif *.jpg *.jpeg *.png *.bmp *.webp"),
        ("PDF",             "*.pdf"),
        ("Görüntü",         "*.tiff *.tif *.jpg *.jpeg *.png *.bmp *.webp"),
        ("Tüm Dosyalar",    "*.*"),
    ]
    _FT_TRANS = [
        ("PDF / Word / Metin", "*.pdf *.docx *.doc *.txt *.rtf *.odt"),
        ("PDF",                "*.pdf"),
        ("Word Belgesi",       "*.docx *.doc"),
        ("Düz Metin",          "*.txt *.rtf"),
        ("Tüm Dosyalar",       "*.*"),
    ]

    def _s1(self):
        _, scroll = _scrolled_frame(self._area)

        def _file_row(parent, label, var, filetypes, hint=""):
            """Tam genişlik dosya satırı (pack tabanlı)."""
            _lbl(parent, label, font=_FSB, fg=_FG2, bg=_CARD).pack(
                anchor=tk.W, pady=(10, 2), padx=14)
            fr = tk.Frame(parent, bg=_CARD)
            fr.pack(fill=tk.X, padx=14, pady=(0, 4))
            ent = _entry(fr, var, width=52)
            ent.pack(side=tk.LEFT, padx=(0, 6))
            _btn(fr, "📂 Seç",
                 lambda ft=filetypes, v=var: self._browse(v, ft),
                 "ghost").pack(side=tk.LEFT)
            if hint:
                _lbl(fr, hint, fg=_FG3, bg=_CARD, font=_FS).pack(
                    side=tk.LEFT, padx=(8, 0))

        # ─ Kaynak Dosyalar ─
        c1 = _card(scroll, padx=0, pady=0)
        c1.pack(fill=tk.X, padx=16, pady=(14, 6))
        _section(c1, "Kaynak Dosyalar", "📄").pack(fill=tk.X)

        _file_row(c1, "El Yazması (PDF / TIFF / JPG / PNG …):",
                  self.ms_path_var, self._FT_YAZI,
                  "pdf · tiff · jpg · png · bmp · webp")
        _file_row(c1, "Transkripsiyon Kaynağı (PDF / Word / Metin …):",
                  self.trans_path_var, self._FT_TRANS,
                  "pdf · docx · txt · rtf · odt")

        # Kaynak türü
        kt_fr = tk.Frame(c1, bg=_CARD)
        kt_fr.pack(anchor=tk.W, padx=14, pady=(4, 12))
        _lbl(kt_fr, "Kaynak türü:", bg=_CARD, fg=_FG2, font=_FSB).pack(
            side=tk.LEFT, padx=(0, 10))
        for val, lbl_text in [
            ("transkripsiyon", "Transkripsiyon"),
            ("tez",            "Tez"),
            ("baskı",          "Matbu Baskı"),
            ("dijital",        "Dijital Edisyon"),
        ]:
            tk.Radiobutton(kt_fr, text=lbl_text, variable=self.kaynak_turu_var,
                           value=val, bg=_CARD, fg=_FG, font=_FS,
                           selectcolor="#1c2035",
                           activebackground=_CARD).pack(side=tk.LEFT, padx=6)

        # ─ Eser Kimliği (grid body ayrı frame içinde) ─
        c2 = _card(scroll, padx=0, pady=0)
        c2.pack(fill=tk.X, padx=16, pady=6)
        _section(c2, "Eser Kimliği", "📋").pack(fill=tk.X)

        body2 = tk.Frame(c2, bg=_CARD)
        body2.pack(fill=tk.X, padx=14, pady=10)
        body2.columnconfigure(1, weight=1)
        body2.columnconfigure(3, weight=1)

        def _id_row(r, c, label, var, width=26):
            _lbl(body2, label, bg=_CARD, fg=_FG2, font=_FSB).grid(
                row=r, column=c * 2, sticky=tk.W, padx=(0, 4), pady=5)
            _entry(body2, var, width=width).grid(
                row=r, column=c * 2 + 1, sticky=tk.EW, padx=(0, 18), pady=5)

        _id_row(0, 0, "Eser Adı:",       self.eser_adi_var,  32)
        _id_row(1, 0, "Yazar:",           self.yazar_var,     32)
        _id_row(2, 0, "Müstensih:",       self.muellif_var)
        _id_row(2, 1, "İstinsah Tar.:",   self.tarih_var,     16)
        _id_row(3, 0, "Kütüphane:",       self.kutuphane_var)
        _id_row(3, 1, "Dem. No:",         self.demir_no_var,  16)
        _id_row(4, 0, "Tez / Kaynak:",    self.tez_ref_var,   32)

        # ─ İpucu ─
        tip = tk.Frame(scroll, bg="#0d1e10")
        tip.pack(fill=tk.X, padx=16, pady=(4, 14))
        tk.Label(tip,
                 text="💡  El yazması: PDF, TIFF veya görüntü dosyası (JPG/PNG/BMP/WebP).\n"
                      "Transkripsiyon: eserin matbu/dijital baskısı, tez transkripsiyonu, "
                      "Word belgesi veya düz metin.\n"
                      "Program bu çiftlerden öğrenerek benzer yazmaları daha isabetli okur.",
                 bg="#0d1e10", fg="#6dbf7e", font=_FS,
                 wraplength=660, justify=tk.LEFT, pady=8, padx=12).pack()

    def _browse(self, var: tk.StringVar, filetypes: list):
        p = filedialog.askopenfilename(
            filetypes=filetypes,
            title="Dosya Seç",
        )
        if p:
            var.set(p)
            if var is self.ms_path_var and not self.eser_adi_var.get():
                stem = Path(p).stem.replace("_", " ").replace("-", " ")
                self.eser_adi_var.set(stem)

    # ════════════════════════════════════════════════════════════════
    #  ADIM 2 — Varak & Satır Bilgisi
    # ════════════════════════════════════════════════════════════════

    def _s2(self):
        _, scroll = _scrolled_frame(self._area)

        # Sayfa aralıkları
        c1 = _card(scroll, padx=0, pady=0)
        c1.pack(fill=tk.X, padx=16, pady=(14,6))
        _section(c1, "İşlenecek Sayfa Aralıkları", "📐").pack(fill=tk.X)

        pr = tk.Frame(c1, bg=_CARD)
        pr.pack(fill=tk.X, padx=12, pady=8)

        def _pg_grp(parent, title, s_var, e_var, col):
            g = tk.LabelFrame(parent, text=title, bg=_CARD, fg=_FG2,
                               font=_FSB, padx=10, pady=8)
            g.grid(row=0, column=col, padx=(0,12), sticky=tk.W)
            _lbl(g, "Başlangıç:", bg=_CARD, fg=_FG).grid(row=0,column=0,sticky=tk.W,pady=3)
            _spin(g, s_var).grid(row=0, column=1, padx=6, pady=3)
            _lbl(g, "Bitiş:", bg=_CARD, fg=_FG).grid(row=1,column=0,sticky=tk.W,pady=3)
            _spin(g, e_var).grid(row=1, column=1, padx=6, pady=3)

        _pg_grp(pr, "El Yazması Sayfaları", self.ms_start_var, self.ms_end_var, 0)

        sync_f = tk.Frame(pr, bg=_CARD)
        sync_f.grid(row=0, column=1, padx=12, sticky=tk.N, pady=4)
        tk.Checkbutton(sync_f, text="Sayfa numaraları\naynı",
                       variable=self.sync_var, command=self._toggle_sync,
                       bg=_CARD, fg=_FG, font=_FS,
                       selectcolor="#1c2035",
                       activebackground=_CARD).pack()

        self._tr_grp_frame = tk.Frame(pr, bg=_CARD)
        self._tr_grp_frame.grid(row=0, column=2, sticky=tk.W)
        _pg_grp(self._tr_grp_frame, "Transkripsiyon Sayfaları",
                self.tr_start_var, self.tr_end_var, 0)
        self._toggle_sync()

        # Toplam varak
        tv_f = tk.Frame(c1, bg=_CARD)
        tv_f.pack(anchor=tk.W, padx=12, pady=(0,8))
        _lbl(tv_f, "Toplam Varak Sayısı (opsiyonel):",
             bg=_CARD, fg=_FG2, font=_FSB).pack(side=tk.LEFT, padx=(0,8))
        _spin(tv_f, self.toplam_varak_var, lo=0).pack(side=tk.LEFT)
        _lbl(tv_f, "  Sütun:", bg=_CARD, fg=_FG2, font=_FSB).pack(side=tk.LEFT, padx=(16,8))
        _spin(tv_f, self.sutun_var, lo=1, hi=5, width=4).pack(side=tk.LEFT)

        # Satır bilgisi
        c2 = _card(scroll, padx=0, pady=0)
        c2.pack(fill=tk.X, padx=16, pady=6)
        _section(c2, "Satır Sayısı Bilgisi", "📏").pack(fill=tk.X)

        sb_f = tk.Frame(c2, bg=_CARD)
        sb_f.pack(fill=tk.X, padx=12, pady=8)

        # Düzenli mi?
        reg_f = tk.Frame(sb_f, bg=_CARD)
        reg_f.pack(anchor=tk.W, pady=(0,8))
        tk.Checkbutton(reg_f, text="Satır sayısı düzenli (sabit)",
                       variable=self.duzenli_var, command=self._toggle_duzenli,
                       bg=_CARD, fg=_FG, font=_F,
                       selectcolor="#1c2035",
                       activebackground=_CARD).pack(side=tk.LEFT)

        row1 = tk.Frame(sb_f, bg=_CARD)
        row1.pack(anchor=tk.W, pady=3)

        _lbl(row1, "Genel satır:", bg=_CARD, fg=_FG, font=_FSB).pack(side=tk.LEFT, padx=(0,6))
        _spin(row1, self.satir_min_var, width=5).pack(side=tk.LEFT)
        self._max_frame = tk.Frame(row1, bg=_CARD)
        self._max_frame.pack(side=tk.LEFT)
        _lbl(self._max_frame, " – ", bg=_CARD, fg=_FG2).pack(side=tk.LEFT)
        _spin(self._max_frame, self.satir_max_var, width=5).pack(side=tk.LEFT)
        _lbl(row1, "  satır", bg=_CARD, fg=_FG2, font=_FS).pack(side=tk.LEFT)

        # Özel varaklar
        row2 = tk.Frame(sb_f, bg=_CARD)
        row2.pack(anchor=tk.W, pady=6)

        def _ozel(parent, label, var, lo=0):
            _lbl(parent, label, bg=_CARD, fg=_FG2, font=_FSB).pack(side=tk.LEFT, padx=(0,6))
            _spin(parent, var, lo=lo, width=5).pack(side=tk.LEFT)
            _lbl(parent, "  ", bg=_CARD, fg=_FG).pack(side=tk.LEFT)

        _ozel(row2, "İlk varak:", self.ilk_varak_satir_var)
        _ozel(row2, "Son varak:", self.son_varak_satir_var)
        _ozel(row2, "Başlık sayfası:", self.baslik_satir_var)
        _lbl(row2, "(0 = genel ile aynı)", bg=_CARD, fg=_FG3, font=_FS).pack(side=tk.LEFT)

        row3 = tk.Frame(sb_f, bg=_CARD)
        row3.pack(anchor=tk.W, pady=4, fill=tk.X)
        _lbl(row3, "Özel varaklar (örn. 1a:12, 45b:18):",
             bg=_CARD, fg=_FG2, font=_FSB).pack(side=tk.LEFT, padx=(0,6))
        _entry(row3, self.ozel_varaklar_var, width=36).pack(side=tk.LEFT)

        row4 = tk.Frame(sb_f, bg=_CARD)
        row4.pack(anchor=tk.W, pady=4, fill=tk.X)
        _lbl(row4, "Notlar:", bg=_CARD, fg=_FG2, font=_FSB).pack(side=tk.LEFT, padx=(0,6))
        _entry(row4, self.varak_not_var, width=52).pack(side=tk.LEFT)

        self._toggle_duzenli()

    def _toggle_sync(self):
        s = tk.DISABLED if self.sync_var.get() else tk.NORMAL
        for w in self._tr_grp_frame.winfo_children():
            try:
                for ww in w.winfo_children():
                    try: ww.configure(state=s)
                    except Exception: pass
            except Exception:
                pass

    def _toggle_duzenli(self):
        state = tk.DISABLED if self.duzenli_var.get() else tk.NORMAL
        for w in self._max_frame.winfo_children():
            try: w.configure(state=state)
            except Exception: pass

    # ════════════════════════════════════════════════════════════════
    #  ADIM 3 — İmla Hususiyetleri
    # ════════════════════════════════════════════════════════════════

    def _s3(self):
        _, scroll = _scrolled_frame(self._area)

        for grp_name, items in IMLA_OZELLIKLERI.items():
            c = _card(scroll, padx=0, pady=0)
            c.pack(fill=tk.X, padx=16, pady=4)
            _section(c, grp_name, "☑").pack(fill=tk.X)

            grid = tk.Frame(c, bg=_CARD)
            grid.pack(fill=tk.X, padx=12, pady=6)
            for i, item in enumerate(items):
                var = self.imla_vars[item]
                cb  = tk.Checkbutton(grid, text=item, variable=var,
                                     bg=_CARD, fg=_FG, font=_FS,
                                     selectcolor="#1c2035",
                                     activebackground=_CARD,
                                     wraplength=320, justify=tk.LEFT,
                                     anchor=tk.W)
                cb.grid(row=i//2, column=i%2, sticky=tk.W, padx=8, pady=2)

        # Serbest metin
        c2 = _card(scroll, padx=0, pady=0)
        c2.pack(fill=tk.X, padx=16, pady=4)
        _section(c2, "Serbest İmla Açıklaması", "✏").pack(fill=tk.X)
        sf = tk.Frame(c2, bg=_CARD)
        sf.pack(fill=tk.X, padx=12, pady=8)
        _lbl(sf, "Bu yazmanın özel imla özellikleri:", bg=_CARD, fg=_FG2, font=_FSB).pack(anchor=tk.W)
        self._imla_text = tk.Text(sf, height=4, width=72,
                                   bg="#1c2035", fg=_FG, font=_F,
                                   insertbackground=_FG, relief=tk.FLAT,
                                   highlightbackground=_BORDER, highlightthickness=1,
                                   padx=6, pady=4, wrap=tk.WORD)
        self._imla_text.pack(fill=tk.X, pady=(4,0))
        if self.imla_serbest_var.get():
            self._imla_text.insert("1.0", self.imla_serbest_var.get())

        # Aktarım ilkeleri
        c3 = _card(scroll, padx=0, pady=0)
        c3.pack(fill=tk.X, padx=16, pady=(4,14))
        _section(c3, "Aktarım / Transkripsiyon İlkeleri", "📜").pack(fill=tk.X)
        af = tk.Frame(c3, bg=_CARD)
        af.pack(fill=tk.X, padx=12, pady=8)
        _lbl(af, "Bu kaynakta uygulanan transkripsiyon kuralları:", bg=_CARD, fg=_FG2, font=_FSB).pack(anchor=tk.W)
        self._aktarim_text = tk.Text(af, height=3, width=72,
                                      bg="#1c2035", fg=_FG, font=_F,
                                      insertbackground=_FG, relief=tk.FLAT,
                                      highlightbackground=_BORDER, highlightthickness=1,
                                      padx=6, pady=4, wrap=tk.WORD)
        self._aktarim_text.pack(fill=tk.X, pady=(4,0))

    # ════════════════════════════════════════════════════════════════
    #  ADIM 4 — Metin Yapısı
    # ════════════════════════════════════════════════════════════════

    def _s4(self):
        _, scroll = _scrolled_frame(self._area)

        info = tk.Frame(scroll, bg="#1a1e10")
        info.pack(fill=tk.X, padx=16, pady=(14,8))
        tk.Label(info,
                 text="📑  Transkripsiyon kaynağında hangi bölümler var ve kaçıncı sayfalarda?\n"
                      "Bu bilgi, yalnızca metin kısmını öğrenmek için doğru sayfaları seçmeye yarar.",
                 bg="#1a1e10", fg="#b8cc70", font=_FS,
                 wraplength=680, justify=tk.LEFT, pady=8, padx=12).pack()

        # Sütun başlıkları
        ch = tk.Frame(scroll, bg=_CARD)
        ch.pack(fill=tk.X, padx=16, pady=(0,2))
        for txt, w in [("Bölüm Adı",36), ("Başl. Sayfa",12), ("Bitiş Sayfa",12), ("Not",22), ("",6)]:
            tk.Label(ch, text=txt, bg=_CARD, fg=_FG2, font=_FSB,
                     width=w, anchor=tk.W).pack(side=tk.LEFT, padx=2)

        self._bolum_frame = tk.Frame(scroll, bg=_BG)
        self._bolum_frame.pack(fill=tk.X, padx=16)

        # Hızlı ekle
        quick = tk.Frame(scroll, bg=_BG)
        quick.pack(fill=tk.X, padx=16, pady=8)
        _lbl(quick, "Hızlı Ekle:", fg=_FG2, font=_FSB).pack(side=tk.LEFT, padx=(0,8))
        for b in METIN_BOLUMLERI[:8]:
            tk.Button(quick, text=b,
                      command=lambda name=b: self._add_bolum(name),
                      font=_FS, bg="#1e2a45", fg=_FG,
                      relief=tk.FLAT, bd=0, padx=8, pady=4,
                      cursor="hand2").pack(side=tk.LEFT, padx=2)

        row_add = tk.Frame(scroll, bg=_BG)
        row_add.pack(anchor=tk.W, padx=16, pady=4)
        _btn(row_add, "➕  Bölüm Ekle", lambda: self._add_bolum(""), "ghost").pack(side=tk.LEFT)

        # Mevcut satırları yeniden oluştur
        for row in self._bolum_rows:
            self._render_bolum_row(row)

    def _add_bolum(self, name=""):
        row = {
            "ad":   tk.StringVar(value=name),
            "bas":  tk.IntVar(value=0),
            "bit":  tk.IntVar(value=0),
            "not_": tk.StringVar(),
        }
        self._bolum_rows.append(row)
        self._render_bolum_row(row)

    def _render_bolum_row(self, row):
        f = tk.Frame(self._bolum_frame, bg=_CARD)
        f.pack(fill=tk.X, pady=2)
        row["_frame"] = f
        cb = ttk.Combobox(f, textvariable=row["ad"],
                          values=METIN_BOLUMLERI, width=34, font=_FS)
        cb.pack(side=tk.LEFT, padx=2)
        for var, w in [(row["bas"],8),(row["bit"],8)]:
            _spin(f, var, lo=0, width=w).pack(side=tk.LEFT, padx=2)
        _entry(f, row["not_"], width=20).pack(side=tk.LEFT, padx=2)
        _btn(f, "✖", lambda fr=f, r=row: self._del_bolum(fr, r), "danger").pack(
            side=tk.LEFT, padx=4)

    def _del_bolum(self, frame, row):
        frame.destroy()
        if row in self._bolum_rows:
            self._bolum_rows.remove(row)

    # ════════════════════════════════════════════════════════════════
    #  ADIM 5 — Alan Bilgisi & Paleografi
    # ════════════════════════════════════════════════════════════════

    def _s5(self):
        _, scroll = _scrolled_frame(self._area)

        # Alan bilgisi
        c1 = _card(scroll, padx=0, pady=0)
        c1.pack(fill=tk.X, padx=16, pady=(14,6))
        _section(c1, "Alan ve Yazı Bilgisi", "🔤").pack(fill=tk.X)

        g = tk.Frame(c1, bg=_CARD)
        g.pack(fill=tk.X, padx=12, pady=8)

        def _frow(parent, label, widget_fn, r, c=0):
            _lbl(parent, label, bg=_CARD, fg=_FG2, font=_FSB).grid(
                row=r, column=c*2, sticky=tk.W, pady=5, padx=(0,8))
            widget_fn().grid(row=r, column=c*2+1, sticky=tk.W, pady=5, padx=(0,20))

        _frow(g, "Alan:",       lambda: _combo(g, self.alan_var,   ALANLAR,    22), 0, 0)
        _frow(g, "Dönem:",      lambda: _combo(g, self.donem_var,  DONEMLER,   22), 1, 0)
        _frow(g, "Yazı Türü:",  lambda: _combo(g, self.yazi_var,   YAZI_TURLERI, 22), 2, 0)
        _frow(g, "Hareke:",     lambda: _combo(g, self.hareke_var, HAREKE_DURUMLARI, 22), 3, 0)
        _frow(g, "Dil Kodu:",   lambda: _combo(g, self.dil_var,
                                               ["ara","tur","tur+ara","fas","deu","eng"], 10), 4, 0)

        # Güven
        gf = tk.Frame(c1, bg=_CARD)
        gf.pack(anchor=tk.W, padx=12, pady=(0,10))
        _lbl(gf, "Transkripsiyon Güveni:", bg=_CARD, fg=_FG2, font=_FSB).pack(side=tk.LEFT)
        self._guven_lbl = _lbl(gf, f"%{int(self.guven_var.get()*100)}",
                                bg=_CARD, fg=_GREEN, font=_FB)
        self._guven_lbl.pack(side=tk.LEFT, padx=8)
        tk.Scale(gf, variable=self.guven_var, from_=0.1, to=1.0, resolution=0.05,
                 orient=tk.HORIZONTAL, length=220, bg=_CARD, fg=_FG,
                 troughcolor=_PANEL, highlightthickness=0, showvalue=False,
                 command=lambda v: self._guven_lbl.configure(
                     text=f"%{int(float(v)*100)}")
                 ).pack(side=tk.LEFT)

        # Harf formları (temel)
        c2 = _card(scroll, padx=0, pady=0)
        c2.pack(fill=tk.X, padx=16, pady=6)
        _section(c2, "Harf Formları (Paleografi Notu)", "حـ").pack(fill=tk.X)

        hf_info = tk.Label(c2,
                           text="Yazmanın tanıtımında/tezinde harf biçimlerine dair bilgi varsa girebilirsiniz.\n"
                                "Harf · Konum (baş/orta/son) · Örnek kelime · Açıklama",
                           bg=_CARD, fg=_FG2, font=_FS,
                           justify=tk.LEFT, anchor=tk.W, padx=12, pady=6)
        hf_info.pack(fill=tk.X)

        # Sütun başlıkları
        hch = tk.Frame(c2, bg=_CARD)
        hch.pack(fill=tk.X, padx=12, pady=(0,2))
        for txt, w in [("Harf",8),("Konum",12),("Örnek Kelime",16),("Açıklama",28),("",5)]:
            tk.Label(hch, text=txt, bg=_CARD, fg=_FG3, font=_FSB,
                     width=w, anchor=tk.W).pack(side=tk.LEFT, padx=2)

        self._harf_frame = tk.Frame(c2, bg=_CARD)
        self._harf_frame.pack(fill=tk.X, padx=12, pady=4)

        for row in self._harf_rows:
            self._render_harf_row(row)

        _btn(c2, "➕  Harf Formu Ekle",
             self._add_harf, "ghost").pack(anchor=tk.W, padx=12, pady=(4,10))

        # Genel notlar
        c3 = _card(scroll, padx=0, pady=0)
        c3.pack(fill=tk.X, padx=16, pady=(6,14))
        _section(c3, "Genel Notlar", "📝").pack(fill=tk.X)
        nf = tk.Frame(c3, bg=_CARD)
        nf.pack(fill=tk.X, padx=12, pady=8)
        self._not_text = tk.Text(nf, height=4, width=72,
                                  bg="#1c2035", fg=_FG, font=_F,
                                  insertbackground=_FG, relief=tk.FLAT,
                                  highlightbackground=_BORDER, highlightthickness=1,
                                  padx=6, pady=4, wrap=tk.WORD)
        self._not_text.pack(fill=tk.X)
        if self.ozel_not_var.get():
            self._not_text.insert("1.0", self.ozel_not_var.get())

    def _add_harf(self):
        row = {
            "harf":   tk.StringVar(),
            "konum":  tk.StringVar(value="baş"),
            "kelime": tk.StringVar(),
            "acikl":  tk.StringVar(),
        }
        self._harf_rows.append(row)
        self._render_harf_row(row)

    def _render_harf_row(self, row):
        f = tk.Frame(self._harf_frame, bg=_CARD)
        f.pack(fill=tk.X, pady=2)
        row["_frame"] = f
        _entry(f, row["harf"],   width=6).pack(side=tk.LEFT, padx=2)
        _combo(f, row["konum"],  ["baş","orta","son","bağımsız"], width=10).pack(side=tk.LEFT, padx=2)
        _entry(f, row["kelime"], width=14).pack(side=tk.LEFT, padx=2)
        _entry(f, row["acikl"],  width=26).pack(side=tk.LEFT, padx=2)
        _btn(f, "✖", lambda fr=f, r=row: self._del_harf(fr, r), "danger").pack(
            side=tk.LEFT, padx=4)

    def _del_harf(self, frame, row):
        frame.destroy()
        if row in self._harf_rows:
            self._harf_rows.remove(row)

    # ════════════════════════════════════════════════════════════════
    #  ADIM 6 — Özet & Başlat
    # ════════════════════════════════════════════════════════════════

    def _s6(self):
        _, scroll = _scrolled_frame(self._area)

        # ── Özet kartı ───────────────────────────────────────────
        c = _card(scroll, padx=0, pady=0)
        c.pack(fill=tk.X, padx=16, pady=(14, 6))
        _section(c, "Öğrenme Özeti", "📋").pack(fill=tk.X)

        sf = tk.Frame(c, bg=_CARD)
        sf.pack(fill=tk.X, padx=12, pady=8)

        imla_sec = [k for k, v in self.imla_vars.items() if v.get()]
        bolumler = [r for r in self._bolum_rows if r["ad"].get()]
        harf_f   = [r for r in self._harf_rows if r["harf"].get()]
        pg_count = self.ms_end_var.get() - self.ms_start_var.get()
        satir_oz = (f"{self.satir_min_var.get()} satır (sabit)"
                    if self.duzenli_var.get()
                    else f"{self.satir_min_var.get()}–{self.satir_max_var.get()} satır")

        ozet_rows = [
            ("Eser",           self.eser_adi_var.get() or "(isimsiz)"),
            ("El Yazması",     Path(self.ms_path_var.get()).name
                               if self.ms_path_var.get() else "—"),
            ("Transkripsiyon", Path(self.trans_path_var.get()).name
                               if self.trans_path_var.get() else "—"),
            ("Sayfalar",       f"{self.ms_start_var.get()}–{self.ms_end_var.get()}"
                               f"  ({pg_count} sayfa)"),
            ("Alan / Dönem",   f"{self.alan_var.get()} · {self.donem_var.get()}"),
            ("Yazı / Hareke",  f"{self.yazi_var.get()} · {self.hareke_var.get()}"),
            ("Satır",          satir_oz),
            ("İmla",           f"{len(imla_sec)} özellik seçili"),
            ("Metin Bölümü",   f"{len(bolumler)} bölüm"),
            ("Harf Formu",     f"{len(harf_f)} kayıt"),
            ("Güven",          f"%{int(self.guven_var.get() * 100)}"),
        ]

        # 2 sütun grid
        body6 = tk.Frame(sf, bg=_CARD)
        body6.pack(fill=tk.X)
        for idx, (lbl, val) in enumerate(ozet_rows):
            r, col = divmod(idx, 2)
            tk.Label(body6, text=f"{lbl}:", bg=_CARD, fg=_FG2,
                     font=_FSB, width=16, anchor=tk.W).grid(
                row=r, column=col * 2, sticky=tk.W, padx=(0, 4), pady=3)
            tk.Label(body6, text=val, bg=_CARD, fg=_FG,
                     font=_F, anchor=tk.W, wraplength=220).grid(
                row=r, column=col * 2 + 1, sticky=tk.W, padx=(0, 24), pady=3)

        # ── İlerleme Paneli (başta gizli, öğrenme başlayınca görünür) ──
        self._prog_panel = _card(scroll, padx=0, pady=0)
        self._prog_panel.pack(fill=tk.X, padx=16, pady=(8, 14))
        _section(self._prog_panel, "Öğrenme İlerlemesi", "⏳").pack(fill=tk.X)

        pf = tk.Frame(self._prog_panel, bg=_CARD)
        pf.pack(fill=tk.X, padx=14, pady=10)

        # Büyük ilerleme çubuğu
        self._prog_bar = ttk.Progressbar(pf, mode="determinate", length=600)
        self._prog_bar.pack(fill=tk.X, pady=(0, 6))

        # Sayfa / yüzde satırı
        row_pct = tk.Frame(pf, bg=_CARD)
        row_pct.pack(fill=tk.X, pady=2)
        self._prog_pct_lbl = tk.Label(
            row_pct, text="—", bg=_CARD, fg=_GREEN,
            font=("Segoe UI", 22, "bold"), anchor=tk.W)
        self._prog_pct_lbl.pack(side=tk.LEFT)
        self._prog_sayfa_lbl = tk.Label(
            row_pct, text="", bg=_CARD, fg=_FG,
            font=_FB, anchor=tk.W)
        self._prog_sayfa_lbl.pack(side=tk.LEFT, padx=(12, 0))

        # Süre satırı
        self._prog_sure_lbl = _lbl(pf, "", fg=_FG2, font=_FS)
        self._prog_sure_lbl.pack(anchor=tk.W, pady=(2, 8))

        # Kontrol butonları
        ctrl = tk.Frame(pf, bg=_CARD)
        ctrl.pack(anchor=tk.W, pady=(4, 0))

        self._pause_btn = _btn(ctrl, "⏸  Mola Ver",
                               self._toggle_pause, "ghost")
        self._pause_btn.pack(side=tk.LEFT, padx=(0, 8))

        self._stop_btn = _btn(ctrl, "⏹  Durdur ve Kaydet",
                              self._stop_learning, "danger")
        self._stop_btn.pack(side=tk.LEFT)

        self._ctrl_info_lbl = _lbl(ctrl,
            "  ← İşlenen kısım kaydedilir, yarım kalmaz.",
            fg=_FG3, font=_FS)
        self._ctrl_info_lbl.pack(side=tk.LEFT, padx=(12, 0))

        # Başlangıçta durum etiketi
        self._prog_status_lbl = _lbl(pf,
            "▶  Öğrenmeyi başlatmak için sağ alttaki butona tıklayın.",
            fg=_FG2, font=_FS)
        self._prog_status_lbl.pack(anchor=tk.W, pady=(10, 0))

        # Butonlar başlangıçta devre dışı (henüz başlamadı)
        self._pause_btn.configure(state=tk.DISABLED)
        self._stop_btn.configure(state=tk.DISABLED)

    # ════════════════════════════════════════════════════════════════
    #  Öğrenmeyi Başlat
    # ════════════════════════════════════════════════════════════════

    def _build_meta(self) -> ManuscriptMeta:
        """UI değerlerinden ManuscriptMeta oluşturur."""
        # İmla serbest metni
        try:
            imla_st = self._imla_text.get("1.0", tk.END).strip()
        except Exception:
            imla_st = self.imla_serbest_var.get()
        try:
            aktarim = self._aktarim_text.get("1.0", tk.END).strip()
        except Exception:
            aktarim = self.aktarim_ilk_var.get()
        try:
            notlar = self._not_text.get("1.0", tk.END).strip()
        except Exception:
            notlar = self.ozel_not_var.get()

        varak = VarakSatirBilgisi(
            genel_min     = self.satir_min_var.get(),
            genel_max     = self.satir_max_var.get(),
            duzenli       = self.duzenli_var.get(),
            ilk_varak     = self.ilk_varak_satir_var.get(),
            son_varak     = self.son_varak_satir_var.get(),
            baslik_varak  = self.baslik_satir_var.get(),
            ozel_varaklar = self.ozel_varaklar_var.get(),
            notlar        = self.varak_not_var.get(),
        )

        bolumleri = [
            MetinBolumu(ad=r["ad"].get(), baslangic=r["bas"].get(),
                        bitis=r["bit"].get(), aciklama=r["not_"].get())
            for r in self._bolum_rows if r["ad"].get()
        ]

        harf_f = [
            HarfFormu(harf=r["harf"].get(), konum=r["konum"].get(),
                      ornek_kelime=r["kelime"].get(), aciklama=r["acikl"].get())
            for r in self._harf_rows if r["harf"].get()
        ]

        return ManuscriptMeta(
            eser_adi        = self.eser_adi_var.get().strip(),
            yazar           = self.yazar_var.get().strip(),
            muellif         = self.muellif_var.get().strip(),
            istinsah_tarihi = self.tarih_var.get().strip(),
            kutuphanesi     = self.kutuphane_var.get().strip(),
            demirbaş_no     = self.demir_no_var.get().strip(),
            tez_referansi   = self.tez_ref_var.get().strip(),
            alan            = self.alan_var.get(),
            donem           = self.donem_var.get(),
            yazi_turu       = self.yazi_var.get(),
            hareke          = self.hareke_var.get(),
            dil_kodu        = self.dil_var.get(),
            sutun_sayisi    = self.sutun_var.get(),
            toplam_varak    = self.toplam_varak_var.get(),
            varak_satir     = varak,
            imla_secimler   = [k for k, v in self.imla_vars.items() if v.get()],
            imla_serbest    = imla_st,
            aktarim_ilkeleri = aktarim,
            metin_bolumleri = bolumleri,
            kaynak_turu     = self.kaynak_turu_var.get(),
            harf_formlari   = harf_f,
            ozel_notlar     = notlar,
            guven           = self.guven_var.get(),
        )

    # ── Öğrenme kontrolü ────────────────────────────────────────────

    def _toggle_pause(self):
        """Mola ver / Devam et."""
        if not hasattr(self, "_pause_event"):
            return
        if self._pause_event.is_set():
            # Molada → devam et
            self._pause_event.clear()
            self._pause_btn.configure(text="⏸  Mola Ver", bg="#2a3050")
            self._prog_status_lbl.configure(
                text="▶  Devam ediyor…", fg=_FG2)
        else:
            # Çalışıyor → molaya al
            self._pause_event.set()
            self._pause_btn.configure(text="▶  Devam Et", bg=_AMBER)
            self._prog_status_lbl.configure(
                text="⏸  Mola verildi — 'Devam Et' ile sürdürün.", fg=_AMBER)

    def _stop_learning(self):
        """Dur sinyali gönder — işlenen kısmı kaydet."""
        if not hasattr(self, "_stop_event"):
            return
        # Molayı kaldır (varsa) ki thread ilerleyip durdurma sinyalini görsün
        if hasattr(self, "_pause_event"):
            self._pause_event.clear()
        self._stop_event.set()
        self._stop_btn.configure(state=tk.DISABLED, text="⏳  Durduruluyor…")
        self._pause_btn.configure(state=tk.DISABLED)
        self._prog_status_lbl.configure(
            text="⏹  Durduruluyor, işlenen kısım kaydediliyor…", fg=_AMBER)

    def _start(self):
        # Kontrol olayları
        self._stop_event  = threading.Event()
        self._pause_event = threading.Event()   # set = molada
        self._start_time  = time.time()

        # Navigasyon kilitle
        self._btn_next.configure(state=tk.DISABLED, text="⏳  İşleniyor…")
        self._btn_back.configure(state=tk.DISABLED)

        # Kontrol butonlarını aktif et
        self._pause_btn.configure(state=tk.NORMAL)
        self._stop_btn.configure(state=tk.NORMAL)
        self._prog_status_lbl.configure(
            text="▶  Öğrenme başladı…", fg=_FG2)

        # Sayfa aralıkları
        ms_start = self.ms_start_var.get() - 1
        ms_end   = self.ms_end_var.get()
        tr_start = ms_start if self.sync_var.get() else self.tr_start_var.get() - 1
        tr_end   = ms_end   if self.sync_var.get() else self.tr_end_var.get()

        # Metin bölümünden transkripsiyon sayfasını bul
        for row in self._bolum_rows:
            if "Metin Transkripsiyonu" in row["ad"].get() and row["bas"].get() > 0:
                tr_start = row["bas"].get() - 1
                tr_end   = row["bit"].get() or tr_end
                break

        meta = self._build_meta()

        def _run():
            try:
                lib          = get_library()
                count, done_flag = lib.teach(
                    ms_pdf       = Path(self.ms_path_var.get()),
                    trans_source = Path(self.trans_path_var.get()),
                    ms_pages     = (ms_start, ms_end),
                    trans_pages  = (tr_start, tr_end),
                    meta         = meta,
                    progress_cb  = self._on_prog,
                    stop_event   = self._stop_event,
                    pause_event  = self._pause_event,
                )
                self.after(0, lambda: self._on_done(count, done_flag))
            except Exception as exc:
                self.after(0, lambda: self._on_err(str(exc)))

        threading.Thread(target=_run, daemon=True).start()

    def _on_prog(self, done: int, total: int):
        elapsed  = time.time() - self._start_time
        pct      = int(done / max(total, 1) * 100)
        per_page = elapsed / max(done, 1)
        remaining = per_page * (total - done)

        self._prog_bar["value"] = pct
        self._prog_pct_lbl.configure(text=f"%{pct}")
        self._prog_sayfa_lbl.configure(
            text=f"Sayfa {done} / {total}  (Varak/Yaprak: {done})")
        self._prog_sure_lbl.configure(
            text=f"Geçen: {_fmt_dur(elapsed)}"
                 + (f"   ·   Tahmini kalan: {_fmt_dur(remaining)}"
                    if done > 0 and done < total else ""))
        self.update_idletasks()

    def _on_done(self, count: int, completed: bool):
        elapsed = time.time() - self._start_time

        # Kontrol butonlarını kapat
        self._pause_btn.configure(state=tk.DISABLED)
        self._stop_btn.configure(state=tk.DISABLED)

        if completed:
            self._prog_bar["value"] = 100
            self._prog_pct_lbl.configure(text="%100", fg=_GREEN)
            self._prog_sayfa_lbl.configure(
                text=f"Tüm {count} sayfa tamamlandı!", fg=_GREEN)
            self._prog_sure_lbl.configure(
                text=f"Toplam süre: {_fmt_dur(elapsed)}", fg=_FG2)
            self._prog_status_lbl.configure(
                text=f"✅  {count} sayfa çifti başarıyla öğrenildi.",
                fg=_GREEN)
            # Bölüm başlığını güncelle
            try:
                for w in self._prog_panel.winfo_children():
                    if isinstance(w, tk.Frame):
                        for lw in w.winfo_children():
                            if isinstance(lw, tk.Label) and "⏳" in lw.cget("text"):
                                lw.configure(text="  ✅  Öğrenme Tamamlandı")
                                break
            except Exception:
                pass
            # Sesli bildirim (Windows)
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_OK)
            except Exception:
                pass
            messagebox.showinfo(
                "Öğrenme Tamamlandı",
                f"✅  {count} sayfa çifti başarıyla öğrenildi!\n\n"
                f"Toplam süre: {_fmt_dur(elapsed)}\n\n"
                f"Program bundan sonra benzer el yazmalarını\n"
                f"daha doğru okuyacak.",
                parent=self,
            )
        else:
            # Yarıda durduruldu
            self._prog_sayfa_lbl.configure(
                text=f"{count} sayfa kaydedildi (durduruldu)", fg=_AMBER)
            self._prog_status_lbl.configure(
                text=f"⏹  {count} sayfa öğrenildi ve kaydedildi.",
                fg=_AMBER)
            messagebox.showinfo(
                "Öğrenme Durduruldu",
                f"⏹  İşlem durduruldu.\n\n"
                f"{count} sayfa çifti kaydedildi.\n\n"
                f"Kalan sayfaları öğretmek için sihirbazı\n"
                f"tekrar açabilirsiniz.",
                parent=self,
            )

        self._btn_next.configure(text="✓  Kapat", state=tk.NORMAL,
                                  command=self.destroy)
        try:
            from metin_atolyesi.core.github_sync import get_sync
            get_sync().schedule_push(delay=3.0)
        except Exception:
            pass

    def _on_err(self, msg: str):
        self._pause_btn.configure(state=tk.DISABLED)
        self._stop_btn.configure(state=tk.DISABLED)
        self._prog_status_lbl.configure(
            text=f"❌  {msg[:140]}", fg=_ACC2)
        self._prog_pct_lbl.configure(text="✗", fg=_ACC2)
        self._btn_next.configure(text="Yeniden Dene",
                                  state=tk.NORMAL, command=self._start)
        self._btn_back.configure(state=tk.NORMAL)


# ══════════════════════════════════════════════════════════════════════════
#  Kütüphane Görüntüleyici
# ══════════════════════════════════════════════════════════════════════════

class ManuscriptLibraryViewer(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Yazma Kütüphanesi")
        self.geometry("780x520")
        self.configure(bg=_BG)
        self.transient(parent)
        self._build()

    def _build(self):
        top = tk.Frame(self, bg="#0d1117", height=48)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="  📚  Öğrenilmiş Yazma Kütüphanesi",
                 bg="#0d1117", fg=_FG, font=_FH).pack(side=tk.LEFT, padx=16, pady=12)

        lib   = get_library()
        stats = lib.stats()

        sf = tk.Frame(self, bg=_PANEL)
        sf.pack(fill=tk.X, padx=16, pady=8)
        for lbl, val in [("Eser",stats["toplam_eser"]),("Sayfa",stats["toplam_sayfa"])]:
            tk.Label(sf, text=f"  {lbl}: ", bg=_PANEL, fg=_FG2, font=_FSB).pack(side=tk.LEFT)
            tk.Label(sf, text=str(val), bg=_PANEL, fg=_GREEN, font=_FB).pack(side=tk.LEFT)
        for alan, cnt in list(stats.get("alanlar",{}).items())[:5]:
            tk.Label(sf, text=f"  {alan}: {cnt}", bg=_PANEL, fg=_FG2, font=_FS).pack(side=tk.LEFT)

        cols = ("Eser Adı","Alan","Dönem","Yazı","Hareke","Sayfa","Güven")
        tree = ttk.Treeview(self, columns=cols, show="headings", height=16)
        for col, w in zip(cols, [200,130,100,90,90,55,55]):
            tree.heading(col, text=col)
            tree.column(col, width=w, anchor=tk.CENTER if w<100 else tk.W)

        for entry in lib.list_entries():
            m = entry.get("meta", {})
            vs = m.get("varak_satir", {})
            tree.insert("", tk.END, values=(
                entry.get("eser_adi","—"),
                m.get("alan","—"),
                m.get("donem","—"),
                m.get("yazi_turu","—"),
                m.get("hareke","—"),
                len(entry.get("pages",[])),
                f"%{int(m.get('guven',0)*100)}",
            ))

        sb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(16,0), pady=8)
        sb.pack(side=tk.RIGHT, fill=tk.Y, pady=8, padx=(0,8))


def open_wizard(parent):
    ManuscriptWizard(parent)

def open_library_viewer(parent):
    ManuscriptLibraryViewer(parent)
