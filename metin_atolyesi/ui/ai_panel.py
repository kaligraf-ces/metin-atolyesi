"""Metin Atölyesi — Yapay Zeka Komut Paneli.

Claude tabanlı dahili asistan: Doğal dil komutlarıyla programı yönetir,
Osmanlıca metinleri öğrenerek düzeltir.
"""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Any

# Tema renkleri
_BG     = "#eceef8"
_PANEL  = "#dde0f5"
_CARD   = "#ffffff"
_ACC1   = "#0d6efd"
_ACC2   = "#d92b4b"
_FG     = "#1a1c2e"
_FG2    = "#3c4060"
_FG3    = "#7078a8"
_GREEN  = "#1a7a40"
_AI_BG  = "#f0f4ff"   # AI mesaj balonu arka planı
_USR_BG = "#e8f5eb"   # Kullanıcı mesaj balonu arka planı
_TOOL_BG= "#fff8e1"   # Araç çalışma balonu


class AIPanel(ttk.Frame):
    """Yapay Zeka Komut Paneli — ana ekrana gömülü."""

    def __init__(self, master, get_context_cb: Callable[[], dict],
                 tool_handlers: dict[str, Callable] | None = None) -> None:
        """
        get_context_cb : Çağrıldığında mevcut program durumunu döndürür
        tool_handlers  : {araç_adı: callable(input_dict) → Any}
        """
        super().__init__(master)
        self._get_context = get_context_cb
        self._tool_handlers = tool_handlers or {}
        self._busy = False

        from metin_atolyesi.core.ai_assistant import get_assistant
        self._assistant = get_assistant()
        # Araç işleyicilerini asistana bağla
        self._assistant.tool_handlers = self._tool_handlers

        self._build()

    def update_tool_handlers(self, handlers: dict) -> None:
        """Araç işleyicilerini güncelle (main_window'dan çağrılır)."""
        self._tool_handlers.update(handlers)
        self._assistant.tool_handlers = self._tool_handlers

    # -----------------------------------------------------------------------
    # UI yapısı
    # -----------------------------------------------------------------------

    def _build(self) -> None:
        self.configure(style="TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # ── Üst başlık ──────────────────────────────────────────────────────
        header = tk.Frame(self, bg=_PANEL)
        header.grid(row=0, column=0, sticky=tk.EW, padx=0, pady=0)
        tk.Frame(header, bg=_ACC1, width=4).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(header, text="  🤖  Yapay Zeka Asistanı",
                 bg=_PANEL, fg=_FG, font=("Segoe UI", 11, "bold"),
                 pady=8, padx=6).pack(side=tk.LEFT)
        tk.Label(header,
                 text="Osmanlıca · Doğal Dil Kontrol · Öğrenme",
                 bg=_PANEL, fg=_FG2, font=("Segoe UI", 9)).pack(side=tk.LEFT)

        clear_btn = tk.Button(header, text="↺ Sıfırla", bg=_PANEL, fg=_FG2,
                              relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                              command=self._clear_history)
        clear_btn.pack(side=tk.RIGHT, padx=8)

        # ── Mesaj geçmişi ────────────────────────────────────────────────────
        msg_frame = tk.Frame(self, bg=_BG)
        msg_frame.grid(row=1, column=0, sticky=tk.NSEW, padx=8, pady=(6, 0))
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        msg_frame.columnconfigure(0, weight=1)
        msg_frame.rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(msg_frame, bg=_BG, highlightthickness=0)
        vscroll = ttk.Scrollbar(msg_frame, orient=tk.VERTICAL,
                                command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vscroll.set)
        self._canvas.grid(row=0, column=0, sticky=tk.NSEW)
        vscroll.grid(row=0, column=1, sticky=tk.NS)
        msg_frame.rowconfigure(0, weight=1)
        msg_frame.columnconfigure(0, weight=1)

        self._msg_inner = tk.Frame(self._canvas, bg=_BG)
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._msg_inner, anchor=tk.NW
        )
        self._msg_inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._msg_inner.bind("<MouseWheel>", self._on_wheel)

        # ── İlerleme göstergesi ──────────────────────────────────────────────
        self._progress_var = tk.StringVar(value="")
        self._progress_lbl = tk.Label(self, textvariable=self._progress_var,
                                      bg=_BG, fg=_ACC1,
                                      font=("Segoe UI", 9, "italic"), anchor=tk.W)
        self._progress_lbl.grid(row=2, column=0, sticky=tk.EW, padx=12, pady=(2, 0))

        # ── Giriş alanı ──────────────────────────────────────────────────────
        input_frame = tk.Frame(self, bg=_PANEL,
                               highlightbackground="#b0b5d5", highlightthickness=1)
        input_frame.grid(row=3, column=0, sticky=tk.EW, padx=8, pady=(4, 8))
        input_frame.columnconfigure(0, weight=1)

        self._input = tk.Text(
            input_frame, bg=_CARD, fg=_FG, insertbackground=_FG,
            font=("Segoe UI", 11), relief=tk.FLAT,
            wrap=tk.WORD, height=3, padx=8, pady=6,
        )
        self._input.grid(row=0, column=0, sticky=tk.EW, padx=(6, 0))
        self._input.bind("<Return>", self._on_enter)
        self._input.bind("<Shift-Return>", lambda e: None)  # Shift+Enter = yeni satır
        self._input.bind("<Control-Return>", lambda e: self._send())

        send_btn = tk.Button(
            input_frame, text="▶", bg=_ACC1, fg="white",
            font=("Segoe UI", 13), relief=tk.FLAT, cursor="hand2",
            width=3, pady=4, activebackground="#1a5fcc",
            command=self._send,
        )
        send_btn.grid(row=0, column=1, sticky=tk.NS, padx=(4, 6), pady=6)

        hint = tk.Label(input_frame,
                        text="Enter = gönder   Shift+Enter = yeni satır",
                        bg=_PANEL, fg=_FG3, font=("Segoe UI", 8))
        hint.grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=8, pady=(0, 4))

        # ── Hızlı komutlar ───────────────────────────────────────────────────
        quick_frame = tk.Frame(self, bg=_BG)
        quick_frame.grid(row=4, column=0, sticky=tk.EW, padx=8, pady=(0, 8))

        tk.Label(quick_frame, text="Hızlı:", bg=_BG, fg=_FG3,
                 font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(0, 4))

        quick_cmds = [
            ("OCR Başlat", "Aktif sayfayı OCR et, Osmanlıca Arap harfli"),
            ("Düzelt", "Bu sayfadaki şüpheli okumaları analiz et ve düzelt"),
            ("Durum", "Projenin mevcut durumunu özetle"),
            ("Öğrendiklerin", "Kütüphanedeki eserleri listele"),
            ("Tüm Proje OCR", "Tüm sayfaları Claude ile OCR et, Osmanlıca mod"),
        ]
        for label, cmd in quick_cmds:
            btn = tk.Button(
                quick_frame, text=label, bg=_PANEL, fg=_FG2,
                font=("Segoe UI", 8), relief=tk.FLAT, cursor="hand2",
                padx=6, pady=2, activebackground=_ACC1, activeforeground="white",
                command=lambda c=cmd: self._quick_send(c),
            )
            btn.pack(side=tk.LEFT, padx=2)

        # Karşılama mesajı
        self._add_ai_message(
            "Merhaba! Metin Atölyesi asistanıyım. Osmanlıca el yazmaları "
            "konusunda uzmanım.\n\n"
            "Örnek komutlar:\n"
            "• \"Bu sayfayı Osmanlıca Nesih olarak OCR et\"\n"
            "• \"وزير kelimesi yanlış, vezîr olmalı — bunu kaydet\"\n"
            "• \"Tüm projedeki OCR hatalarını analiz et\"\n"
            "• \"El yazması ayarlarını Nesih, harekesiz, 16. yy olarak ayarla\"\n\n"
            "Ne yapmamı istersiniz?"
        )

    # -----------------------------------------------------------------------
    # Mesaj gösterimi
    # -----------------------------------------------------------------------

    def _add_message(self, text: str, bg: str, align: str,
                     prefix: str = "", fg: str = _FG) -> None:
        """Mesaj balonu ekle."""
        outer = tk.Frame(self._msg_inner, bg=_BG)
        outer.pack(fill=tk.X, padx=8, pady=3, anchor=tk.E if align == "right" else tk.W)

        bubble = tk.Frame(outer, bg=bg,
                          highlightbackground="#d0d4e8", highlightthickness=1)
        bubble.pack(side=tk.RIGHT if align == "right" else tk.LEFT,
                    fill=tk.NONE, expand=False)

        if prefix:
            tk.Label(bubble, text=prefix, bg=bg, fg=_FG3,
                     font=("Segoe UI", 8, "bold"), pady=2).pack(anchor=tk.W, padx=8, pady=(4, 0))

        lbl = tk.Label(
            bubble, text=text, bg=bg, fg=fg,
            font=("Segoe UI", 10), wraplength=550,
            justify=tk.LEFT, anchor=tk.NW,
            padx=10, pady=6,
        )
        lbl.pack(anchor=tk.NW)

        self._scroll_to_bottom()

    def _add_user_message(self, text: str) -> None:
        self._add_message(text, _USR_BG, "right", prefix="Sen")

    def _add_ai_message(self, text: str) -> None:
        self._add_message(text, _AI_BG, "left", prefix="🤖 Asistan")

    def _add_tool_message(self, tool_name: str, params: dict) -> None:
        tr = {
            "ocr_calistir": "🔍 OCR başlatılıyor",
            "metin_guncelle": "✏️ Metin güncelleniyor",
            "metin_al": "📄 Metin okunuyor",
            "bul_degistir": "🔄 Bul-değiştir",
            "duzeltme_ekle": "💾 Düzeltme kaydediliyor",
            "duzeltmeleri_listele": "📋 Düzeltmeler listeleniyor",
            "kutuphane_ara": "📚 Kütüphane aranıyor",
            "kutuphane_listele": "📚 Kütüphane listeleniyor",
            "el_yazmasi_ayarla": "⚙️ El yazması ayarlanıyor",
            "ocr_ayarla": "⚙️ OCR ayarlanıyor",
            "sayfa_git": "📄 Sayfaya gidiliyor",
            "pdf_ac": "📂 PDF açılıyor",
            "proje_kaydet": "💾 Proje kaydediliyor",
            "disa_aktar": "📤 Dışa aktarılıyor",
            "proje_durumu": "📊 Durum raporlanıyor",
            "metin_analiz": "🔬 Metin analiz ediliyor",
        }
        label = tr.get(tool_name, f"⚙️ {tool_name}")
        param_str = ", ".join(f"{k}={v}" for k, v in list(params.items())[:3])
        self._add_message(
            f"{label}…  ({param_str})",
            _TOOL_BG, "left", fg=_FG2,
        )

    def _add_error_message(self, text: str) -> None:
        self._add_message(f"❌ {text}", "#fff0f0", "left", fg=_ACC2)

    # -----------------------------------------------------------------------
    # Gönderme
    # -----------------------------------------------------------------------

    def _on_enter(self, event) -> str:
        if event.state & 0x1:   # Shift basılı → yeni satır
            return
        self._send()
        return "break"

    def _quick_send(self, cmd: str) -> None:
        self._input.delete("1.0", tk.END)
        self._input.insert("1.0", cmd)
        self._send()

    def _send(self) -> None:
        if self._busy:
            return
        text = self._input.get("1.0", tk.END).strip()
        if not text:
            return
        self._input.delete("1.0", tk.END)
        self._add_user_message(text)
        self._start_response(text)

    def _start_response(self, message: str) -> None:
        self._busy = True
        self._progress_var.set("⏳ Düşünüyor…")
        context = self._get_context()

        def _run():
            try:
                def _on_tool(name: str, params: dict) -> None:
                    self.after(0, lambda n=name, p=params: self._add_tool_message(n, p))
                    self.after(0, lambda n=name: self._progress_var.set(f"⚙️ {n} çalışıyor…"))

                response = self._assistant.chat(
                    message,
                    context=context,
                    on_tool_call=_on_tool,
                )
                self.after(0, lambda r=response: self._on_response(r))
            except Exception as exc:
                self.after(0, lambda e=exc: self._on_error(e))

        threading.Thread(target=_run, daemon=True).start()

    def _on_response(self, text: str) -> None:
        self._busy = False
        self._progress_var.set("")
        if text:
            self._add_ai_message(text)

    def _on_error(self, exc: Exception) -> None:
        self._busy = False
        self._progress_var.set("")
        self._add_error_message(str(exc))

    def _clear_history(self) -> None:
        self._assistant.reset()
        for widget in self._msg_inner.winfo_children():
            widget.destroy()
        self._add_ai_message("Konuşma sıfırlandı. Nasıl yardımcı olabilirim?")

    # -----------------------------------------------------------------------
    # Canvas scroll yardımcıları
    # -----------------------------------------------------------------------

    def _scroll_to_bottom(self) -> None:
        self.after(50, lambda: self._canvas.yview_moveto(1.0))

    def _on_inner_configure(self, _event=None) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self._canvas.itemconfig(self._canvas_window, width=event.width)

    def _on_wheel(self, event) -> None:
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
