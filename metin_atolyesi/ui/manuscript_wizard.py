"""El Yazması Öğretme Sihirbazı — 4 adımlı wizard arayüzü."""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from metin_atolyesi.core.manuscript_library import (
    ALANLAR, DONEMLER, HAREKE_DURUMLARI, YAZI_TURLERI,
    ManuscriptMeta, get_library,
)


# ── Renk ve stil sabitleri ────────────────────────────────────────────────

_BG      = "#1a1a2e"
_PANEL   = "#16213e"
_CARD    = "#0f3460"
_ACCENT  = "#e94560"
_ACCENT2 = "#0d6efd"
_FG      = "#e0e0f0"
_FG2     = "#a0a0c0"
_GREEN   = "#2ecc71"
_BORDER  = "#2a2a4a"

_FONT        = ("Segoe UI", 10)
_FONT_BOLD   = ("Segoe UI", 10, "bold")
_FONT_TITLE  = ("Segoe UI", 13, "bold")
_FONT_SMALL  = ("Segoe UI", 9)
_FONT_HEADER = ("Segoe UI", 11, "bold")


def _tk_label(parent, text, font=None, fg=None, bg=None, **kw):
    return tk.Label(parent, text=text,
                    font=font or _FONT, fg=fg or _FG, bg=bg or _BG, **kw)

def _tk_entry(parent, var, width=30, **kw):
    e = tk.Entry(parent, textvariable=var, width=width,
                 font=_FONT, bg="#1e1e3a", fg=_FG,
                 insertbackground=_FG,
                 relief=tk.FLAT, bd=1,
                 highlightbackground=_BORDER,
                 highlightthickness=1, **kw)
    return e

def _tk_combo(parent, var, values, width=22):
    cb = ttk.Combobox(parent, textvariable=var, values=values,
                      width=width, state="readonly", font=_FONT)
    return cb

def _step_btn(parent, text, command, primary=True):
    bg = _ACCENT2 if primary else "#2a2a4a"
    btn = tk.Button(parent, text=text, command=command,
                    font=_FONT_BOLD, bg=bg, fg="white",
                    relief=tk.FLAT, bd=0,
                    padx=18, pady=8,
                    cursor="hand2",
                    activebackground=_ACCENT if primary else "#3a3a5a",
                    activeforeground="white")
    return btn


# ── Ana Wizard Sınıfı ─────────────────────────────────────────────────────

