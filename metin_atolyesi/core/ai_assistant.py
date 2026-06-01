"""Metin Atölyesi — Dahili Yapay Zeka Asistanı.

Claude API tool_use ile programı doğal dil komutlarıyla yönetir.
Osmanlıca bağlam, el yazması kütüphanesi ve düzeltmeler sürekli öğrenilir.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Callable, Any

# ---------------------------------------------------------------------------
# Araç tanımları — Claude'un kullanabileceği tüm program işlevleri
# ---------------------------------------------------------------------------

TOOLS: list[dict] = [
    {
        "name": "ocr_calistir",
        "description": (
            "OCR işlemini başlatır. Sayfaları metne dönüştürür. "
            "Belirtilmezse tüm sayfalarda çalışır."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sayfalar": {
                    "type": "string",
                    "description": "Hangi sayfalar: 'tumu', 'aktif', '1-5', '3,7,9'",
                },
                "motor": {
                    "type": "string",
                    "description": "OCR motoru: otomatik/tesseract/windows/easyocr/claude",
                },
                "dil": {
                    "type": "string",
                    "description": "Dil kodu: ara/tur/tur+ara/eng",
                },
            },
        },
    },
    {
        "name": "metin_al",
        "description": "Aktif sayfanın veya belirtilen sayfanın OCR metnini döndürür.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sayfa": {"type": "integer", "description": "Sayfa numarası (1'den başlar). Boşsa aktif sayfa."},
                "tum_proje": {"type": "boolean", "description": "True ise tüm proje metni"},
            },
        },
    },
    {
        "name": "metin_guncelle",
        "description": "Aktif sayfanın veya belirtilen sayfanın OCR metnini günceller/düzeltir.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metin": {"type": "string", "description": "Yeni/düzeltilmiş metin"},
                "sayfa": {"type": "integer", "description": "Sayfa numarası. Boşsa aktif sayfa."},
            },
            "required": ["metin"],
        },
    },
    {
        "name": "bul_degistir",
        "description": (
            "Metinde kelime veya ifade bulup değiştirir. "
            "Tüm sayfalarda veya sadece aktif sayfada yapılabilir."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "aranan": {"type": "string"},
                "yeni": {"type": "string"},
                "tum_proje": {"type": "boolean", "description": "Tüm sayfalarda mı? Varsayılan: aktif sayfa"},
                "regex": {"type": "boolean", "description": "Regex deseni kullan"},
            },
            "required": ["aranan", "yeni"],
        },
    },
    {
        "name": "duzeltme_ekle",
        "description": (
            "OCR düzeltmesi ekler: yanlış okunan → doğru yazım. "
            "Kalıcıdır, gelecek OCR işlemlerinde otomatik uygulanır."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "yanlis": {"type": "string", "description": "Yanlış okunan metin"},
                "dogru": {"type": "string", "description": "Doğru yazım"},
                "kapsam": {
                    "type": "string",
                    "enum": ["global", "proje"],
                    "description": "global=tüm projeler, proje=sadece bu proje",
                },
            },
            "required": ["yanlis", "dogru"],
        },
    },
    {
        "name": "duzeltmeleri_listele",
        "description": "Kayıtlı OCR düzeltmelerini listeler.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filtre": {"type": "string", "description": "Arama filtresi"},
            },
        },
    },
    {
        "name": "kutuphane_ara",
        "description": "El yazması kütüphanesinde kelime veya eser arar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sorgu": {"type": "string"},
            },
            "required": ["sorgu"],
        },
    },
    {
        "name": "kutuphane_listele",
        "description": "Öğrenilmiş el yazması eserlerini listeler.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "el_yazmasi_ayarla",
        "description": "El yazması meta verilerini ayarlar. OCR kalitesini artırır.",
        "input_schema": {
            "type": "object",
            "properties": {
                "eser_adi":   {"type": "string"},
                "yazi_turu":  {"type": "string", "description": "Nesih/Talik/Sulus/Divani..."},
                "hareke":     {"type": "string", "description": "Harekesiz/Tam harekeli/Kısmen harekeli"},
                "donem":      {"type": "string", "description": "Osmanlı dönemi"},
                "alan":       {"type": "string", "description": "Osmanlıca/Arapça/Farsça..."},
                "mod":        {"type": "string", "enum": ["el_yazmasi", "normal"], "description": "Belge türü"},
            },
        },
    },
    {
        "name": "ocr_ayarla",
        "description": "OCR motor, dil veya ön işleme ayarını değiştirir.",
        "input_schema": {
            "type": "object",
            "properties": {
                "motor":      {"type": "string", "description": "otomatik/tesseract/windows/easyocr/claude/surya"},
                "dil":        {"type": "string", "description": "ara/tur/tur+ara/eng/..."},
                "on_islem":   {"type": "string", "description": "coklu deneme/adaptif/zorlu/dengeli/temiz"},
                "guven":      {"type": "boolean"},
                "deskew":     {"type": "boolean"},
            },
        },
    },
    {
        "name": "sayfa_git",
        "description": "Belirtilen sayfaya gider.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sayfa": {"type": "integer", "description": "Sayfa numarası (1'den başlar)"},
            },
            "required": ["sayfa"],
        },
    },
    {
        "name": "pdf_ac",
        "description": "PDF dosyası açar. Yol belirtilmezse dosya seçici açılır.",
        "input_schema": {
            "type": "object",
            "properties": {
                "yol": {"type": "string", "description": "Dosya yolu. Boşsa dialog açılır."},
            },
        },
    },
    {
        "name": "proje_kaydet",
        "description": "Mevcut projeyi kaydeder.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "disa_aktar",
        "description": "Metni dışa aktarır (Word/TXT/PDF).",
        "input_schema": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["word", "txt", "pdf"],
                },
                "yol": {"type": "string", "description": "Kayıt yolu. Boşsa dialog açılır."},
            },
            "required": ["format"],
        },
    },
    {
        "name": "proje_durumu",
        "description": "Projenin mevcut durumunu raporlar: sayfa sayısı, OCR durumu, ayarlar.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "metin_analiz",
        "description": (
            "Osmanlıca/Arapça metni analiz eder: şüpheli okumalar, kelime sıklığı, "
            "düzeltme önerileri. Claude OCR motoru ile en iyi sonuç."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metin": {"type": "string", "description": "Analiz edilecek metin. Boşsa aktif sayfa"},
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Sistem promptu
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
Sen Metin Atölyesi'nin dahili yapay zeka asistanısın. Osmanlıca, Arapça ve \
tarihi Türkçe el yazmaları konusunda uzman bir asistan ve editörsün.

Görevin:
- Kullanıcının doğal dil komutlarını anlayıp uygun program araçlarını çalıştırmak
- OCR hatalarını tanıyıp düzeltmek ve bu düzeltmeleri kaydetmek
- Osmanlıca metinlerin bağlamını, dilbilgisini ve anlamını gözetmek
- El yazması kütüphanesinden öğrendiklerini aktif olarak kullanmak
- Her işlemden sonra ne yaptığını ve neden yaptığını açıklamak

Osmanlıca/Arapça OCR kuralları:
- Sağdan sola yazım, ligatürler, harekesiz okuma
- Bağlamdan kelime tamamlama (dini metinlerde kalıplar çoktur)
- Yaygın OCR hataları: vav↔elif, kef↔gaf, noktasız harfler
- Düzeltmeleri daima 'duzeltme_ekle' ile kaydet — öğrenme böyle olur

Kullanıcıya:
- Türkçe cevap ver
- Yaptığın işlemi kısaca açıkla
- Emin olmadığın okumalarda alternatif öner
- Öğrendiğin kalıpları belirt
"""


