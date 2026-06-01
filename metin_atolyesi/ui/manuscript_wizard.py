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
    ALANLAR, DONEMLER, HAREKE_DURUMLARI, ICERIK_TURLERI,
    IMLA_OZELLIKLERI, METIN_BOLUMLERI, YAZI_TURLERI,
    DIL_GORUNUM, DIL_GORUNUM_LISTE,
    HarfFormu, ManuscriptMeta, MetinBolumu, VarakSatirBilgisi,
    get_library,
)

# ── Tema — açık, sistem temasıyla uyumlu ─────────────────────────────────
_BG     = "#eceef8"   # ana zemin (açık gri-mavi)
_PANEL  = "#dde0f5"   # panel / nav bar
_CARD   = "#ffffff"   # kart zemin
_BORDER = "#b0b5d5"   # ince kenarlık
_ACC1   = "#0d6efd"   # mavi vurgu
_ACC2   = "#d92b4b"   # kırmızı
_GREEN  = "#1a7a40"   # koyu yeşil (açık zeminde okunabilir)
_AMBER  = "#b37a00"   # koyu amber
_FG     = "#1a1c2e"   # ana metin (koyu)
_FG2    = "#3c4060"   # ikincil metin
_FG3    = "#7078a8"   # üçüncül / placeholder

_F      = ("Segoe UI", 10)
_FB     = ("Segoe UI", 10, "bold")
_FH     = ("Segoe UI", 12, "bold")
_FT     = ("Segoe UI", 14, "bold")
_FS     = ("Segoe UI", 9)
_FSB    = ("Segoe UI", 9, "bold")


# ── Sembolik ikon çizimleri ───────────────────────────────────────────────

def _sayfa_ikon(parent, tip: str, etiket: str):
    """Sayfa formatı sembolik ikonu (Canvas)."""
    W, H = 62, 46
    c = tk.Canvas(parent, width=W, height=H, bg=_PANEL,
                  highlightthickness=1, highlightbackground=_BORDER)
    c.pack(side=tk.LEFT, padx=6)
    if tip == "tek_dikey":
        c.create_rectangle(16, 3, 46, 40, outline=_FG2, fill=_CARD, width=1)
        for y in range(9, 38, 6):
            c.create_line(20, y, 42, y, fill=_FG3, width=1)
    elif tip == "tek_yatay":
        c.create_rectangle(5, 12, 57, 34, outline=_FG2, fill=_CARD, width=1)
        for x in range(11, 54, 10):
            c.create_line(x, 16, x, 30, fill=_FG3, width=1)
    elif tip == "cift_yatay":
        # İki sayfa yan yana
        c.create_rectangle(2, 5, 29, 40, outline=_FG2, fill=_CARD, width=1)
        c.create_rectangle(33, 5, 60, 40, outline=_FG2, fill=_CARD, width=1)
        for y in range(11, 38, 7):
            c.create_line(5, y, 26, y, fill=_FG3, width=1)
            c.create_line(36, y, 57, y, fill=_FG3, width=1)
        # b / a etiket
        c.create_text(15, 43, text="b", fill=_FG3, font=("Segoe UI", 7))
        c.create_text(46, 43, text="a", fill=_FG3, font=("Segoe UI", 7))
    tk.Label(parent, text=etiket, bg=_CARD, fg=_FG3,
             font=("Segoe UI", 7)).pack(side=tk.LEFT, padx=(0, 8))


def _beyit_ikon(parent, tip: str, etiket: str):
    """Beyit satır düzeni sembolik ikonu (Canvas)."""
    W, H = 80, 44
    c = tk.Canvas(parent, width=W, height=H, bg=_PANEL,
                  highlightthickness=1, highlightbackground=_BORDER)
    c.pack(side=tk.LEFT, padx=6)
    if tip == "yan_yana":
        # Dikey ayraç + iki sütun
        c.create_line(40, 5, 40, 39, fill=_FG3, dash=(3, 2))
        for y in (12, 22, 32):
            c.create_line(4, y, 36, y, fill=_ACC1, width=2)
            c.create_line(44, y, 76, y, fill=_FG2, width=1)
    elif tip == "girintili":
        # 1. mısra sola, 2. mısra girintili
        for i, (x1, x2, y, clr) in enumerate([
            (4, 60, 10, _ACC1), (16, 72, 20, _FG2),
            (4, 60, 32, _ACC1), (16, 72, 42, _FG2)
        ]):
            c.create_line(x1, y, x2, y, fill=clr, width=2 if clr==_ACC1 else 1)
    elif tip == "hizali":
        # İki mısra hizalı alt alta
        for y, clr in [(10, _ACC1), (20, _FG2), (32, _ACC1), (42, _FG2)]:
            c.create_line(4, y, 66, y, fill=clr, width=2 if clr==_ACC1 else 1)
    tk.Label(parent, text=etiket, bg=_CARD, fg=_FG3,
             font=("Segoe UI", 7)).pack(side=tk.LEFT, padx=(0, 8))


# ── Çeviri yazı karakterleri ──────────────────────────────────────────────

_CEVIRI_YAZI = [
    # Uzun ünlüler
    "ā", "ī", "ū",
    # Klasik çeviri yazı ünsüzleri
    "ḥ", "ḫ", "ṭ", "ẓ", "ḳ", "ġ", "ś", "ẕ", "ṣ", "ḍ",
    # Hemze / ayn
    "ʿ", "ʾ",
    # Nazal
    "ñ", "ŋ",
    # Diğer
    "š", "č",
    # Eski imlada yaygın
    "â", "î", "û",
]

_ARAP_HARFLERI = list(
    "ا ب پ ت ث ج چ ح خ د ذ ر ز ژ س ش ص ض ط ظ ع غ ف ق ك گ ل م ن و ه ی ة ء".split()
)

def _insert_to_focused(widget_root, char: str):
    """Odaklanmış Entry veya Text widget'ına karakter ekle."""
    try:
        w = widget_root.focus_get()
        if isinstance(w, tk.Entry):
            pos = w.index(tk.INSERT)
            w.insert(pos, char)
        elif isinstance(w, tk.Text):
            w.insert(tk.INSERT, char)
    except Exception:
        pass