class ManuscriptWizard(tk.Toplevel):
    """4 adımlı el yazması öğretme sihirbazı."""

    STEPS = ["Kaynak Seçimi", "Sayfa Aralıkları", "Alan Bilgisi", "Özet & Başlat"]

    def __init__(self, parent):
        super().__init__(parent)
        self.title("El Yazması Öğretme Sihirbazı")
        self.geometry("720x600")
        self.minsize(680, 560)
        self.configure(bg=_BG)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._step = 0
        self._init_vars()
        self._build()
        self._show_step(0)

    # ── Değişkenler ──────────────────────────────────────────────────────

    def _init_vars(self):
        self.ms_path_var    = tk.StringVar()
        self.trans_path_var = tk.StringVar()
        self.eser_adi_var   = tk.StringVar()

        self.ms_start_var   = tk.IntVar(value=1)
        self.ms_end_var     = tk.IntVar(value=10)
        self.tr_start_var   = tk.IntVar(value=1)
        self.tr_end_var     = tk.IntVar(value=10)
        self.sync_pages_var = tk.BooleanVar(value=True)

        self.alan_var       = tk.StringVar(value="Osmanlıca")
        self.donem_var      = tk.StringVar(value="Belirsiz")
        self.yazi_var       = tk.StringVar(value="Nesih")
        self.hareke_var     = tk.StringVar(value="Harekesiz")
        self.satir_var      = tk.IntVar(value=15)
        self.sutun_var      = tk.IntVar(value=1)
        self.yazar_var      = tk.StringVar()
        self.muellif_var    = tk.StringVar()
        self.dil_var        = tk.StringVar(value="ara")
        self.guven_var      = tk.DoubleVar(value=0.9)
        self.aciklama_var   = tk.StringVar()

    # ── Genel çerçeve ────────────────────────────────────────────────────

    def _build(self):
        # Başlık şeridi
        header = tk.Frame(self, bg=_CARD, height=56)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="  ✍  El Yazması Öğretme Sihirbazı",
                 bg=_CARD, fg=_FG,
                 font=_FONT_TITLE).pack(side=tk.LEFT, padx=16, pady=14)

        # Adım göstergesi
        self._step_bar = tk.Frame(self, bg=_PANEL, height=44)
        self._step_bar.pack(fill=tk.X)
        self._step_bar.pack_propagate(False)
        self._step_labels = []
        for i, name in enumerate(self.STEPS):
            lbl = tk.Label(self._step_bar,
                           text=f"  {i+1}. {name}  ",
                           font=_FONT_SMALL, bg=_PANEL, fg=_FG2,
                           pady=12)
            lbl.pack(side=tk.LEFT)
            self._step_labels.append(lbl)
            if i < len(self.STEPS) - 1:
                tk.Label(self._step_bar, text="›", bg=_PANEL,
                         fg=_FG2, font=_FONT_BOLD).pack(side=tk.LEFT)

        # İçerik alanı
        self._content = tk.Frame(self, bg=_BG)
        self._content.pack(fill=tk.BOTH, expand=True, padx=20, pady=12)

        # Alt butonlar
        nav = tk.Frame(self, bg=_PANEL, height=60)
        nav.pack(fill=tk.X, side=tk.BOTTOM)
        nav.pack_propagate(False)

        self._btn_back = _step_btn(nav, "◀  Geri", self._go_back, primary=False)
        self._btn_back.pack(side=tk.LEFT, padx=16, pady=10)
        self._btn_next = _step_btn(nav, "İleri  ▶", self._go_next, primary=True)
        self._btn_next.pack(side=tk.RIGHT, padx=16, pady=10)
        _step_btn(nav, "İptal", self.destroy, primary=False).pack(
            side=tk.RIGHT, padx=(0, 8), pady=10)

    # ── Adım göstergesi renklendirme ─────────────────────────────────────

    def _update_step_bar(self):
        for i, lbl in enumerate(self._step_labels):
            if i < self._step:
                lbl.configure(bg=_PANEL, fg=_GREEN)
            elif i == self._step:
                lbl.configure(bg=_ACCENT2, fg="white")
            else:
                lbl.configure(bg=_PANEL, fg=_FG2)
        self._btn_back.configure(state=tk.NORMAL if self._step > 0 else tk.DISABLED)
        is_last = self._step == len(self.STEPS) - 1
        self._btn_next.configure(text="✓  Öğrenmeyi Başlat" if is_last else "İleri  ▶")

    # ── Adım geçişleri ────────────────────────────────────────────────────

    def _show_step(self, n: int):
        for w in self._content.winfo_children():
            w.destroy()
        self._step = n
        self._update_step_bar()
        [self._step1, self._step2, self._step3, self._step4][n]()

    def _go_next(self):
        if not self._validate():
            return
        if self._step < len(self.STEPS) - 1:
            self._show_step(self._step + 1)
        else:
            self._start_learning()

    def _go_back(self):
        if self._step > 0:
            self._show_step(self._step - 1)

    # ── Doğrulama ─────────────────────────────────────────────────────────

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
                messagebox.showwarning("Hata", "Başlangıç sayfası bitiş sayfasından küçük olmalı.", parent=self)
                return False
        return True

    # ╔══════════════════════════════════════════════════════════════╗
    # ║  ADIM 1 — Kaynak Seçimi                                     ║
    # ╚══════════════════════════════════════════════════════════════╝

    def _step1(self):
        f = self._content
        _tk_label(f, "El Yazması PDF", font=_FONT_HEADER).grid(
            row=0, column=0, sticky=tk.W, pady=(0, 4))

        ms_frame = tk.Frame(f, bg=_BG)
        ms_frame.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(0, 12))
        _tk_entry(ms_frame, self.ms_path_var, width=52).pack(side=tk.LEFT, padx=(0, 8))
        _step_btn(ms_frame, "📂 Seç", self._browse_ms).pack(side=tk.LEFT)

        _tk_label(f, "Transkripsiyon Kaynağı (PDF veya TXT)",
                  font=_FONT_HEADER).grid(row=2, column=0, sticky=tk.W, pady=(0, 4))
        _tk_label(f, "Daha önce okunmuş/yazılmış doğru metin",
                  fg=_FG2, font=_FONT_SMALL).grid(row=3, column=0, sticky=tk.W)

        tr_frame = tk.Frame(f, bg=_BG)
        tr_frame.grid(row=4, column=0, columnspan=2, sticky=tk.EW, pady=(4, 12))
        _tk_entry(tr_frame, self.trans_path_var, width=52).pack(side=tk.LEFT, padx=(0, 8))
        _step_btn(tr_frame, "📂 Seç", self._browse_trans).pack(side=tk.LEFT)

        _tk_label(f, "Eser Adı", font=_FONT_HEADER).grid(
            row=5, column=0, sticky=tk.W, pady=(0, 4))
        _tk_entry(f, self.eser_adi_var, width=46).grid(
            row=6, column=0, sticky=tk.EW, pady=(0, 4))

        # İpucu kutusu
        tip = tk.Frame(f, bg="#0d2a1a", bd=0)
        tip.grid(row=7, column=0, columnspan=2, sticky=tk.EW, pady=(16, 0))
        tk.Label(tip,
                 text="💡  Transkripsiyon kaynağı: Elinizde varsa eserin matbu/dijital baskısı "
                      "ya da el yazısıyla hazırlanmış okunuşu olabilir. "
                      "Program bu çiftlerden öğrenerek benzer eserleri daha iyi okur.",
                 bg="#0d2a1a", fg="#a0d0b0", font=_FONT_SMALL,
                 wraplength=580, justify=tk.LEFT, pady=10, padx=10).pack(fill=tk.X)

        f.columnconfigure(0, weight=1)

    def _browse_ms(self):
        p = filedialog.askopenfilename(
            title="El Yazması PDF Seç",
            filetypes=[("PDF", "*.pdf"), ("Tüm dosyalar", "*.*")])
        if p:
            self.ms_path_var.set(p)
            if not self.eser_adi_var.get():
                self.eser_adi_var.set(Path(p).stem.replace("_", " "))

    def _browse_trans(self):
        p = filedialog.askopenfilename(
            title="Transkripsiyon Kaynağı Seç",
            filetypes=[("PDF / Metin", "*.pdf *.txt"), ("Tüm dosyalar", "*.*")])
        if p:
            self.trans_path_var.set(p)

    # ╔══════════════════════════════════════════════════════════════╗
    # ║  ADIM 2 — Sayfa Aralıkları                                  ║
    # ╚══════════════════════════════════════════════════════════════╝

    def _step2(self):
        f = self._content

        def _spin_row(parent, lbl_text, var, row):
            tk.Label(parent, text=lbl_text, bg=_BG, fg=_FG,
                     font=_FONT_BOLD).grid(row=row, column=0, sticky=tk.W, pady=6)
            sb = tk.Spinbox(parent, textvariable=var,
                            from_=1, to=9999, width=7,
                            font=_FONT, bg="#1e1e3a", fg=_FG,
                            buttonbackground="#2a2a4a",
                            relief=tk.FLAT, bd=1,
                            highlightbackground=_BORDER,
                            highlightthickness=1)
            sb.grid(row=row, column=1, sticky=tk.W, padx=12)

        # Yazma sayfaları
        card1 = tk.Frame(f, bg=_PANEL, padx=14, pady=10)
        card1.pack(fill=tk.X, pady=(0, 10))
        tk.Label(card1, text="📜  El Yazması Sayfaları",
                 bg=_PANEL, fg=_FG, font=_FONT_HEADER).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))
        _spin_row(card1, "Başlangıç Sayfası:", self.ms_start_var, 1)
        _spin_row(card1, "Bitiş Sayfası:",     self.ms_end_var,   2)

        # Senkronize seçeneği
        sync_frame = tk.Frame(f, bg=_BG)
        sync_frame.pack(fill=tk.X, pady=6)
        tk.Checkbutton(sync_frame,
                       text="Transkripsiyon sayfa numaraları el yazmasıyla aynı",
                       variable=self.sync_pages_var,
                       command=self._toggle_trans_pages,
                       bg=_BG, fg=_FG, font=_FONT,
                       selectcolor="#1e1e3a",
                       activebackground=_BG, activeforeground=_FG).pack(anchor=tk.W)

        # Transkripsiyon sayfaları
        self._trans_card = tk.Frame(f, bg=_PANEL, padx=14, pady=10)
        self._trans_card.pack(fill=tk.X, pady=(0, 10))
        tk.Label(self._trans_card, text="📝  Transkripsiyon Sayfaları",
                 bg=_PANEL, fg=_FG, font=_FONT_HEADER).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))
        _spin_row(self._trans_card, "Başlangıç Sayfası:", self.tr_start_var, 1)
        _spin_row(self._trans_card, "Bitiş Sayfası:",     self.tr_end_var,   2)

        self._toggle_trans_pages()

        # Bilgi
        tk.Label(f,
                 text="ℹ  Sayfa numaraları 1'den başlar. "
                      "Aralık dışındaki sayfalar atlanır.",
                 bg=_BG, fg=_FG2, font=_FONT_SMALL,
                 wraplength=560, justify=tk.LEFT).pack(anchor=tk.W, pady=(8, 0))

    def _toggle_trans_pages(self):
        state = tk.DISABLED if self.sync_pages_var.get() else tk.NORMAL
        for w in self._trans_card.winfo_children():
            try:
                w.configure(state=state)
            except Exception:
                pass

    # ╔══════════════════════════════════════════════════════════════╗
    # ║  ADIM 3 — Alan Bilgisi                                      ║
    # ╚══════════════════════════════════════════════════════════════╝

    def _step3(self):
        f = self._content

        def _row(parent, label, widget_fn, r, c=0):
            tk.Label(parent, text=label, bg=_PANEL, fg=_FG,
                     font=_FONT).grid(row=r, column=c, sticky=tk.W, pady=5, padx=(0, 8))
            w = widget_fn()
            w.grid(row=r, column=c+1, sticky=tk.W, pady=5)
            return w

        # Sol sütun
        left = tk.Frame(f, bg=_PANEL, padx=14, pady=10)
        left.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 8))

        tk.Label(left, text="🔤  Yazı ve Alan Bilgisi",
                 bg=_PANEL, fg=_FG, font=_FONT_HEADER).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        _row(left, "Alan:",        lambda: _tk_combo(left, self.alan_var,  ALANLAR,           width=22), 1)
        _row(left, "Dönem:",       lambda: _tk_combo(left, self.donem_var, DONEMLER,          width=22), 2)
        _row(left, "Yazı Türü:",   lambda: _tk_combo(left, self.yazi_var,  YAZI_TURLERI,      width=22), 3)
        _row(left, "Hareke:",      lambda: _tk_combo(left, self.hareke_var,HAREKE_DURUMLARI,  width=22), 4)
        _row(left, "Dil Kodu:",    lambda: _tk_combo(left, self.dil_var,
                                                     ["ara","tur","tur+ara","fas","deu","eng"], width=10), 5)

        # Sağ sütun
        right = tk.Frame(f, bg=_PANEL, padx=14, pady=10)
        right.grid(row=0, column=1, sticky=tk.NSEW)

        tk.Label(right, text="📐  Sayfa ve Kaynak Bilgisi",
                 bg=_PANEL, fg=_FG, font=_FONT_HEADER).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        def _spin(parent, var, r):
            sb = tk.Spinbox(parent, textvariable=var, from_=1, to=200, width=5,
                            font=_FONT, bg="#1e1e3a", fg=_FG,
                            relief=tk.FLAT, bd=1,
                            highlightbackground=_BORDER, highlightthickness=1)
            sb.grid(row=r, column=1, sticky=tk.W, pady=5)

        tk.Label(right, text="Satır / Sayfa:", bg=_PANEL, fg=_FG, font=_FONT).grid(
            row=1, column=0, sticky=tk.W, pady=5, padx=(0, 8))
        _spin(right, self.satir_var, 1)

        tk.Label(right, text="Sütun Sayısı:", bg=_PANEL, fg=_FG, font=_FONT).grid(
            row=2, column=0, sticky=tk.W, pady=5, padx=(0, 8))
        _spin(right, self.sutun_var, 2)

        tk.Label(right, text="Yazar / Müellif:", bg=_PANEL, fg=_FG, font=_FONT).grid(
            row=3, column=0, sticky=tk.W, pady=5, padx=(0, 8))
        _tk_entry(right, self.yazar_var, width=18).grid(row=3, column=1, sticky=tk.W, pady=5)

        tk.Label(right, text="Müstensih:", bg=_PANEL, fg=_FG, font=_FONT).grid(
            row=4, column=0, sticky=tk.W, pady=5, padx=(0, 8))
        _tk_entry(right, self.muellif_var, width=18).grid(row=4, column=1, sticky=tk.W, pady=5)

        # Güven skoru
        guven_frame = tk.Frame(f, bg=_BG)
        guven_frame.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(10, 0))
        tk.Label(guven_frame, text="Transkripsiyon Güven Derecesi:",
                 bg=_BG, fg=_FG, font=_FONT).pack(side=tk.LEFT)
        self._guven_lbl = tk.Label(guven_frame,
                                   text=f"%{int(self.guven_var.get()*100)}",
                                   bg=_BG, fg=_GREEN, font=_FONT_BOLD, width=5)
        self._guven_lbl.pack(side=tk.LEFT, padx=8)
        tk.Scale(guven_frame, variable=self.guven_var,
                 from_=0.1, to=1.0, resolution=0.05,
                 orient=tk.HORIZONTAL, length=200,
                 bg=_BG, fg=_FG, troughcolor=_PANEL,
                 highlightthickness=0, showvalue=False,
                 command=lambda v: self._guven_lbl.configure(
                     text=f"%{int(float(v)*100)}")
                 ).pack(side=tk.LEFT)

        f.columnconfigure(0, weight=1)
        f.columnconfigure(1, weight=1)

    # ╔══════════════════════════════════════════════════════════════╗
    # ║  ADIM 4 — Özet & Başlat                                     ║
    # ╚══════════════════════════════════════════════════════════════╝

    def _step4(self):
        f = self._content
        ms_pages = self.ms_end_var.get() - self.ms_start_var.get()

        summary = tk.Frame(f, bg=_PANEL, padx=20, pady=16)
        summary.pack(fill=tk.X, pady=(0, 12))

        tk.Label(summary, text="📋  Öğrenme Özeti",
                 bg=_PANEL, fg=_FG, font=_FONT_HEADER).pack(anchor=tk.W, pady=(0, 10))

        rows = [
            ("Eser Adı",       self.eser_adi_var.get() or "(isimsiz)"),
            ("El Yazması",     Path(self.ms_path_var.get()).name),
            ("Transkripsiyon", Path(self.trans_path_var.get()).name),
            ("Sayfa Aralığı",  f"{self.ms_start_var.get()} – {self.ms_end_var.get()} ({ms_pages} sayfa)"),
            ("Alan",           self.alan_var.get()),
            ("Dönem",          self.donem_var.get()),
            ("Yazı Türü",      self.yazi_var.get()),
            ("Hareke",         self.hareke_var.get()),
            ("Satır / Sayfa",  str(self.satir_var.get())),
            ("Güven",          f"%{int(self.guven_var.get()*100)}"),
        ]
        for lbl, val in rows:
            row_f = tk.Frame(summary, bg=_PANEL)
            row_f.pack(fill=tk.X, pady=2)
            tk.Label(row_f, text=f"{lbl}:", bg=_PANEL, fg=_FG2,
                     font=_FONT, width=18, anchor=tk.W).pack(side=tk.LEFT)
            tk.Label(row_f, text=val, bg=_PANEL, fg=_FG,
                     font=_FONT_BOLD).pack(side=tk.LEFT)

        # İlerleme göstergesi (başlatınca görünür)
        self._prog_frame = tk.Frame(f, bg=_BG)
        self._prog_frame.pack(fill=tk.X, pady=(8, 0))
        self._prog_bar = ttk.Progressbar(self._prog_frame, mode="determinate",
                                         length=460)
        self._prog_bar.pack(fill=tk.X, pady=(0, 4))
        self._prog_lbl = tk.Label(self._prog_frame, text="",
                                  bg=_BG, fg=_FG2, font=_FONT_SMALL)
        self._prog_lbl.pack(anchor=tk.W)
        self._prog_frame.pack_forget()

    # ── Öğrenmeyi Başlat ─────────────────────────────────────────────────

    def _start_learning(self):
        self._btn_next.configure(state=tk.DISABLED, text="⏳  İşleniyor…")
        self._btn_back.configure(state=tk.DISABLED)
        self._prog_frame.pack(fill=tk.X, pady=(8, 0))

        ms_start = self.ms_start_var.get() - 1   # 0-tabanlı
        ms_end   = self.ms_end_var.get()
        if self.sync_pages_var.get():
            tr_start, tr_end = ms_start, ms_end
        else:
            tr_start = self.tr_start_var.get() - 1
            tr_end   = self.tr_end_var.get()

        meta = ManuscriptMeta(
            eser_adi     = self.eser_adi_var.get().strip(),
            alan         = self.alan_var.get(),
            donem        = self.donem_var.get(),
            yazi_turu    = self.yazi_var.get(),
            hareke       = self.hareke_var.get(),
            satir_sayisi = self.satir_var.get(),
            sutun_sayisi = self.sutun_var.get(),
            yazar        = self.yazar_var.get().strip(),
            muellif      = self.muellif_var.get().strip(),
            dil_kodu     = self.dil_var.get(),
            guven        = self.guven_var.get(),
        )

        def _run():
            try:
                lib = get_library()
                count = lib.teach(
                    ms_pdf        = Path(self.ms_path_var.get()),
                    trans_source  = Path(self.trans_path_var.get()),
                    ms_pages      = (ms_start, ms_end),
                    trans_pages   = (tr_start, tr_end),
                    meta          = meta,
                    progress_cb   = self._on_progress,
                )
                self.after(0, lambda: self._on_done(count))
            except Exception as exc:
                self.after(0, lambda: self._on_error(str(exc)))

        threading.Thread(target=_run, daemon=True).start()

    def _on_progress(self, done: int, total: int):
        pct = int(done / max(total, 1) * 100)
        self._prog_bar["value"] = pct
        self._prog_lbl.configure(text=f"Sayfa {done}/{total} işleniyor…")
        self.update_idletasks()

    def _on_done(self, count: int):
        self._prog_bar["value"] = 100
        self._prog_lbl.configure(
            text=f"✅  {count} sayfa çifti başarıyla öğrenildi!",
            fg=_GREEN)
        self._btn_next.configure(text="✓  Kapat", state=tk.NORMAL,
                                 command=self.destroy)
        # GitHub'a push
        try:
            from metin_atolyesi.core.github_sync import get_sync
            get_sync().schedule_push(delay=3.0)
        except Exception:
            pass

    def _on_error(self, msg: str):
        self._prog_lbl.configure(text=f"❌  Hata: {msg[:120]}", fg=_ACCENT)
        self._btn_next.configure(text="Yeniden Dene", state=tk.NORMAL,
                                 command=self._start_learning)
        self._btn_back.configure(state=tk.NORMAL)