# ---------------------------------------------------------------------------
# AI Asistanı
# ---------------------------------------------------------------------------

class AIAssistant:
    """Claude API + tool_use ile program kontrolü."""

    def __init__(self) -> None:
        self._history: list[dict] = []
        self._lock = threading.Lock()

        # Araç çalıştırıcılar — ui/main_window tarafından bağlanır
        self.tool_handlers: dict[str, Callable[[dict], Any]] = {}

    def reset(self) -> None:
        """Konuşma geçmişini sıfırla."""
        with self._lock:
            self._history.clear()

    def _get_client(self):
        try:
            import anthropic
            from metin_atolyesi.core.claude_ocr import get_api_key, _default_model
            key = get_api_key()
            if not key:
                raise ValueError(
                    "Claude API anahtarı girilmemiş.\n"
                    "Dosya → ⚡ Claude API Ayarları menüsünden girin."
                )
            return anthropic.Anthropic(api_key=key), _default_model
        except ImportError:
            raise RuntimeError(
                "'anthropic' paketi kurulu değil.\n"
                "Terminal'de: pip install anthropic"
            )

    def chat(
        self,
        user_message: str,
        context: dict | None = None,
        on_tool_call: Callable[[str, dict], None] | None = None,
        on_partial: Callable[[str], None] | None = None,
    ) -> str:
        """Kullanıcı mesajını işle, araçları çalıştır, yanıt döndür.

        context : Mevcut program durumu (metin, sayfa, ayarlar vb.)
        on_tool_call : (araç_adı, parametreler) → UI feedback için
        on_partial : Kısmi metin gelince callback (streaming için)
        """
        client, model = self._get_client()

        # Bağlamı kullanıcı mesajına ekle
        if context:
            ctx_parts = []
            if context.get("aktif_sayfa_no") is not None:
                ctx_parts.append(f"Aktif sayfa: {context['aktif_sayfa_no'] + 1}")
            if context.get("toplam_sayfa"):
                ctx_parts.append(f"Toplam sayfa: {context['toplam_sayfa']}")
            if context.get("aktif_metin"):
                metin_ozet = context["aktif_metin"][:500]
                ctx_parts.append(f"Aktif sayfa metni (ilk 500 karakter):\n{metin_ozet}")
            if context.get("el_yazmasi_meta"):
                meta = context["el_yazmasi_meta"]
                if meta.get("eser_adi"):
                    ctx_parts.append(f"Eser: {meta['eser_adi']}")
                if meta.get("yazi_turu"):
                    ctx_parts.append(f"Yazı türü: {meta['yazi_turu']}")
            if context.get("motor"):
                ctx_parts.append(f"OCR motoru: {context['motor']}")
            if context.get("dil"):
                ctx_parts.append(f"Dil: {context['dil']}")

            if ctx_parts:
                user_message = (
                    "[Program durumu]\n" + "\n".join(ctx_parts) +
                    "\n\n[Komut]\n" + user_message
                )

        with self._lock:
            self._history.append({"role": "user", "content": user_message})

        # Claude'a gönder
        messages = list(self._history)
        final_response = ""

        # Tool_use döngüsü — Claude araç isteyebilir, biz çalıştırırız
        for _round in range(8):   # max 8 araç turu
            resp = client.messages.create(
                model=model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            # Yanıtı geçmişe ekle
            messages.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason == "end_turn":
                # Sadece metin içerik
                parts = [
                    blk.text for blk in resp.content
                    if hasattr(blk, "text")
                ]
                final_response = "\n".join(parts)
                break

            if resp.stop_reason == "tool_use":
                tool_results = []

                for blk in resp.content:
                    if blk.type != "tool_use":
                        continue

                    tool_name  = blk.name
                    tool_input = blk.input

                    if on_tool_call:
                        on_tool_call(tool_name, tool_input)

                    # Aracı çalıştır
                    try:
                        handler = self.tool_handlers.get(tool_name)
                        if handler:
                            result = handler(tool_input)
                            result_text = (
                                json.dumps(result, ensure_ascii=False)
                                if not isinstance(result, str)
                                else result
                            )
                        else:
                            result_text = f"Araç '{tool_name}' henüz bağlanmamış."
                    except Exception as exc:
                        result_text = f"Araç hatası ({tool_name}): {exc}"

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": blk.id,
                        "content": result_text,
                    })

                messages.append({"role": "user", "content": tool_results})
            else:
                # Bilinmeyen stop reason
                break

        # Konuşma geçmişini güncelle (sadece asistan yanıtını)
        with self._lock:
            # Kullanıcı mesajı zaten eklendi, asistan cevabını ekle
            self._history.append({
                "role": "assistant",
                "content": final_response or "(işlem tamamlandı)",
            })
            # Geçmiş çok uzarsa kırp (son 20 tur tut)
            if len(self._history) > 40:
                self._history = self._history[-40:]

        return final_response

    def get_history(self) -> list[dict]:
        with self._lock:
            return list(self._history)


# Singleton
_assistant: AIAssistant | None = None


def get_assistant() -> AIAssistant:
    global _assistant
    if _assistant is None:
        _assistant = AIAssistant()
    return _assistant