def _ceviri_yazi_panel(parent, widget_root):
    """Çeviri yazı işaretleri ve Arap harfleri tıklanabilir paneli."""
    frm = tk.Frame(parent, bg=_PANEL,
                   highlightbackground=_BORDER, highlightthickness=1)
    frm.pack(fill=tk.BOTH, expand=True)

    # Başlık
    tk.Label(frm, text="Çeviri Yazı İşaretleri",
             bg=_PANEL, fg=_FG2, font=_FSB).pack(anchor=tk.W, padx=6, pady=(6,2))

    # Latin/transliterasyon karakterleri — 6 sütunlu grid
    lat_f = tk.Frame(frm, bg=_PANEL)
    lat_f.pack(fill=tk.X, padx=6, pady=2)
    for i, ch in enumerate(_CEVIRI_YAZI):
        tk.Button(lat_f, text=ch, width=3, height=1,
                  font=("Segoe UI", 11),
                  bg="#eaecf4", fg=_FG,
                  activebackground=_ACC1, activeforeground="white",
                  relief=tk.FLAT, bd=0,
                  command=lambda c=ch: _insert_to_focused(widget_root, c)
                  ).grid(row=i // 6, column=i % 6, padx=2, pady=1, sticky=tk.EW)

    # Ayraç
    tk.Frame(frm, bg=_BORDER, height=1).pack(fill=tk.X, padx=6, pady=4)
    tk.Label(frm, text="Arap Harfleri",
             bg=_PANEL, fg=_FG2, font=_FSB).pack(anchor=tk.W, padx=6, pady=(0,2))

    # Arap harfleri — 8 sütunlu grid
    ar_f = tk.Frame(frm, bg=_PANEL)
    ar_f.pack(fill=tk.X, padx=6, pady=2)
    for i, ch in enumerate(_ARAP_HARFLERI):
        tk.Button(ar_f, text=ch, width=3, height=1,
                  font=("Segoe UI", 13),
                  bg="#eaecf4", fg="#5a4030",
                  activebackground=_ACC1, activeforeground="white",
                  relief=tk.FLAT, bd=0,
                  command=lambda c=ch: _insert_to_focused(widget_root, c)
                  ).grid(row=i // 8, column=i % 8, padx=2, pady=1, sticky=tk.EW)

    return frm


# ── Widget yardımcıları ───────────────────────────────────────────────────

def _lbl(p, text, font=None, fg=None, bg=None, **kw):
    return tk.Label(p, text=text, font=font or _F,
                    fg=fg or _FG, bg=bg or _BG, **kw)

def _entry(p, var, width=32, show="", **kw):
    return tk.Entry(p, textvariable=var, width=width, show=show,
                    font=_F, bg="#ffffff", fg=_FG,
                    insertbackground=_FG, relief=tk.FLAT,
                    highlightbackground=_BORDER, highlightthickness=1, **kw)

def _combo(p, var, values, width=24):
    cb = ttk.Combobox(p, textvariable=var, values=values,
                      width=width, state="readonly", font=_F)
    return cb

def _spin(p, var, lo=1, hi=999, width=6):
    return tk.Spinbox(p, textvariable=var, from_=lo, to=hi, width=width,
                      font=_F, bg="#ffffff", fg=_FG,
                      buttonbackground=_BORDER, relief=tk.FLAT,
                      highlightbackground=_BORDER, highlightthickness=1)

def _btn(p, text, cmd, style="primary", **kw):
    colors = {
        "primary": (_ACC1, "white"),
        "danger":  (_ACC2, "white"),
        "ghost":   (_BORDER, _FG),
        "success": (_GREEN, "white"),
    }
    bg, fg = colors.get(style, (_ACC1, "white"))
    b = tk.Button(p, text=text, command=cmd, font=_FB,
                  bg=bg, fg=fg, relief=tk.FLAT, bd=0,
                  padx=14, pady=7, cursor="hand2",
                  activebackground=_ACC2 if style=="danger" else "#1a5fcc",
                  activeforeground="white", **kw)
    return b

def _section(p, title, icon="▸"):
    """Bölüm başlığı — sol vurgu çizgili güçlü şerit."""
    f = tk.Frame(p, bg=_PANEL)
    # Sol 4 px mavi accent çizgisi
    tk.Frame(f, bg=_ACC1, width=4).pack(side=tk.LEFT, fill=tk.Y)
    tk.Label(f, text=f"  {icon}  {title}", bg=_PANEL, fg=_FG,
             font=("Segoe UI", 10, "bold"), pady=7, padx=4).pack(side=tk.LEFT)
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

class ManuscriptWizard(tk.Frame):
    STEPS = [
        ("📄", "Kaynak"),
        ("📐", "Varak"),
        ("✒", "İmla"),
        ("📑", "Yapı"),
        ("🔤", "Paleografi"),
        ("✅", "Özet"),
        ("📊", "Sonuç"),
    ]
    # 6. adım (Sonuç) sadece öğrenme tamamlandıktan sonra aktif
    _SONUC_STEP = 6

    def __init__(self, parent, on_close=None, config_only: bool = False):
        """Gömülebilir wizard Frame'i.

        Parameters
        ----------
        parent      : Üst widget (Frame veya Toplevel).
        on_close    : 'İptal' veya 'Kapat' düğmesine tıklanınca çağrılır.
        config_only : True ise öğrenme modu devre dışı — sadece meta/ayar
                      yapılandırması için açılır (OCR panelinden tetiklenir).
                      Transkripsiyon kaynağı zorunlu olmaz.
        """
        super().__init__(parent, bg=_BG)
        self._on_close_cb = on_close
        self._config_only = config_only   # sadece ayar, öğrenme yok
        self._step = 0
        self._init_vars()
        self._build_shell()
        self._show_step(0)

    def _on_close(self):
        # Fare tekerleği binding'ini temizle
        try:
            self.unbind_all("<MouseWheel>")
        except Exception:
            pass
        if self._on_close_cb:
            self._on_close_cb()
        # Embedded modda kendinizi yok etme — üst pencere yönetir

    def _apply_and_switch(self):
        """Mevcut wizard ayarlarını OCR paneline aktar, OCR moduna geç."""
        import dataclasses
        try:
            meta = self._build_meta()
            meta_dict = (dataclasses.asdict(meta)
                         if dataclasses.is_dataclass(meta) else {})
        except Exception:
            meta_dict = {}
        if self.on_learning_done:
            try:
                self.on_learning_done(meta_dict)
            except Exception:
                pass
        self._on_close()

    # ── Değişkenler ──────────────────────────────────────────────────────

    def _init_vars(self):
        # Adım 1
        self.ms_path_var    = tk.StringVar()
        self.trans_path_var = tk.StringVar()
        self.eser_adi_var   = tk.StringVar()
        # Auto-fill: önceki eser girişlerini hatırla
        self._autofill_timer: str | None = None
        self._autofill_done_for: str = ""
        self._autofill_in_progress: bool = False
        self.eser_adi_var.trace_add("write", self._autofill_debounce)
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
        self.imla_skala_vars: dict[str, tk.IntVar] = {}
        for grp_items in IMLA_OZELLIKLERI.values():
            for item in grp_items:
                self.imla_vars[item]       = tk.BooleanVar(value=False)
                self.imla_skala_vars[item] = tk.IntVar(value=50)
        self.imla_serbest_var    = tk.StringVar()
        self.aktarim_ilk_var     = tk.StringVar()

        # Adım 4 — Metin yapısı
        self._bolum_rows: list[dict] = []   # dinamik satırlar

        # Adım 1 ek — İçerik & Transkripsiyon
        self.icerik_vars: dict[str, tk.BooleanVar] = {
            t: tk.BooleanVar(value=False) for t in ICERIK_TURLERI
        }
        self.mensur_manzum_var = tk.StringVar(value="Mensur")
        self._trans_rows: list[dict] = []   # [{isaret, arap_harfi, karsilik, dosyalar}]

        # Adım 2 ek — Varak/sayfa dönüşümü
        self.varak_baslangic_var = tk.StringVar()   # örn. "85b"
        self.varak_bitis_var     = tk.StringVar()   # örn. "212a"

        # Adım 4 ek — Ana metin sayfaları
        self.metin_bas_var = tk.IntVar(value=0)
        self.metin_bit_var = tk.IntVar(value=0)

        # Adım 5 ek — Kelime yoğunluğu
        self.arapca_yogun_var = tk.IntVar(value=30)
        self.farsca_yogun_var = tk.IntVar(value=20)
        self.turkce_yogun_var = tk.IntVar(value=50)

        # Adım 5 — Paleografi + alan
        self.alan_var       = tk.StringVar(value="Osmanlıca")
        self.donem_var      = tk.StringVar(value="Belirsiz")
        self.yazi_var       = tk.StringVar(value="Nesih")
        self.hareke_var     = tk.StringVar(value="Harekesiz")
        # Dil kodu açıklamalı etiket olarak saklanır, _build_meta'da koda çevrilir
        self.dil_var        = tk.StringVar(
            value="Osmanlıca  —  Arap harfli Türkçe")
        self.guven_var      = tk.DoubleVar(value=0.9)
        self.ozel_not_var   = tk.StringVar()
        self._harf_rows: list[dict] = []

        # Sonuç adımı
        self._last_entry_id: str = ""
        self._learning_done: bool = False
        # Öğrenme tamamlanınca çağrılacak hook (meta: dict)
        self.on_learning_done: "Callable[[dict], None] | None" = None

        # Transkripsiyon varak/satır aralığı
        self.trans_varak_bas_var = tk.StringVar()   # örn. "25b/7"
        self.trans_varak_bit_var = tk.StringVar()   # örn. "48a/12"

        # Adım 7 — Öğrenme testi
        self._test_word_var = tk.StringVar()
        self._test_all_var  = tk.BooleanVar(value=False)

        # PDF / Sayfa formatı
        self.pdf_format_var  = tk.StringVar(value="tek")       # "tek" / "cift"
        self.sayfa_yonu_var  = tk.StringVar(value="dikey")     # "dikey" / "yatay"
        self.beyit_duzen_var = tk.StringVar(value="yan_yana")  # yan_yana/girintili/hizali

        # Okunabilirlik / Tahribat durumu
        self.ilk_varak_durum_var = tk.StringVar(value="Tam okunabilir")
        self.son_varak_durum_var = tk.StringVar(value="Tam okunabilir")
        self.ic_sayfa_durum_var  = tk.StringVar(value="Tam okunabilir")

    # ── Kabuk ────────────────────────────────────────────────────────────

    def _build_shell(self):
        # Başlık
        top = tk.Frame(self, bg=_PANEL, height=52)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="  ✍  El Yazması Öğretme Sihirbazı",
                 bg=_PANEL, fg=_FG, font=_FT).pack(side=tk.LEFT, padx=16, pady=12)

        # Adım çubuğu
        self._bar = tk.Frame(self, bg=_PANEL, height=48)
        self._bar.pack(fill=tk.X)
        self._bar.pack_propagate(False)
        self._step_btns: list[tk.Label] = []
        for i, (icon, name) in enumerate(self.STEPS):
            f = tk.Frame(self._bar, bg=_PANEL)
            f.pack(side=tk.LEFT, expand=True, fill=tk.X)
            lbl = tk.Label(f, text=f"{icon} {i+1}. {name}",
                           bg=_PANEL, fg=_FG2, font=_FS, pady=14,
                           cursor="hand2")
            lbl.pack()
            lbl.bind("<Button-1>", lambda e, s=i: self._nav_to_step(s))
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
        self._btn_cancel = _btn(nav, "İptal", self._on_close, "ghost")
        self._btn_cancel.pack(side=tk.RIGHT, padx=16, pady=10)
        self._btn_apply_ocr = _btn(nav, "✓  Seçili Ayarları OCR için Kullan",
                                    self._apply_and_switch, "success")
        self._btn_apply_ocr.pack(side=tk.RIGHT, padx=(0, 8), pady=10)
        self._btn_next = _btn(nav, "İleri  ▶", self._go_next, "primary")
        self._btn_next.pack(side=tk.RIGHT, padx=(0,8), pady=10)

    def _update_bar(self):
        for i, lbl in enumerate(self._step_btns):
            if i == self._SONUC_STEP and not self._learning_done:
                lbl.configure(fg=_FG3, bg=_PANEL)   # gri — henüz erişilemiyor
            elif i < self._step:
                lbl.configure(fg=_GREEN, bg=_PANEL)
            elif i == self._step:
                lbl.configure(fg="white", bg=_ACC1)
            else:
                lbl.configure(fg=_FG2, bg=_PANEL)

        # Geri butonu
        back_ok = self._step > 0 and self._step != self._SONUC_STEP
        self._btn_back.configure(state=tk.NORMAL if back_ok else tk.DISABLED)

        # İleri / Başlat / Kapat — KOMUT HER ZAMAN _go_next olmalı
        OZET = self._SONUC_STEP - 1   # = 5
        if self._step == OZET:
            self._btn_next.configure(text="✓  Öğrenmeyi Başlat",
                                     bg=_GREEN, state=tk.NORMAL,
                                     command=self._go_next)
        elif self._step == self._SONUC_STEP:
            self._btn_next.configure(text="✓  Kapat",
                                     bg=_GREEN, state=tk.NORMAL,
                                     command=self._go_next)
        else:
            self._btn_next.configure(text="İleri  ▶",
                                     bg=_ACC1, state=tk.NORMAL,
                                     command=self._go_next)

    def _show_step(self, n):
        for w in self._area.winfo_children():
            w.destroy()
        self._step = n
        self._update_bar()
        [self._s1, self._s2, self._s3, self._s4,
         self._s5, self._s6, self._s7][n]()
        # Canvas'ın gerçek boyutunu alıp iç frame'i genişletmesi için
        self._area.update_idletasks()

    def _go_next(self):
        OZET = self._SONUC_STEP - 1   # = 5
        if self._step == self._SONUC_STEP:
            self._on_close()   # gömülü modda callback'i çağırır
            return
        if self._step == OZET:
            if self._validate():
                self._start()
            return
        if not self._validate():
            return
        # Sonuç adımını atla (sadece _on_done ile girilir)
        nxt = self._step + 1
        if nxt == self._SONUC_STEP:
            nxt = OZET   # Özet'ten önce atlamayı engelle — zaten OZET'teyiz
            return
        self._show_step(nxt)

    def _go_back(self):
        if self._step == self._SONUC_STEP:
            self._show_step(self._SONUC_STEP - 1)
            return
        if self._step > 0:
            self._show_step(self._step - 1)

    def _nav_to_step(self, n: int):
        """Adım başlığına tıklanınca doğrudan o adıma git."""
        # Sonuç adımı sadece öğrenme tamamlanınca erişilebilir
        if n == self._SONUC_STEP and not self._learning_done:
            return
        # Öğrenme devam ediyorken (Özet adımındayken) navigasyonu kilitle
        if self._step == self._SONUC_STEP - 1 and hasattr(self, "_stop_event"):
            return
        self._show_step(n)

    def _validate(self) -> bool:
        if self._step == 0:
            if not self.ms_path_var.get():
                messagebox.showwarning("Eksik", "El yazması PDF seçin.", parent=self.winfo_toplevel())
                return False
            # config_only modunda (OCR ayarı) transkripsiyon kaynağı zorunlu değil
            if not self._config_only and not self.trans_path_var.get():
                messagebox.showwarning("Eksik", "Transkripsiyon kaynağı seçin.", parent=self.winfo_toplevel())
                return False
        if self._step == 1:
            if self.ms_start_var.get() >= self.ms_end_var.get():
                messagebox.showwarning("Hata",
                    "Başlangıç sayfası bitiş sayfasından küçük olmalı.", parent=self.winfo_toplevel())
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

        # Transkripsiyon kaynağı — kütüphaneden seç
        lib_f = tk.Frame(c1, bg=_CARD)
        lib_f.pack(anchor=tk.W, padx=14, pady=(0, 4))
        _lbl(lib_f, "ya da:", bg=_CARD, fg=_FG3, font=_FS).pack(side=tk.LEFT, padx=(0, 8))
        _btn(lib_f, "📚  Kütüphaneden Seç",
             self._browse_library_trans, "ghost").pack(side=tk.LEFT, padx=(0, 6))
        _lbl(lib_f, "(önceden öğrenilmiş bir eserin transkripsiyonunu kullan)",
             bg=_CARD, fg=_FG3, font=_FS).pack(side=tk.LEFT)

        # Kaynak türü
        kt_fr = tk.Frame(c1, bg=_CARD)
        kt_fr.pack(anchor=tk.W, padx=14, pady=(4, 6))
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
                           selectcolor="#ffffff",
                           activebackground=_CARD).pack(side=tk.LEFT, padx=6)

        # ─ PDF / Sayfa Formatı ─────────────────────────────────────
        cf = _card(scroll, padx=0, pady=0)
        cf.pack(fill=tk.X, padx=16, pady=6)
        _section(cf, "PDF Sayfa Formatı", "📐").pack(fill=tk.X)

        pf = tk.Frame(cf, bg=_CARD)
        pf.pack(fill=tk.X, padx=14, pady=(8, 4))

        # Tek / çift sayfa
        pdf_row = tk.Frame(pf, bg=_CARD)
        pdf_row.pack(anchor=tk.W, pady=(0, 4))
        _lbl(pdf_row, "PDF düzeni:", bg=_CARD, fg=_FG2, font=_FSB).pack(side=tk.LEFT, padx=(0, 10))
        for val, txt in [
            ("tek",  "Tek sayfa (standart)"),
            ("cift", "Çift sayfa — yatay (kütüphane taraması)"),
        ]:
            tk.Radiobutton(pdf_row, text=txt, variable=self.pdf_format_var,
                           value=val, bg=_CARD, fg=_FG, font=_FS,
                           selectcolor="#ffffff", activebackground=_CARD,
                           command=self._toggle_cift_sayfa).pack(side=tk.LEFT, padx=(0, 14))

        # Çift sayfa açıklama paneli (başlangıçta gizli)
        self._cift_info_lbl = tk.Label(pf,
            text="ℹ  Sağ sayfa = b (verso), Sol sayfa = a (recto)\n"
                 "   Örnek açılış: Sağ=83b · Sol=84a  →  Sağ=84b · Sol=85a\n"
                 "   Program her PDF sayfasını ortadan ikiye bölerek işler.",
            bg="#dde8f8", fg="#1a5a9a", font=_FS,
            justify=tk.LEFT, padx=10, pady=6, anchor=tk.W)
        # Başlangıç görünürlüğünü ayarla
        self._toggle_cift_sayfa()

        # Sayfa yönü + sembolik ikonlar
        yon_row = tk.Frame(pf, bg=_CARD)
        yon_row.pack(anchor=tk.W, pady=(6, 4))
        _lbl(yon_row, "Sayfa yönü:", bg=_CARD, fg=_FG2, font=_FSB).pack(side=tk.LEFT, padx=(0, 10))
        for val, txt in [("dikey", "Dikey (portre)"), ("yatay", "Yatay (peyzaj)")]:
            tk.Radiobutton(yon_row, text=txt, variable=self.sayfa_yonu_var,
                           value=val, bg=_CARD, fg=_FG, font=_FS,
                           selectcolor="#ffffff",
                           activebackground=_CARD).pack(side=tk.LEFT, padx=(0, 14))

        # Sembolik sayfa format ikonları
        icon_row = tk.Frame(pf, bg=_CARD)
        icon_row.pack(anchor=tk.W, pady=(2, 6))
        _sayfa_ikon(icon_row, "tek_dikey",  "Tek · Dikey")
        _sayfa_ikon(icon_row, "tek_yatay",  "Tek · Yatay")
        _sayfa_ikon(icon_row, "cift_yatay", "Çift · Yatay (sağ=b, sol=a)")

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

        # ─ İçerik Türü ─
        c3 = _card(scroll, padx=0, pady=0)
        c3.pack(fill=tk.X, padx=16, pady=6)
        _section(c3, "İçerik Türü", "📚").pack(fill=tk.X)

        ic_body = tk.Frame(c3, bg=_CARD)
        ic_body.pack(fill=tk.X, padx=14, pady=8)
        for i, tur in enumerate(ICERIK_TURLERI):
            var = self.icerik_vars[tur]
            tk.Checkbutton(ic_body, text=tur, variable=var,
                           bg=_CARD, fg=_FG, font=_FS,
                           selectcolor="#ffffff",
                           activebackground=_CARD).grid(
                row=i // 3, column=i % 3,
                sticky=tk.W, padx=6, pady=2)

        mm_f = tk.Frame(c3, bg=_CARD)
        mm_f.pack(anchor=tk.W, padx=14, pady=(0, 6))
        _lbl(mm_f, "Üslup:", bg=_CARD, fg=_FG2, font=_FSB).pack(
            side=tk.LEFT, padx=(0, 10))
        for val in ("Mensur", "Manzum", "Karışık (mensur + manzum)"):
            tk.Radiobutton(mm_f, text=val, variable=self.mensur_manzum_var,
                           value=val, bg=_CARD, fg=_FG, font=_FS,
                           selectcolor="#ffffff", activebackground=_CARD,
                           command=self._toggle_beyit).pack(side=tk.LEFT, padx=6)

        # Beyit / mısra satır düzeni (manzum seçilince görünür)
        self._beyit_frame = tk.Frame(c3, bg=_CARD)
        bf2 = tk.Frame(self._beyit_frame, bg=_CARD)
        bf2.pack(anchor=tk.W, padx=14, pady=(0, 8))
        _lbl(bf2, "Beyit/mısra düzeni:", bg=_CARD, fg=_FG2, font=_FSB).pack(side=tk.LEFT, padx=(0, 10))
        for val, txt in [
            ("yan_yana",  "Yan yana (sütun — 1. ve 2. mısra aynı satırda)"),
            ("girintili", "Alt alta, girintili (2. mısra içeriden)"),
            ("hizali",    "Alt alta, hizalı (2. mısra bir alt satırda)"),
        ]:
            tk.Radiobutton(bf2, text=txt, variable=self.beyit_duzen_var,
                           value=val, bg=_CARD, fg=_FG, font=_FS,
                           selectcolor="#ffffff",
                           activebackground=_CARD).pack(anchor=tk.W, padx=(16, 0), pady=1)

        # Sembolik beyit ikonları
        bi_row = tk.Frame(self._beyit_frame, bg=_CARD)
        bi_row.pack(anchor=tk.W, padx=14, pady=(0, 8))
        _beyit_ikon(bi_row, "yan_yana",  "Yan yana")
        _beyit_ikon(bi_row, "girintili", "Girintili")
        _beyit_ikon(bi_row, "hizali",    "Hizalı")

        self._toggle_beyit()

        # ─ Transkripsiyon İşaretleri ─
        c4 = _card(scroll, padx=0, pady=0)
        c4.pack(fill=tk.X, padx=16, pady=6)
        _section(c4, "Transkripsiyon İşaretleri ve Karşılıkları", "⇌").pack(fill=tk.X)

        ti_info = tk.Label(c4,
            text="Kaynakta kullanılan özel transkripsiyon işaretlerini buraya girin\n"
                 "(örn.  ā = uzun a   |   ḥ = h ile h arası ses   |   ' = hemze)",
            bg=_CARD, fg=_FG2, font=_FS, justify=tk.LEFT, padx=14, pady=4)
        ti_info.pack(anchor=tk.W)

        # Sütun başlıkları
        ti_hdr = tk.Frame(c4, bg=_CARD)
        ti_hdr.pack(fill=tk.X, padx=14, pady=(0, 2))
        for txt, w in [("Latin", 8), ("Arap Harfi", 7), ("Karşılığı / Açıklama", 34), ("📎", 3)]:
            tk.Label(ti_hdr, text=txt, bg=_CARD, fg=_FG3,
                     font=_FSB, width=w, anchor=tk.W).pack(side=tk.LEFT, padx=2)

        self._trans_frame = tk.Frame(c4, bg=_CARD)
        self._trans_frame.pack(fill=tk.X, padx=14, pady=2)

        for row in self._trans_rows:   # önceki adımlardan dönerken yeniden çiz
            self._render_trans_row(row)

        btn_ti = tk.Frame(c4, bg=_CARD)
        btn_ti.pack(anchor=tk.W, padx=14, pady=(4, 10))
        _btn(btn_ti, "➕  İşaret Ekle",
             self._add_trans_row, "ghost").pack(side=tk.LEFT, padx=(0, 8))
        # Yaygın işaretler hızlı ekle
        for ish in ["ā", "ū", "ī", "ḥ", "ḫ", "ġ", "ṭ", "ẓ", "ʿ", "ʾ"]:
            tk.Button(btn_ti, text=ish,
                      command=lambda s=ish: self._add_trans_row(s),
                      font=("Segoe UI", 10), bg="#dde5f5", fg=_FG,
                      relief=tk.FLAT, bd=0, padx=6, pady=3,
                      cursor="hand2").pack(side=tk.LEFT, padx=1)

        # ─ İpucu ─
        tip = tk.Frame(scroll, bg="#e8f5eb")
        tip.pack(fill=tk.X, padx=16, pady=(4, 14))
        tk.Label(tip,
                 text="💡  El yazması: PDF, TIFF veya görüntü dosyası (JPG/PNG/BMP/WebP).\n"
                      "Transkripsiyon: eserin matbu/dijital baskısı, tez transkripsiyonu, "
                      "Word belgesi veya düz metin.\n"
                      "Program bu çiftlerden öğrenerek benzer yazmaları daha isabetli okur.",
                 bg="#e8f5eb", fg=_GREEN, font=_FS,
                 wraplength=660, justify=tk.LEFT, pady=8, padx=12).pack()

    def _add_trans_row(self, isaret=""):
        row = {
            "isaret":     tk.StringVar(value=isaret),
            "arap_harfi": tk.StringVar(),   # Arap alfabesiyle gösterim
            "karsilik":   tk.StringVar(),
            "dosyalar":   [],               # ek dosya yolları
        }
        self._trans_rows.append(row)
        self._render_trans_row(row)

    def _render_trans_row(self, row):
        if "dosyalar" not in row:
            row["dosyalar"] = []
        f = tk.Frame(self._trans_frame, bg=_CARD)
        f.pack(fill=tk.X, pady=1)
        row["_frame"] = f
        _entry(f, row["isaret"],     width=8).pack(side=tk.LEFT, padx=2)
        # Arap harfli gösterim (RTL destekli giriş)
        e_ar = tk.Entry(f, textvariable=row["arap_harfi"], width=7,
                        font=("Arial Unicode MS", 11),
                        bg="#ffffff", fg=_FG, insertbackground=_FG,
                        relief=tk.FLAT,
                        highlightbackground=_BORDER, highlightthickness=1)
        e_ar.pack(side=tk.LEFT, padx=2)
        _entry(f, row["karsilik"],   width=34).pack(side=tk.LEFT, padx=2)
        # Dosya ekleme butonu
        row["_dosya_lbl"] = tk.Label(
            f, text=f"📎{len(row['dosyalar'])}" if row["dosyalar"] else "📎",
            bg=_CARD, fg=_FG2, font=_FS, cursor="hand2")
        row["_dosya_lbl"].pack(side=tk.LEFT, padx=2)
        row["_dosya_lbl"].bind("<Button-1>",
                                lambda e, r=row: self._show_trans_dosyalar(r))
        _btn(f, "✖", lambda fr=f, r=row: self._del_trans_row(fr, r),
             "danger").pack(side=tk.LEFT, padx=2)

    def _show_trans_dosyalar(self, row: dict):
        """Transkripsiyon işareti için dosya ekle diyalogu."""
        dlg = tk.Toplevel(self)
        dlg.title("İşaret Dosyaları")
        dlg.configure(bg=_BG)
        dlg.geometry("480x360")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()

        _lbl(dlg, "Bu işaret için Word / PDF / Excel / Görüntü ekleyin:",
             fg=_FG2, font=_FS).pack(anchor=tk.W, padx=14, pady=(10,4))

        lf = tk.Frame(dlg, bg=_BG)
        lf.pack(fill=tk.BOTH, expand=True, padx=14, pady=4)

        def refresh():
            for w in lf.winfo_children(): w.destroy()
            if not row["dosyalar"]:
                _lbl(lf, "Henüz dosya eklenmedi.", fg=_FG3, font=_FS).pack(
                    anchor=tk.W, pady=8)
                return
            for path in row["dosyalar"]:
                rf = tk.Frame(lf, bg=_CARD)
                rf.pack(fill=tk.X, pady=2)
                _lbl(rf, Path(path).name[:54], fg=_FG, bg=_CARD, font=_FS).pack(
                    side=tk.LEFT, padx=6)
                _btn(rf, "✖",
                     lambda p=path: (row["dosyalar"].remove(p), refresh()),
                     "danger").pack(side=tk.RIGHT, padx=4)
            if "_dosya_lbl" in row:
                row["_dosya_lbl"].configure(
                    text=f"📎{len(row['dosyalar'])}", fg=_ACC1)

        def add_file():
            ft = [("Desteklenen","*.pdf *.docx *.doc *.xlsx *.xls *.jpg *.jpeg *.png *.bmp"),
                  ("Tüm","*.*")]
            p = filedialog.askopenfilename(filetypes=ft, parent=dlg)
            if p:
                row["dosyalar"].append(p)
                refresh()

        refresh()
        bf = tk.Frame(dlg, bg=_BG)
        bf.pack(fill=tk.X, padx=14, pady=(4,12))
        _btn(bf, "➕  Dosya / Görüntü Ekle", add_file, "primary").pack(side=tk.LEFT)
        _btn(bf, "✓  Tamam", dlg.destroy, "success").pack(side=tk.RIGHT)

    def _del_trans_row(self, frame, row):
        frame.destroy()
        if row in self._trans_rows:
            self._trans_rows.remove(row)

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

        # ─ Sayfa/Varak açıklama ─
        info_v = tk.Frame(scroll, bg="#dde8f8")
        info_v.pack(fill=tk.X, padx=16, pady=(14, 4))
        tk.Label(info_v,
                 text="ℹ  Sayfa numaraları: PDF/Word'deki sıra numarasıdır (1, 2, 3 …).\n"
                      "Varak numarası: yazmanın kendi numaralaması (85b, 86a …).\n"
                      "Bazı çalışmalar bir yazmanın belirli varaklarını kapsar; "
                      "bu durumda altındaki 'İlk varak' alanını doldurun.",
                 bg="#dde8f8", fg="#1a5a9a", font=_FS,
                 justify=tk.LEFT, padx=12, pady=6).pack(fill=tk.X)

        # Sayfa aralıkları
        c1 = _card(scroll, padx=0, pady=0)
        c1.pack(fill=tk.X, padx=16, pady=(4, 6))
        _section(c1, "İşlenecek Sayfa Aralıkları (PDF / Word Sayfa No)", "📐").pack(fill=tk.X)

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

        _pg_grp(pr, "El Yazması PDF Sayfası", self.ms_start_var, self.ms_end_var, 0)

        sync_f = tk.Frame(pr, bg=_CARD)
        sync_f.grid(row=0, column=1, padx=12, sticky=tk.N, pady=4)
        tk.Checkbutton(sync_f, text="Sayfa numaraları\naynı",
                       variable=self.sync_var, command=self._toggle_sync,
                       bg=_CARD, fg=_FG, font=_FS,
                       selectcolor="#ffffff",
                       activebackground=_CARD).pack()

        self._tr_grp_frame = tk.Frame(pr, bg=_CARD)
        self._tr_grp_frame.grid(row=0, column=2, sticky=tk.W)
        _pg_grp(self._tr_grp_frame, "Transkripsiyon Sayfası (PDF/Word)",
                self.tr_start_var, self.tr_end_var, 0)
        self._toggle_sync()

        # ─ Varak numaraları ─
        cv = _card(scroll, padx=0, pady=0)
        cv.pack(fill=tk.X, padx=16, pady=(4, 6))
        _section(cv, "Yazma Varak Numaraları (opsiyonel)", "📜").pack(fill=tk.X)
        vf = tk.Frame(cv, bg=_CARD)
        vf.pack(fill=tk.X, padx=14, pady=10)
        _lbl(vf, "İlk PDF sayfası = Varak:", bg=_CARD, fg=_FG2, font=_FSB).pack(
            side=tk.LEFT, padx=(0,6))
        _entry(vf, self.varak_baslangic_var, width=8).pack(side=tk.LEFT)
        _lbl(vf, " (örn. 85b)", bg=_CARD, fg=_FG3, font=_FS).pack(side=tk.LEFT, padx=(2,16))
        _lbl(vf, "Son PDF sayfası = Varak:", bg=_CARD, fg=_FG2, font=_FSB).pack(
            side=tk.LEFT, padx=(0,6))
        _entry(vf, self.varak_bitis_var, width=8).pack(side=tk.LEFT)
        _lbl(vf, " (örn. 212a)", bg=_CARD, fg=_FG3, font=_FS).pack(side=tk.LEFT, padx=2)

        # Toplam varak
        tv_f = tk.Frame(cv, bg=_CARD)
        tv_f.pack(anchor=tk.W, padx=14, pady=(0, 10))
        _lbl(tv_f, "Toplam varak sayısı:",
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
                       selectcolor="#ffffff",
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

        # ─ Transkripsiyon Kapsam Aralığı ─
        ctr = _card(scroll, padx=0, pady=0)
        ctr.pack(fill=tk.X, padx=16, pady=(4, 4))
        _section(ctr, "Transkripsiyon Kapsam Aralığı (Varak / Satır)", "📌").pack(fill=tk.X)

        tk.Label(ctr,
                 text="Bazı çalışmalar yazmanın sadece belirli varaklarını kapsar.\n"
                      "Transkripsiyonun başladığı ve bittiği varak/satır numarasını "
                      "belirtin (örn. 25b/7 – 48a/12).\n"
                      "Bu bilgi yazma görseli ile metin eşleştirmesini doğru yapar.",
                 bg=_CARD, fg=_FG2, font=_FS,
                 justify=tk.LEFT, padx=14, pady=4, anchor=tk.W).pack(fill=tk.X)

        vr_row = tk.Frame(ctr, bg=_CARD)
        vr_row.pack(anchor=tk.W, padx=14, pady=(0, 10))
        _lbl(vr_row, "Başlangıç (varak/satır):", bg=_CARD, fg=_FG2, font=_FSB).pack(side=tk.LEFT, padx=(0,6))
        _entry(vr_row, self.trans_varak_bas_var, width=10).pack(side=tk.LEFT)
        tk.Label(vr_row, text=" — ", bg=_CARD, fg=_FG2, font=_F).pack(side=tk.LEFT, padx=4)
        _lbl(vr_row, "Bitiş (varak/satır):", bg=_CARD, fg=_FG2, font=_FSB).pack(side=tk.LEFT, padx=(0,6))
        _entry(vr_row, self.trans_varak_bit_var, width=10).pack(side=tk.LEFT)
        tk.Label(vr_row, text=" örn: 25b/7 — 48a/12",
                 bg=_CARD, fg=_FG3, font=_FS).pack(side=tk.LEFT, padx=8)

        # ─ Okunabilirlik / Tahribat Durumu ─
        cd = _card(scroll, padx=0, pady=0)
        cd.pack(fill=tk.X, padx=16, pady=(6, 14))
        _section(cd, "Okunabilirlik / Tahribat Durumu", "🔍").pack(fill=tk.X)

        tk.Label(cd,
                 text="Sayfaların okunabilirlik durumunu belirtin — OCR güven eşiğini ayarlamada kullanılır.",
                 bg=_CARD, fg=_FG2, font=_FS, padx=14, pady=4, anchor=tk.W).pack(fill=tk.X)

        _DURUMLAR = ["Tam okunabilir", "Kısmen okunabilir",
                     "Tahribatlı (silinme, leke, yırtık)", "Ağır tahribat / eksik yaprak"]
        df = tk.Frame(cd, bg=_CARD)
        df.pack(fill=tk.X, padx=14, pady=(0, 12))
        df.columnconfigure(1, weight=1)

        def _durum_row(r, label, var):
            _lbl(df, label, bg=_CARD, fg=_FG2, font=_FSB).grid(
                row=r, column=0, sticky=tk.W, padx=(0, 12), pady=4)
            _combo(df, var, _DURUMLAR, width=36).grid(
                row=r, column=1, sticky=tk.W, pady=4)

        _durum_row(0, "İlk varak / kapak:",      self.ilk_varak_durum_var)
        _durum_row(1, "Son varak / bitiş:",       self.son_varak_durum_var)
        _durum_row(2, "İç sayfalar (genel):",     self.ic_sayfa_durum_var)

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

    def _toggle_cift_sayfa(self):
        """Çift sayfa PDF seçilince açıklama etiketini göster/gizle."""
        try:
            if self.pdf_format_var.get() == "cift":
                self._cift_info_lbl.pack(fill=tk.X, padx=14, pady=(0, 6))
            else:
                self._cift_info_lbl.pack_forget()
        except Exception:
            pass

    def _toggle_beyit(self):
        """Manzum seçilince beyit düzeni seçeneğini göster/gizle."""
        try:
            if self.mensur_manzum_var.get() in ("Manzum", "Karışık (mensur + manzum)"):
                self._beyit_frame.pack(fill=tk.X)
            else:
                self._beyit_frame.pack_forget()
        except Exception:
            pass

    def _browse_library_trans(self):
        """Kütüphaneden bir eser seçip transkripsiyonunu kaynak olarak kullan."""
        lib     = get_library()
        entries = lib.list_entries()
        if not entries:
            messagebox.showinfo("Boş Kütüphane",
                "Kütüphanede henüz öğrenilmiş eser yok.\n"
                "Önce bir eser öğretin.", parent=self.winfo_toplevel())
            return

        dlg = tk.Toplevel(self)
        dlg.title("Kütüphaneden Transkripsiyon Seç")
        dlg.configure(bg=_BG)
        dlg.geometry("640x440")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()

        tk.Label(dlg,
                 text="  Transkripsiyon kaynağı olarak kullanılacak eseri seçin.\n"
                      "  Seçilen eserin öğrenilmiş sayfa metinleri geçici dosyaya aktarılır.",
                 bg=_PANEL, fg=_FG2, font=_FS, justify=tk.LEFT,
                 pady=6).pack(fill=tk.X)

        lf = tk.Frame(dlg, bg=_BG)
        lf.pack(fill=tk.BOTH, expand=True, padx=14, pady=6)

        sb2 = ttk.Scrollbar(lf)
        lb = tk.Listbox(lf, yscrollcommand=sb2.set,
                        bg="#f0f2fa", fg=_FG, font=_F,
                        selectbackground=_ACC1, activestyle="none",
                        height=14)
        sb2.configure(command=lb.yview)
        sb2.pack(side=tk.RIGHT, fill=tk.Y)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for e in entries:
            m     = e.get("meta", {})
            pages = len(e.get("pages", []))
            lb.insert(tk.END,
                f"  {e.get('eser_adi','?'):<40}"
                f"  {m.get('alan','?'):<18}"
                f"  {m.get('donem','?'):<14}"
                f"  {pages} sayfa")

        def _confirm():
            sel = lb.curselection()
            if not sel:
                messagebox.showwarning("Seçim Yok", "Bir eser seçin.", parent=dlg)
                return
            entry = entries[sel[0]]

            # Tüm sayfa metinlerini birleştirip geçici .txt'ye yaz
            from metin_atolyesi.core.manuscript_library import _lib_dir as _ld, _load_sample_text as _lst
            texts = []
            for pg in entry.get("pages", []):
                t = _lst(pg["hash"])
                if t:
                    texts.append(f"=== Sayfa {pg['ms_page']+1} ===\n{t}")

            if not texts:
                messagebox.showwarning("Boş",
                    "Bu eserin kaydedilmiş metin verisi yok.", parent=dlg)
                return

            tmp_dir  = Path.home() / ".metin_atolyesi"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = tmp_dir / f"lib_trans_{entry.get('id','')[:8]}.txt"
            tmp_path.write_text("\n\n".join(texts), encoding="utf-8")

            self.trans_path_var.set(str(tmp_path))
            # Eser bilgilerini de doldur
            self._do_autofill(entry)
            dlg.destroy()
            messagebox.showinfo("Hazır",
                f"'{entry.get('eser_adi')}' transkripsiyonu kaynak olarak ayarlandı.\n"
                f"({len(texts)} sayfa — {tmp_path.name})",
                parent=self.winfo_toplevel())

        bf3 = tk.Frame(dlg, bg=_BG)
        bf3.pack(fill=tk.X, padx=14, pady=(4, 12))
        _btn(bf3, "✓  Seç ve Kullan", _confirm,    "primary").pack(side=tk.LEFT)
        _btn(bf3, "İptal",             dlg.destroy, "ghost").pack(side=tk.RIGHT)

    # ════════════════════════════════════════════════════════════════
    #  ADIM 3 — İmla Hususiyetleri
    # ════════════════════════════════════════════════════════════════

    def _s3(self):
        _, scroll = _scrolled_frame(self._area)

        for grp_name, items in IMLA_OZELLIKLERI.items():
            c = _card(scroll, padx=0, pady=0)
            c.pack(fill=tk.X, padx=16, pady=4)
            _section(c, grp_name, "☑").pack(fill=tk.X)

            # ─ 6 sütun grid: [checkbox | scale | %] × 2 — skalalar hizalı ─
            grid_f = tk.Frame(c, bg=_CARD)
            grid_f.pack(fill=tk.X, padx=10, pady=(4, 8))
            for _col, _minw in [(0, 210), (1, 100), (2, 48),
                                  (3, 210), (4, 100), (5, 48)]:
                grid_f.columnconfigure(_col, minsize=_minw)

            def _make_cmd(lbl, bv):
                def _cb(x):
                    v = int(float(x))
                    if v > 0:
                        bv.set(True)
                    lbl.configure(
                        text=f"{v:3d}%",
                        fg=(_FG3 if v == 0 else _ACC1 if v < 60 else _GREEN))
                return _cb

            for idx, item in enumerate(items):
                bool_var  = self.imla_vars[item]
                skala_var = self.imla_skala_vars[item]
                row_g    = idx // 2
                col_base = (idx % 2) * 3   # 0 veya 3

                # % etiketi — önce oluştur (Scale komutuna geçmek için)
                val_lbl = tk.Label(grid_f, text=f"{skala_var.get():3d}%",
                                   bg=_CARD, fg=_ACC1, font=_FSB, width=4)

                # Checkbox — sütun 0 veya 3, sabit genişlik sayesinde hizalı
                tk.Checkbutton(grid_f, text=item, variable=bool_var,
                               bg=_CARD, fg=_FG, font=_FS,
                               selectcolor="#ffffff", activebackground=_CARD,
                               wraplength=180, justify=tk.LEFT, anchor=tk.W
                               ).grid(row=row_g, column=col_base,
                                      sticky=tk.W, padx=(4, 2), pady=2)

                # Scale — sütun 1 veya 4: tüm skalalar aynı X'te başlar
                tk.Scale(grid_f, variable=skala_var, from_=0, to=100,
                         orient=tk.HORIZONTAL, length=90,
                         bg=_CARD, fg=_FG, troughcolor=_PANEL,
                         highlightthickness=0, showvalue=False,
                         command=_make_cmd(val_lbl, bool_var)
                         ).grid(row=row_g, column=col_base + 1,
                                sticky=tk.W, padx=(0, 2), pady=2)

                # % etiketi — sütun 2 veya 5
                val_lbl.grid(row=row_g, column=col_base + 2,
                             sticky=tk.W, padx=(0, 12))

        # Serbest metin
        c2 = _card(scroll, padx=0, pady=0)
        c2.pack(fill=tk.X, padx=16, pady=4)
        _section(c2, "Serbest İmla Açıklaması", "✏").pack(fill=tk.X)
        sf = tk.Frame(c2, bg=_CARD)
        sf.pack(fill=tk.X, padx=12, pady=8)
        _lbl(sf, "Bu yazmanın özel imla özellikleri:", bg=_CARD, fg=_FG2, font=_FSB).pack(anchor=tk.W)
        self._imla_text = tk.Text(sf, height=4, width=72,
                                   bg="#ffffff", fg=_FG, font=_F,
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
                                      bg="#ffffff", fg=_FG, font=_F,
                                      insertbackground=_FG, relief=tk.FLAT,
                                      highlightbackground=_BORDER, highlightthickness=1,
                                      padx=6, pady=4, wrap=tk.WORD)
        self._aktarim_text.pack(fill=tk.X, pady=(4,0))

    # ════════════════════════════════════════════════════════════════
    #  ADIM 4 — Metin Yapısı
    # ════════════════════════════════════════════════════════════════

    def _s4(self):
        _, scroll = _scrolled_frame(self._area)

        # ─ Ana Metin sayfaları (her zaman görünür) ─
        cm = _card(scroll, padx=0, pady=0)
        cm.pack(fill=tk.X, padx=16, pady=(14, 6))
        _section(cm, "Ana Metin Kısmı", "📖").pack(fill=tk.X)
        mf = tk.Frame(cm, bg=_CARD)
        mf.pack(anchor=tk.W, padx=14, pady=10)
        _lbl(mf, "Metin başlangıç sayfası:", bg=_CARD, fg=_FG2, font=_FSB).pack(
            side=tk.LEFT, padx=(0, 6))
        _spin(mf, self.metin_bas_var, lo=0, width=6).pack(side=tk.LEFT)
        _lbl(mf, "   Bitiş:", bg=_CARD, fg=_FG2, font=_FSB).pack(
            side=tk.LEFT, padx=(12, 6))
        _spin(mf, self.metin_bit_var, lo=0, width=6).pack(side=tk.LEFT)
        _lbl(mf, "   (0 = otomatik algıla)", bg=_CARD, fg=_FG3, font=_FS).pack(
            side=tk.LEFT, padx=8)

        info = tk.Frame(scroll, bg="#e8f5eb")
        info.pack(fill=tk.X, padx=16, pady=(4, 8))
        tk.Label(info,
                 text="📑  Transkripsiyon kaynağında hangi bölümler var ve kaçıncı sayfalarda?\n"
                      "Bu bilgi, yalnızca metin kısmını öğrenmek için doğru sayfaları seçmeye yarar.",
                 bg="#e8f5eb", fg=_GREEN, font=_FS,
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
                      font=_FS, bg="#dde5f5", fg=_FG,
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

        _frow(g, "Alan:",         lambda: _combo(g, self.alan_var,   ALANLAR,    24), 0, 0)
        _frow(g, "Dönem:",        lambda: _combo(g, self.donem_var,  DONEMLER,   24), 1, 0)
        _frow(g, "Yazı Türü:",    lambda: _combo(g, self.yazi_var,   YAZI_TURLERI, 24), 2, 0)
        _frow(g, "Hareke:",       lambda: _combo(g, self.hareke_var, HAREKE_DURUMLARI, 24), 3, 0)
        _frow(g, "Yazı Sistemi\n(Dil):",
              lambda: _combo(g, self.dil_var, DIL_GORUNUM_LISTE, 42), 4, 0)

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

        # Harf formları — sol: tablo, sağ: çeviri yazı klavyesi
        c2 = _card(scroll, padx=0, pady=0)
        c2.pack(fill=tk.X, padx=16, pady=6)
        _section(c2, "Harf Formları (Paleografi Notu)", "حـ").pack(fill=tk.X)

        # İki sütun: sol = tablo, sağ = klavye
        hf_outer = tk.Frame(c2, bg=_CARD)
        hf_outer.pack(fill=tk.X, padx=4, pady=4)

        # Sol: tablo
        hf_left = tk.Frame(hf_outer, bg=_CARD)
        hf_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 4))

        tk.Label(hf_left,
                 text="Yazmanın tanıtımında/tezinde harf biçimlerine dair bilgi "
                      "varsa girebilirsiniz.  Harf · Konum · Örnek kelime · Açıklama",
                 bg=_CARD, fg=_FG2, font=_FS,
                 justify=tk.LEFT, anchor=tk.W, pady=4).pack(fill=tk.X)

        hch = tk.Frame(hf_left, bg=_CARD)
        hch.pack(fill=tk.X, pady=(0, 2))
        for txt, w in [("Harf", 6), ("Konum", 10), ("Örnek Kelime", 14),
                       ("Açıklama", 20), ("Görüntüler", 9), ("", 4)]:
            tk.Label(hch, text=txt, bg=_CARD, fg=_FG3, font=_FSB,
                     width=w, anchor=tk.W).pack(side=tk.LEFT, padx=2)

        self._harf_frame = tk.Frame(hf_left, bg=_CARD)
        self._harf_frame.pack(fill=tk.X, pady=2)

        for row in self._harf_rows:
            self._render_harf_row(row)

        _btn(hf_left, "➕  Harf Formu Ekle",
             self._add_harf, "ghost").pack(anchor=tk.W, pady=(4, 8))

        # Sağ: çeviri yazı / Arap harfleri klavyesi
        hf_right = tk.Frame(hf_outer, bg=_PANEL, width=200)
        hf_right.pack(side=tk.RIGHT, fill=tk.Y, padx=(4, 8), pady=4)
        hf_right.pack_propagate(False)
        _ceviri_yazi_panel(hf_right, self)

        # ─ Kelime Yoğunluğu ─
        cw = _card(scroll, padx=0, pady=0)
        cw.pack(fill=tk.X, padx=16, pady=6)
        _section(cw, "Yaklaşık Kelime Yoğunluğu", "📊").pack(fill=tk.X)
        tk.Label(cw,
                 text="Metindeki Arapça / Farsça / Türkçe kelime oranı (yaklaşık %)",
                 bg=_CARD, fg=_FG2, font=_FS, padx=14, pady=4,
                 anchor=tk.W).pack(fill=tk.X)
        wf = tk.Frame(cw, bg=_CARD)
        wf.pack(fill=tk.X, padx=14, pady=(2,10))

        def _yogun_row(parent, label, var):
            rf = tk.Frame(parent, bg=_CARD)
            rf.pack(fill=tk.X, pady=2)
            tk.Label(rf, text=label, bg=_CARD, fg=_FG2, font=_FSB, width=14,
                     anchor=tk.W).pack(side=tk.LEFT)
            pct_lbl = tk.Label(rf, text=f"{var.get():3d}%",
                               bg=_CARD, fg=_ACC1, font=_FSB, width=5)
            pct_lbl.pack(side=tk.LEFT, padx=4)
            tk.Scale(rf, variable=var, from_=0, to=100,
                     orient=tk.HORIZONTAL, length=220,
                     bg=_CARD, fg=_FG, troughcolor=_PANEL,
                     highlightthickness=0, showvalue=False,
                     command=lambda v, l=pct_lbl: l.configure(
                         text=f"{int(float(v)):3d}%")).pack(side=tk.LEFT)

        _yogun_row(wf, "Arapça:", self.arapca_yogun_var)
        _yogun_row(wf, "Farsça:",  self.farsca_yogun_var)
        _yogun_row(wf, "Türkçe:", self.turkce_yogun_var)

        # Genel notlar
        c3 = _card(scroll, padx=0, pady=0)
        c3.pack(fill=tk.X, padx=16, pady=(6,14))
        _section(c3, "Genel Notlar", "📝").pack(fill=tk.X)
        nf = tk.Frame(c3, bg=_CARD)
        nf.pack(fill=tk.X, padx=12, pady=8)
        self._not_text = tk.Text(nf, height=4, width=72,
                                  bg="#ffffff", fg=_FG, font=_F,
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
        if "goruntular" not in row:
            row["goruntular"] = []
        f = tk.Frame(self._harf_frame, bg=_CARD)
        f.pack(fill=tk.X, pady=2)
        row["_frame"] = f
        _entry(f, row["harf"],   width=5).pack(side=tk.LEFT, padx=2)
        _combo(f, row["konum"],  ["baş","orta","son","bağımsız"], width=9).pack(side=tk.LEFT, padx=2)
        _entry(f, row["kelime"], width=13).pack(side=tk.LEFT, padx=2)
        _entry(f, row["acikl"],  width=22).pack(side=tk.LEFT, padx=2)
        # Görüntü sayısı etiketi + buton
        row["_img_lbl"] = tk.Label(f, text=f"🖼 {len(row['goruntular'])}",
                                    bg=_CARD, fg=_FG2, font=_FS, cursor="hand2")
        row["_img_lbl"].pack(side=tk.LEFT, padx=2)
        row["_img_lbl"].bind("<Button-1>",
                              lambda e, r=row: self._show_harf_images(r))
        _btn(f, "✖", lambda fr=f, r=row: self._del_harf(fr, r), "danger").pack(
            side=tk.LEFT, padx=4)

    def _del_harf(self, frame, row):
        frame.destroy()
        if row in self._harf_rows:
            self._harf_rows.remove(row)

    def _show_harf_images(self, row: dict):
        """Harf görüntüleri mini-diyalogu: ekle / sil / önizle."""
        dlg = tk.Toplevel(self)
        dlg.title(f"Harf Görüntüleri — {row['harf'].get() or '?'}")
        dlg.configure(bg=_BG)
        dlg.geometry("520x420")
        dlg.minsize(420, 300)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()

        _lbl(dlg,
             "Harfin başta / ortada / sonda biçimlerini gösteren\n"
             "ekran görüntüleri veya kesintiler ekleyin.",
             fg=_FG2, font=_FS).pack(anchor=tk.W, padx=14, pady=(10,4))

        list_f = tk.Frame(dlg, bg=_BG)
        list_f.pack(fill=tk.BOTH, expand=True, padx=14, pady=4)

        # PIL thumbnail desteği
        _pil_ok = False
        try:
            from PIL import Image, ImageTk
            _pil_ok = True
        except ImportError:
            pass

        _photo_refs: list = []   # garbage collector'dan korur

        def refresh():
            for w in list_f.winfo_children():
                w.destroy()
            _photo_refs.clear()
            if not row["goruntular"]:
                _lbl(list_f, "Henüz görüntü eklenmedi.",
                     fg=_FG3, font=_FS).pack(anchor=tk.W, pady=8)
                return
            for idx, path in enumerate(row["goruntular"]):
                rf = tk.Frame(list_f, bg=_CARD)
                rf.pack(fill=tk.X, pady=2)
                # Küçük önizleme
                if _pil_ok:
                    try:
                        img = Image.open(path)
                        img.thumbnail((64, 64))
                        photo = ImageTk.PhotoImage(img)
                        _photo_refs.append(photo)
                        tk.Label(rf, image=photo, bg=_CARD).pack(
                            side=tk.LEFT, padx=4, pady=2)
                    except Exception:
                        _lbl(rf, "🖼", fg=_FG2, bg=_CARD, font=("Segoe UI",18)).pack(
                            side=tk.LEFT, padx=4)
                else:
                    _lbl(rf, "🖼", fg=_FG2, bg=_CARD, font=("Segoe UI",18)).pack(
                        side=tk.LEFT, padx=4)
                nm = Path(path).name
                _lbl(rf, nm if len(nm)<48 else nm[:45]+"…",
                     fg=_FG, bg=_CARD, font=_FS).pack(
                    side=tk.LEFT, padx=4, expand=True, anchor=tk.W)
                _btn(rf, "✖",
                     lambda p=path: (row["goruntular"].remove(p), refresh()),
                     "danger").pack(side=tk.RIGHT, padx=4)

        def add_img():
            ft = [("Görüntü","*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp"),
                  ("Tüm Dosyalar","*.*")]
            p = filedialog.askopenfilename(
                filetypes=ft, title="Harf Görüntüsü Seç", parent=dlg)
            if p:
                row["goruntular"].append(p)
                # Etiket güncelle
                if "_img_lbl" in row:
                    row["_img_lbl"].configure(
                        text=f"🖼 {len(row['goruntular'])}")
                refresh()

        def paste_img():
            """Panodan görüntü yapıştır (Win: PrintScreen / Ctrl+C sonrası)."""
            try:
                from PIL import ImageGrab
                img = ImageGrab.grabclipboard()
                if img is None:
                    messagebox.showwarning("Pano",
                        "Panoda görüntü yok.\n"
                        "Önce ekran görüntüsü alın (PrtScr) veya\n"
                        "bir görüntüyü kopyalayın.", parent=dlg)
                    return
                import tempfile, os
                tmp_dir = Path.home() / ".metin_atolyesi"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                tmp = tempfile.NamedTemporaryFile(
                    suffix=".png", delete=False,
                    dir=str(tmp_dir))
                img.save(tmp.name)
                tmp.close()
                row["goruntular"].append(tmp.name)
                if "_img_lbl" in row:
                    row["_img_lbl"].configure(
                        text=f"🖼 {len(row['goruntular'])}")
                refresh()
            except ImportError:
                messagebox.showwarning("PIL Gerekli",
                    "Pano yapıştırma için Pillow gerekli.\n"
                    "pip install Pillow", parent=dlg)
            except Exception as exc:
                messagebox.showerror("Hata", str(exc), parent=dlg)

        refresh()

        btn_f = tk.Frame(dlg, bg=_BG)
        btn_f.pack(fill=tk.X, padx=14, pady=(4,12))
        _btn(btn_f, "➕  Görüntü Ekle", add_img, "primary").pack(side=tk.LEFT, padx=(0,6))
        _btn(btn_f, "📋  Panodan Yapıştır", paste_img, "ghost").pack(side=tk.LEFT)
        _btn(btn_f, "✓  Tamam", dlg.destroy, "success").pack(side=tk.RIGHT)

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

        # Dil kodu: görüntü etiketini koda çevir
        dil_gorunum = self.dil_var.get()
        dil_kodu = DIL_GORUNUM.get(dil_gorunum, "ara")

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
            dil_kodu        = dil_kodu,
            sutun_sayisi    = self.sutun_var.get(),
            toplam_varak    = self.toplam_varak_var.get(),
            varak_satir     = varak,
            icerik_turleri  = [k for k, v in self.icerik_vars.items() if v.get()],
            mensur_manzum   = self.mensur_manzum_var.get(),
            trans_isaretleri = [
                {"isaret":     r["isaret"].get(),
                 "arap_harfi": r.get("arap_harfi", tk.StringVar()).get()
                               if isinstance(r.get("arap_harfi"), tk.StringVar)
                               else r.get("arap_harfi",""),
                 "karsilik":   r["karsilik"].get(),
                 "dosyalar":   r.get("dosyalar",[])}
                for r in self._trans_rows if r["isaret"].get()
            ],
            varak_baslangic  = self.varak_baslangic_var.get().strip(),
            varak_bitis      = self.varak_bitis_var.get().strip(),
            pdf_format       = self.pdf_format_var.get(),
            sayfa_yonu       = self.sayfa_yonu_var.get(),
            beyit_duzen      = self.beyit_duzen_var.get(),
            ilk_varak_durum  = self.ilk_varak_durum_var.get(),
            son_varak_durum  = self.son_varak_durum_var.get(),
            ic_sayfa_durum   = self.ic_sayfa_durum_var.get(),
            metin_baslangic  = self.metin_bas_var.get(),
            metin_bitis      = self.metin_bit_var.get(),
            trans_varak_bas  = self.trans_varak_bas_var.get().strip(),
            trans_varak_bit  = self.trans_varak_bit_var.get().strip(),
            imla_secimler   = [k for k, v in self.imla_vars.items() if v.get()],
            imla_skalalar   = {k: v.get() for k, v in self.imla_skala_vars.items()
                               if self.imla_vars[k].get()},
            imla_serbest    = imla_st,
            aktarim_ilkeleri = aktarim,
            metin_bolumleri = bolumleri,
            kaynak_turu     = self.kaynak_turu_var.get(),
            kelime_yogunlugu = {
                "Arapça": self.arapca_yogun_var.get(),
                "Farsça":  self.farsca_yogun_var.get(),
                "Türkçe": self.turkce_yogun_var.get(),
            },
            harf_formlari   = [
                HarfFormu(
                    harf          = r["harf"].get(),
                    konum         = r["konum"].get(),
                    ornek_kelime  = r["kelime"].get(),
                    aciklama      = r["acikl"].get(),
                    goruntu_yollar = r.get("goruntular", []),
                )
                for r in self._harf_rows if r["harf"].get()
            ],
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
            self._pause_btn.configure(text="⏸  Mola Ver", bg=_PANEL)
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
                lib                    = get_library()
                count, done_flag, eid  = lib.teach(
                    ms_pdf       = Path(self.ms_path_var.get()),
                    trans_source = Path(self.trans_path_var.get()),
                    ms_pages     = (ms_start, ms_end),
                    trans_pages  = (tr_start, tr_end),
                    meta         = meta,
                    progress_cb  = self._on_prog,
                    stop_event   = self._stop_event,
                    pause_event  = self._pause_event,
                )
                self.after(0, lambda: self._on_done(count, done_flag, eid))
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

    def _on_done(self, count: int, completed: bool, entry_id: str = ""):
        elapsed = time.time() - self._start_time

        # Kontrol butonlarını kapat
        self._pause_btn.configure(state=tk.DISABLED)
        self._stop_btn.configure(state=tk.DISABLED)

        # Sonuç adımı için sakla
        self._last_entry_id = entry_id
        self._learning_done = True

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
                parent=self.winfo_toplevel(),
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
                parent=self.winfo_toplevel(),
            )

        try:
            from metin_atolyesi.core.github_sync import get_sync
            get_sync().schedule_push(delay=3.0)
        except Exception:
            pass

        # Sonuç sekmesine git — _update_bar komutunu sıfırlar, biz sadece adımı değiştiriyoruz
        self._learning_done = True
        self._show_step(self._SONUC_STEP)

        # OCR paneline meta veri aktar (varsa)
        if self.on_learning_done:
            try:
                import dataclasses
                meta = self._build_meta()
                meta_dict = dataclasses.asdict(meta) if dataclasses.is_dataclass(meta) else {}
                self.on_learning_done(meta_dict)
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

    # ════════════════════════════════════════════════════════════════
    #  AUTO-FILL — Daha önce girilen eser bilgilerini yükle
    # ════════════════════════════════════════════════════════════════

    def _autofill_debounce(self, *_):
        """Eser adı değişince 700 ms bekle, sonra kütüphanede ara."""
        if self._autofill_in_progress:
            return
        if self._autofill_timer:
            try:
                self.after_cancel(self._autofill_timer)
            except Exception:
                pass
        self._autofill_timer = self.after(700, self._autofill_check)

    def _autofill_check(self):
        """Eser adıyla eşleşen önceki kayıt varsa teklif et."""
        self._autofill_timer = None
        if self._autofill_in_progress:
            return
        name = self.eser_adi_var.get().strip()
        if len(name) < 2 or name.lower() == self._autofill_done_for.lower():
            return
        try:
            lib     = get_library()
            entries = lib.list_entries()
        except Exception:
            return
        for entry in reversed(entries):
            if entry.get("eser_adi", "").strip().lower() == name.lower():
                self._offer_autofill(entry)
                return

    def _offer_autofill(self, entry: dict):
        """Önceki kayıt bulundu diyalogu."""
        self._autofill_done_for = self.eser_adi_var.get().strip()
        if messagebox.askyesno(
            "Önceki Kayıt Bulundu",
            f"'{entry.get('eser_adi')}' adlı eser daha önce sisteme girilmiş.\n\n"
            "Önceki giriş bilgilerini (el yazması yolu, imla, yapı, paleografi…)\n"
            "otomatik doldurmak ister misiniz?",
            parent=self.winfo_toplevel(),
        ):
            self._do_autofill(entry)

    def _do_autofill(self, entry: dict):
        """Kayıttaki tüm meta bilgileri wizard değişkenlerine yükler."""
        self._autofill_in_progress = True
        try:
            meta = entry.get("meta", {})

            # ── Temel kimlik ────────────────────────────────────────
            self.yazar_var.set(meta.get("yazar", ""))
            self.muellif_var.set(meta.get("muellif", ""))
            self.tarih_var.set(meta.get("istinsah_tarihi", ""))
            self.kutuphane_var.set(meta.get("kutuphanesi", ""))
            self.demir_no_var.set(meta.get("demirbaş_no", ""))
            self.tez_ref_var.set(meta.get("tez_referansi", ""))
            self.kaynak_turu_var.set(meta.get("kaynak_turu", "transkripsiyon"))

            # ── El yazması dosya yolu (mevcutsa) ────────────────────
            ms_pdf = entry.get("ms_pdf", "")
            if ms_pdf and Path(ms_pdf).exists():
                self.ms_path_var.set(ms_pdf)

            # ── Sayfa aralıkları ────────────────────────────────────
            self.ms_start_var.set(entry.get("ms_start", 0) + 1)
            self.ms_end_var.set(entry.get("ms_end", 10))

            # ── Varak bilgisi ───────────────────────────────────────
            self.varak_baslangic_var.set(meta.get("varak_baslangic", ""))
            self.varak_bitis_var.set(meta.get("varak_bitis", ""))
            self.toplam_varak_var.set(meta.get("toplam_varak", 0))
            self.sutun_var.set(meta.get("sutun_sayisi", 1))

            vs = meta.get("varak_satir", {})
            self.satir_min_var.set(vs.get("genel_min", 15))
            self.satir_max_var.set(vs.get("genel_max", 15))
            self.duzenli_var.set(vs.get("duzenli", True))
            self.ilk_varak_satir_var.set(vs.get("ilk_varak", 0))
            self.son_varak_satir_var.set(vs.get("son_varak", 0))
            self.baslik_satir_var.set(vs.get("baslik_varak", 0))
            self.ozel_varaklar_var.set(vs.get("ozel_varaklar", ""))
            self.varak_not_var.set(vs.get("notlar", ""))

            # ── İmla ────────────────────────────────────────────────
            imla_sec  = set(meta.get("imla_secimler", []))
            imla_skal = meta.get("imla_skalalar", {})
            for k, v in self.imla_vars.items():
                v.set(k in imla_sec)
            for k, v in self.imla_skala_vars.items():
                if k in imla_skal:
                    v.set(imla_skal[k])
            self.imla_serbest_var.set(meta.get("imla_serbest", ""))
            self.aktarim_ilk_var.set(meta.get("aktarim_ilkeleri", ""))

            # ── İçerik türü / üslup ─────────────────────────────────
            icerik_sec = set(meta.get("icerik_turleri", []))
            for k, v in self.icerik_vars.items():
                v.set(k in icerik_sec)
            self.mensur_manzum_var.set(meta.get("mensur_manzum", "Mensur"))

            # ── Transkripsiyon işaretleri ───────────────────────────
            self._trans_rows.clear()
            for rd in meta.get("trans_isaretleri", []):
                self._trans_rows.append({
                    "isaret":     tk.StringVar(value=rd.get("isaret", "")),
                    "arap_harfi": tk.StringVar(value=rd.get("arap_harfi", "")),
                    "karsilik":   tk.StringVar(value=rd.get("karsilik", "")),
                    "dosyalar":   list(rd.get("dosyalar", [])),
                })

            # ── Alan / yazı sistemi ─────────────────────────────────
            self.alan_var.set(meta.get("alan", "Osmanlıca"))
            self.donem_var.set(meta.get("donem", "Belirsiz"))
            self.yazi_var.set(meta.get("yazi_turu", "Nesih"))
            self.hareke_var.set(meta.get("hareke", "Harekesiz"))
            self.guven_var.set(meta.get("guven", 0.9))
            self.ozel_not_var.set(meta.get("ozel_notlar", ""))

            # Dil kodu → görüntü etiketi (ilk eşleşen)
            dil_kodu = meta.get("dil_kodu", "ara")
            dil_gorunum_etiket = DIL_GORUNUM_LISTE[0]
            for etk, kod in DIL_GORUNUM.items():
                if kod == dil_kodu:
                    dil_gorunum_etiket = etk
                    break
            self.dil_var.set(dil_gorunum_etiket)

            # ── PDF / Sayfa formatı ──────────────────────────────────
            self.pdf_format_var.set(meta.get("pdf_format", "tek"))
            self.sayfa_yonu_var.set(meta.get("sayfa_yonu", "dikey"))
            self.beyit_duzen_var.set(meta.get("beyit_duzen", "yan_yana"))
            self.ilk_varak_durum_var.set(meta.get("ilk_varak_durum", "Tam okunabilir"))
            self.son_varak_durum_var.set(meta.get("son_varak_durum", "Tam okunabilir"))
            self.ic_sayfa_durum_var.set(meta.get("ic_sayfa_durum", "Tam okunabilir"))

            # ── Kelime yoğunluğu ────────────────────────────────────
            ky = meta.get("kelime_yogunlugu", {})
            self.arapca_yogun_var.set(ky.get("Arapça", 30))
            self.farsca_yogun_var.set(ky.get("Farsça",  20))
            self.turkce_yogun_var.set(ky.get("Türkçe", 50))

            # ── Harf formları ────────────────────────────────────────
            self._harf_rows.clear()
            for hf in meta.get("harf_formlari", []):
                self._harf_rows.append({
                    "harf":      tk.StringVar(value=hf.get("harf", "")),
                    "konum":     tk.StringVar(value=hf.get("konum", "baş")),
                    "kelime":    tk.StringVar(value=hf.get("ornek_kelime", "")),
                    "acikl":     tk.StringVar(value=hf.get("aciklama", "")),
                    "goruntular": list(hf.get("goruntu_yollar", [])),
                })

            # ── Metin bölümleri ─────────────────────────────────────
            self._bolum_rows.clear()
            for bm in meta.get("metin_bolumleri", []):
                self._bolum_rows.append({
                    "ad":   tk.StringVar(value=bm.get("ad", "")),
                    "bas":  tk.IntVar(value=bm.get("baslangic", 0)),
                    "bit":  tk.IntVar(value=bm.get("bitis", 0)),
                    "not_": tk.StringVar(value=bm.get("aciklama", "")),
                })
            self.metin_bas_var.set(meta.get("metin_baslangic", 0))
            self.metin_bit_var.set(meta.get("metin_bitis", 0))
            self.trans_varak_bas_var.set(meta.get("trans_varak_bas", ""))
            self.trans_varak_bit_var.set(meta.get("trans_varak_bit", ""))

        finally:
            self._autofill_in_progress = False

    # ════════════════════════════════════════════════════════════════
    #  ADIM 7 — Sonuç: Öğrenilen İçerik
    # ════════════════════════════════════════════════════════════════

    def _s7(self):
        _, scroll = _scrolled_frame(self._area)

        # Başlık
        top_f = tk.Frame(scroll, bg="#e8f5eb")
        top_f.pack(fill=tk.X, padx=16, pady=(14, 6))
        tk.Label(top_f,
                 text="📊  Öğrenilen içeriği aşağıda görebilirsiniz.\n"
                      "Eksik veya atlanan sayfaları tespit edip tekrar öğretebilirsiniz.",
                 bg="#e8f5eb", fg=_GREEN, font=_FS,
                 justify=tk.LEFT, padx=12, pady=8).pack(fill=tk.X)

        # Kütüphaneden giriş yükle
        lib     = get_library()
        entries = lib.list_entries()
        entry   = None
        for e in reversed(entries):
            if e.get("id") == self._last_entry_id:
                entry = e
                break
        if entry is None and entries:
            entry = entries[-1]   # son kaydı göster

        if not entry:
            _lbl(scroll, "Henüz öğrenilmiş kayıt bulunamadı.",
                 fg=_FG3, font=_F).pack(padx=16, pady=20)
            return

        pages   = entry.get("pages", [])
        partial = entry.get("partial", False)
        meta_d  = entry.get("meta", {})

        # ─ Özet kartı ─
        cs = _card(scroll, padx=0, pady=0)
        cs.pack(fill=tk.X, padx=16, pady=4)
        _section(cs, "Öğrenme Özeti", "✅" if not partial else "⏹").pack(fill=tk.X)

        sb = tk.Frame(cs, bg=_CARD)
        sb.pack(fill=tk.X, padx=14, pady=8)
        sb.columnconfigure(1, weight=1); sb.columnconfigure(3, weight=1)

        def _sr(r, c, lbl, val, vclr=_FG):
            tk.Label(sb, text=f"{lbl}:", bg=_CARD, fg=_FG2,
                     font=_FSB, width=18, anchor=tk.W).grid(
                row=r, column=c*2, sticky=tk.W, pady=3, padx=(0,4))
            tk.Label(sb, text=str(val), bg=_CARD, fg=vclr,
                     font=_F, anchor=tk.W).grid(
                row=r, column=c*2+1, sticky=tk.W, pady=3, padx=(0,20))

        _sr(0, 0, "Eser",          entry.get("eser_adi","—"))
        _sr(0, 1, "Durum",
            "Tamamlandı" if not partial else "Kısmi (durduruldu)",
            _GREEN if not partial else _AMBER)
        _sr(1, 0, "Öğrenilen Sayfa", f"{len(pages)} sayfa")
        _sr(1, 1, "Alan",           meta_d.get("alan","—"))
        _sr(2, 0, "Yazı Türü",      meta_d.get("yazi_turu","—"))
        _sr(2, 1, "Hareke",         meta_d.get("hareke","—"))

        # ─ Sayfa listesi ─
        cp = _card(scroll, padx=0, pady=0)
        cp.pack(fill=tk.X, padx=16, pady=4)
        _section(cp, f"Öğrenilen Sayfalar  ({len(pages)} adet)", "📋").pack(fill=tk.X)

        # Scrollable liste
        lf = tk.Frame(cp, bg=_CARD)
        lf.pack(fill=tk.X, padx=14, pady=8)

        for i, pg in enumerate(pages):
            from metin_atolyesi.core.manuscript_library import _load_sample_text
            text_preview = _load_sample_text(pg["hash"])[:80].replace("\n", " ")
            rf = tk.Frame(lf, bg="#eff1fa" if i % 2 == 0 else _CARD)
            rf.pack(fill=tk.X, pady=1)
            tk.Label(rf, text=f"  S.{pg['ms_page']+1:>4}",
                     bg=rf["bg"], fg=_GREEN, font=_FSB, width=8).pack(side=tk.LEFT)
            tk.Label(rf, text=text_preview or "(metin yok)",
                     bg=rf["bg"], fg=_FG if text_preview else _FG3,
                     font=_FS, anchor=tk.W).pack(side=tk.LEFT, padx=4)

        if not pages:
            _lbl(lf, "Hiç sayfa öğrenilmedi.", fg=_AMBER, font=_F).pack(pady=8)

        # ─ Eksik / Atlanan sayfalar ─
        ms_start = entry.get("ms_start", 0)
        ms_end   = entry.get("ms_end", 0)
        learned  = {pg["ms_page"] for pg in pages}
        missing  = [p for p in range(ms_start, ms_end) if p not in learned]

        if missing:
            cm2 = _card(scroll, padx=0, pady=0)
            cm2.pack(fill=tk.X, padx=16, pady=4)
            _section(cm2,
                     f"Atlanmış / Boş Sayfalar  ({len(missing)} adet)", "⚠").pack(fill=tk.X)
            mf2 = tk.Frame(cm2, bg=_CARD)
            mf2.pack(fill=tk.X, padx=14, pady=6)
            miss_txt = ", ".join(f"S.{p+1}" for p in missing[:30])
            if len(missing) > 30:
                miss_txt += f" … (+{len(missing)-30} daha)"
            tk.Label(mf2,
                     text=f"Bu sayfalar boş transkripsiyon nedeniyle atlandı:\n{miss_txt}",
                     bg=_CARD, fg=_AMBER, font=_FS,
                     justify=tk.LEFT, wraplength=660, padx=4, pady=4).pack(anchor=tk.W)

        # ─ Öğrenme Testi ─────────────────────────────────────────────
        ct = _card(scroll, padx=0, pady=0)
        ct.pack(fill=tk.X, padx=16, pady=(8, 4))
        _section(ct, "Öğrenme Testi — Kelimeyi Yazmada Bul", "🔍").pack(fill=tk.X)

        tk.Label(ct,
                 text="Bir kelime yazın → transkripsiyon metinlerinde aranır → "
                      "el yazması sayfasında kırmızı çerçeveyle gösterilir.",
                 bg=_CARD, fg=_FG2, font=_FS,
                 justify=tk.LEFT, padx=14, pady=4, wraplength=660).pack(fill=tk.X)

        # Arama satırı
        sr = tk.Frame(ct, bg=_CARD)
        sr.pack(fill=tk.X, padx=14, pady=(2, 4))
        _entry(sr, self._test_word_var, width=30).pack(side=tk.LEFT, padx=(0, 8))
        tk.Checkbutton(sr, text="Tüm kütüphane",
                       variable=self._test_all_var,
                       bg=_CARD, fg=_FG2, font=_FS,
                       selectcolor="#ffffff",
                       activebackground=_CARD).pack(side=tk.LEFT, padx=(0, 10))
        _btn(sr, "🔍  Ara",
             self._test_search, "primary").pack(side=tk.LEFT)

        # Sonuç alanı
        self._test_result_frame = tk.Frame(ct, bg=_CARD)
        self._test_result_frame.pack(fill=tk.X, padx=14, pady=(0, 10))

        # Enter tuşu da çalışsın
        def _enter_search(e):
            self._test_search()
        sr.winfo_children()[0].bind("<Return>", _enter_search)

        # ─ Eylem butonları ─
        act = tk.Frame(scroll, bg=_BG)
        act.pack(fill=tk.X, padx=16, pady=(8, 14))

        _btn(act, "🔄  Tekrar Öğret  (farklı sayfa / parametre)",
             lambda: self._show_step(self._SONUC_STEP - 1),
             "ghost").pack(side=tk.LEFT, padx=(0, 8))

        _btn(act, "✓  Kapat",
             self._on_close, "success").pack(side=tk.RIGHT)

        # _update_bar için adım adını da güncelle
        self._btn_back.configure(
            state=tk.NORMAL,
            text="◀  Özet'e Dön")

    # ════════════════════════════════════════════════════════════════
    #  Öğrenme Testi
    # ════════════════════════════════════════════════════════════════

    def _test_search(self):
        """Kelimeyi transkripsiyon metinlerinde arar, sonuçları listeler."""
        word = self._test_word_var.get().strip()
        if not word:
            messagebox.showwarning("Eksik", "Aranacak kelimeyi girin.", parent=self.winfo_toplevel())
            return

        # Önceki sonuçları temizle
        for w in self._test_result_frame.winfo_children():
            w.destroy()
        _lbl(self._test_result_frame, "🔄  Aranıyor…",
             fg=_FG2, font=_FS).pack(anchor=tk.W, pady=4)
        self.update_idletasks()

        lib = get_library()

        # Hangi eserde aranacak?
        if self._test_all_var.get():
            eser = ""
        else:
            eser = ""
            for e in lib.list_entries():
                if e.get("id") == self._last_entry_id:
                    eser = e.get("eser_adi", "")
                    break

        results = lib.search_in_transcriptions(word, eser_adi=eser)

        # Sonuçları temizle
        for w in self._test_result_frame.winfo_children():
            w.destroy()

        if not results:
            _lbl(self._test_result_frame,
                 f"'{word}' transkripsiyon metinlerinde bulunamadı.",
                 fg=_AMBER, font=_FS).pack(anchor=tk.W, pady=8)
            return

        _lbl(self._test_result_frame,
             f"✅  {len(results)} eşleşme — "
             "📍 Yazmada Göster ile sayfada konumunu görün:",
             fg=_GREEN, font=_FSB).pack(anchor=tk.W, pady=(4, 6))

        for res in results:
            rf = tk.Frame(self._test_result_frame, bg="#f0f2fa",
                          highlightbackground=_BORDER, highlightthickness=1)
            rf.pack(fill=tk.X, pady=2)

            # Sol: eser + sayfa
            info = f"  {res['eser_adi']}  S.{res['ms_page']+1}"
            tk.Label(rf, text=info, bg="#f0f2fa", fg=_ACC1,
                     font=_FSB, width=26, anchor=tk.W).pack(side=tk.LEFT, padx=4)

            # Bağlam metni — eşleşen kelime vurgulanmış
            ctx = res["context"]
            off = res["word_offset"]
            wln = res["word_len"]
            before  = ctx[:off]
            matched = ctx[off:off + wln]
            after   = ctx[off + wln:]

            ctx_f = tk.Frame(rf, bg="#f0f2fa")
            ctx_f.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
            pre = ("…" + before[-28:]) if len(before) > 28 else before
            suf = (after[:28] + "…") if len(after) > 28 else after
            tk.Label(ctx_f, text=pre,
                     bg="#f0f2fa", fg=_FG2, font=_FS).pack(side=tk.LEFT)
            tk.Label(ctx_f, text=matched,
                     bg="#fff3cd", fg="#8B4500", font=_FSB).pack(side=tk.LEFT)
            tk.Label(ctx_f, text=suf,
                     bg="#f0f2fa", fg=_FG2, font=_FS).pack(side=tk.LEFT)

            # Sağ: görüntüde bul — her zaman göster, yoksa dialog içinde seç
            _btn(rf, "📍  Yazmada Göster",
                 lambda r=res, w=word: self._show_word_in_image(r, w),
                 "primary" if res["has_img"] else "ghost"
                 ).pack(side=tk.RIGHT, padx=6, pady=3)

    def _show_word_in_image(self, result: dict, word: str):
        """Claude Vision ile kelimeyi görüntüde bul, kırmızı çerçeveyle göster."""
        from metin_atolyesi.core.manuscript_library import (
            _lib_dir, _extract_page_thumbnail, _save_sample, _read_jsonl, _index_path)
        from metin_atolyesi.core.claude_ocr import find_word_in_image

        thumb_path = _lib_dir() / "samples" / f"{result['hash']}.jpg"

        # Thumbnail yoksa — ms_pdf'den anlık çıkarmayı dene
        if not thumb_path.exists():
            ms_pdf_path = ""
            for e in _read_jsonl(_index_path()):
                if e.get("id") == result.get("entry_id"):
                    ms_pdf_path = e.get("ms_pdf", "")
                    break

            if ms_pdf_path and Path(ms_pdf_path).exists():
                img_bytes = _extract_page_thumbnail(
                    Path(ms_pdf_path), result["ms_page"])
                if img_bytes:
                    _save_sample(result["hash"], img_bytes, "")

            # Hâlâ yoksa — kullanıcıdan dosya seç
            if not thumb_path.exists():
                chosen = filedialog.askopenfilename(
                    parent=self.winfo_toplevel(),
                    title=f"S.{result['ms_page']+1} için el yazması görüntüsünü seçin",
                    filetypes=[
                        ("Görüntü", "*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp"),
                        ("PDF",     "*.pdf"),
                        ("Tüm",     "*.*"),
                    ],
                )
                if not chosen:
                    return
                chosen_p = Path(chosen)
                if chosen_p.suffix.lower() == ".pdf":
                    img_bytes = _extract_page_thumbnail(chosen_p, 0)
                    if img_bytes:
                        _save_sample(result["hash"], img_bytes, "")
                else:
                    # Doğrudan görüntü → kopyala
                    from PIL import Image as _PIL
                    import io as _io
                    buf = _io.BytesIO()
                    _PIL.open(chosen).convert("RGB").save(buf, "JPEG", quality=88)
                    _save_sample(result["hash"], buf.getvalue(), "")

            if not thumb_path.exists():
                messagebox.showerror("Görüntü Alınamadı",
                    "Seçilen dosyadan görüntü oluşturulamadı.", parent=self.winfo_toplevel())
                return

        # ── Dialog ──────────────────────────────────────────────────
        dlg = tk.Toplevel(self)
        dlg.title(f"🔍 '{word}'  —  S.{result['ms_page']+1}")
        dlg.configure(bg=_BG)
        dlg.geometry("720x620")
        dlg.minsize(520, 440)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()

        # Başlık bandı
        hf = tk.Frame(dlg, bg=_PANEL, height=46)
        hf.pack(fill=tk.X)
        hf.pack_propagate(False)
        tk.Label(hf,
                 text=f"  🔍  '{word}'  ·  {result['eser_adi']}  ·  S.{result['ms_page']+1}",
                 bg=_PANEL, fg=_FG, font=_FH).pack(side=tk.LEFT, padx=14, pady=10)

        # Durum satırı
        status_lbl = tk.Label(dlg, text="⏳  Claude Vision ile aranıyor…",
                               bg=_BG, fg=_AMBER, font=_FSB, anchor=tk.W)
        status_lbl.pack(fill=tk.X, padx=14, pady=(6, 2))

        # Konum açıklaması
        explain_lbl = tk.Label(dlg, text="", bg=_BG, fg=_FG2, font=_FS, anchor=tk.W)
        explain_lbl.pack(fill=tk.X, padx=14, pady=(0, 4))

        # Görüntü alanı (canvas + scrollbar)
        img_outer = tk.Frame(dlg, bg=_BG)
        img_outer.pack(fill=tk.BOTH, expand=True, padx=14, pady=2)

        # Alt: kapat
        _btn(dlg, "✓  Kapat", dlg.destroy, "ghost").pack(
            side=tk.RIGHT, padx=14, pady=8)

        # ── Görüntüyü çiz ───────────────────────────────────────────
        def _display_image(konum: dict | None):
            for w in img_outer.winfo_children():
                w.destroy()
            try:
                from PIL import Image, ImageDraw, ImageTk

                img = Image.open(thumb_path)

                if konum:
                    draw = ImageDraw.Draw(img)
                    iw, ih = img.size
                    x1 = int(konum["x1"] / 100 * iw)
                    y1 = int(konum["y1"] / 100 * ih)
                    x2 = int(konum["x2"] / 100 * iw)
                    y2 = int(konum["y2"] / 100 * ih)
                    # Kırmızı kalın çerçeve (5 piksel)
                    for t in range(5):
                        draw.rectangle(
                            [x1 - t, y1 - t, x2 + t, y2 + t],
                            outline="#ff2020")
                    # Turuncu dış çerçeve (belirginlik için)
                    for t in range(2):
                        draw.rectangle(
                            [x1 - 8 - t, y1 - 8 - t, x2 + 8 + t, y2 + 8 + t],
                            outline="#ff8c00")

                # Genişliğe sığdır
                dlg.update_idletasks()
                max_w = max(dlg.winfo_width() - 32, 500)
                if img.width > max_w:
                    ratio = max_w / img.width
                    img   = img.resize(
                        (max_w, int(img.height * ratio)), Image.LANCZOS)

                photo = ImageTk.PhotoImage(img)

                # Canvas + dikey scrollbar
                sb_c = ttk.Scrollbar(img_outer, orient=tk.VERTICAL)
                c = tk.Canvas(img_outer, bg="#e8e8f0",
                              highlightthickness=0,
                              yscrollcommand=sb_c.set)
                sb_c.configure(command=c.yview)
                sb_c.pack(side=tk.RIGHT, fill=tk.Y)
                c.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

                c.create_image(0, 0, anchor=tk.NW, image=photo)
                c.configure(scrollregion=(0, 0, img.width, img.height))
                c.image = photo   # GC koruması

                # Kelime bulunduysa o bölgeye kaydır
                if konum:
                    c.yview_moveto(max(0.0, konum["y1"] / 100 - 0.12))

                def _mw(e):
                    c.yview_scroll(int(-1 * (e.delta / 120)), "units")
                c.bind_all("<MouseWheel>", _mw)

            except ImportError:
                _lbl(img_outer,
                     "PIL/Pillow kurulu değil — görüntü gösterilemiyor.\n"
                     "pip install Pillow", fg=_AMBER, font=_F).pack(pady=20)
            except Exception as exc:
                _lbl(img_outer, f"Görüntü hatası: {exc}",
                     fg=_ACC2, font=_FS).pack(pady=8)

        # ── Arka plan iş parçacığı ──────────────────────────────────
        def _run():
            loc = find_word_in_image(thumb_path, word)
            dlg.after(0, lambda: _show_result(loc))

        def _show_result(loc: dict):
            if "hata" in loc:
                status_lbl.configure(
                    text=f"❌  {loc['hata']}", fg=_ACC2)
                _display_image(None)
                return
            if not loc.get("bulundu", False):
                status_lbl.configure(
                    text=f"⚠  '{word}' bu sayfada bulunamadı — "
                         "transkripsiyon metni doğru ama görüntü belirsiz olabilir.",
                    fg=_AMBER)
                explain_lbl.configure(text=loc.get("aciklama", ""))
                _display_image(None)
                return
            konum = loc.get("konum")
            status_lbl.configure(
                text=f"✅  '{word}' kırmızı çerçeveyle işaretlendi",
                fg=_GREEN)
            explain_lbl.configure(
                text=f"📍  {loc.get('aciklama', '')}")
            _display_image(konum)

        dlg.update_idletasks()
        threading.Thread(target=_run, daemon=True).start()


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
        top = tk.Frame(self, bg=_PANEL, height=48)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="  📚  Öğrenilmiş Yazma Kütüphanesi",
                 bg=_PANEL, fg=_FG, font=_FH).pack(side=tk.LEFT, padx=16, pady=12)

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
    """Sihirbazı ayrı Toplevel penceresinde açar (eski uyumluluk)."""
    dlg = tk.Toplevel(parent)
    dlg.title("El Yazması Öğretme Sihirbazı")
    dlg.configure(bg=_BG)
    dlg.resizable(True, True)
    _sw = dlg.winfo_screenwidth()
    _sh = dlg.winfo_screenheight()
    _ww = max(900, int(_sw * 0.80))
    _wh = max(660, int(_sh * 0.80))
    _wx = (_sw - _ww) // 2
    _wy = max(10, (_sh - _wh) // 2)
    dlg.geometry(f"{_ww}x{_wh}+{_wx}+{_wy}")
    dlg.minsize(800, 600)
    dlg.transient(parent)
    dlg.grab_set()
    wizard = ManuscriptWizard(dlg, on_close=dlg.destroy)
    wizard.pack(fill=tk.BOTH, expand=True)
    dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)

def open_library_viewer(parent):
    ManuscriptLibraryViewer(parent)