# ── Kütüphane Görüntüleyici ───────────────────────────────────────────────

class ManuscriptLibraryViewer(tk.Toplevel):
    """Öğrenilmiş yazma kütüphanesini gösterir."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Yazma Kütüphanesi")
        self.geometry("700x480")
        self.configure(bg=_BG)
        self.transient(parent)
        self._build()

    def _build(self):
        header = tk.Frame(self, bg=_CARD, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="  📚  Öğrenilmiş Yazma Kütüphanesi",
                 bg=_CARD, fg=_FG, font=_FONT_HEADER).pack(side=tk.LEFT, padx=16, pady=12)

        from metin_atolyesi.core.manuscript_library import get_library
        lib   = get_library()
        stats = lib.stats()

        # İstatistik bandı
        stat_frame = tk.Frame(self, bg=_PANEL)
        stat_frame.pack(fill=tk.X, padx=16, pady=(12, 4))
        for lbl, val in [
            ("Toplam Eser",  stats["toplam_eser"]),
            ("Toplam Sayfa", stats["toplam_sayfa"]),
            ("Depo",         str(Path(stats["depo_yolu"]).name)),
        ]:
            tk.Label(stat_frame, text=f"{lbl}: ", bg=_PANEL, fg=_FG2,
                     font=_FONT_SMALL).pack(side=tk.LEFT, padx=(10, 0))
            tk.Label(stat_frame, text=str(val), bg=_PANEL, fg=_FG,
                     font=_FONT_BOLD).pack(side=tk.LEFT, padx=(0, 16))

        # Tablo
        cols = ("Eser Adı", "Alan", "Dönem", "Yazı", "Sayfa")
        tree = ttk.Treeview(self, columns=cols, show="headings", height=15)
        for col in cols:
            tree.heading(col, text=col)
        tree.column("Eser Adı", width=200)
        tree.column("Alan",     width=150)
        tree.column("Dönem",    width=120)
        tree.column("Yazı",     width=100)
        tree.column("Sayfa",    width=60, anchor=tk.CENTER)

        for entry in lib.list_entries():
            m = entry.get("meta", {})
            tree.insert("", tk.END, values=(
                entry.get("eser_adi", "—"),
                m.get("alan", "—"),
                m.get("donem", "—"),
                m.get("yazi_turu", "—"),
                len(entry.get("pages", [])),
            ))

        sb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(16, 0), pady=8)
        sb.pack(side=tk.RIGHT, fill=tk.Y, pady=8, padx=(0, 8))


def open_wizard(parent) -> None:
    ManuscriptWizard(parent)

def open_library_viewer(parent) -> None:
    ManuscriptLibraryViewer(parent)
