"""Transkribus HTR (Handwritten Text Recognition) entegrasyonu.

Transkribus; Avusturya Ulusal Kütüphanesi, Devlet Arşivleri ve yüzlerce
akademik konsorsiyum tarafından Osmanlıca el yazmaları için standart
platform olarak kullanılmaktadır. CNN/LSTM tabanlı derin öğrenme (HTR+)
motoru, özellikle sağdan-sola Arap hatlı metinlerde ve ligatür analizinde
Tesseract ve benzeri motorlara göre belirgin üstünlük sağlar.

Entegrasyon:
  • Transkribus EU REST API  (classic, kararlı)
  • Her sayfa işlemi kredi tüketir; ücretsiz hesap yaklaşık 500 kredi ile başlar
  • Hesap: https://app.transkribus.ai
  • Özel model eğitimi için 50-100 sayfalık Ground Truth yeterlidir

Yapılandırma (Metin Atölyesi → Dosya → Transkribus Ayarları):
  • E-posta ve şifre
  • HTR Model ID (Osmanlıca için varsayılan sağlanmıştır)
"""
from __future__ import annotations

import json
import time
from pathlib import Path

# Kimlik bilgisi ve oturum önbelleği
_config_path = Path.home() / ".metin_atolyesi_config.json"
_session_id: str = ""
_session_expires: float = 0.0
_user_id: int = 0        # login'den gelen userId
_user_name: str = ""     # login'den gelen isim

# Transkribus API taban URL'i
_BASE = "https://transkribus.eu/TrpServer/rest"

# Varsayılan Osmanlıca HTR modelleri (Transkribus model ID'leri)
# Kullanıcı kendi modelini de girebilir.
OTTOMAN_MODELS: dict[str, int] = {
    "Osmanlı Genel (önerilen)":    48454,   # Ottoman Turkish General HTR+
    "Osmanlıca Nesih":             39995,   # Nesih hattı için eğitilmiş
    "Osmanlı Arşiv (Divani)":      44000,   # Divani ve resmi belgeler
    "Arapça / Mağribî":            38763,   # Arapça el yazmaları
}
DEFAULT_MODEL_ID = 48454  # Ottoman Turkish General


# ---------------------------------------------------------------------------
# Yapılandırma
# ---------------------------------------------------------------------------

def get_config() -> dict:
    """~/.metin_atolyesi_config.json dosyasından Transkribus ayarlarını oku."""
    try:
        data = json.loads(_config_path.read_text(encoding="utf-8"))
        return {
            "email":    data.get("transkribus_email", ""),
            "password": data.get("transkribus_password", ""),
            "model_id": int(data.get("transkribus_model_id", DEFAULT_MODEL_ID)),
        }
    except Exception:
        return {"email": "", "password": "", "model_id": DEFAULT_MODEL_ID}


def save_config(email: str, password: str, model_id: int = DEFAULT_MODEL_ID) -> None:
    """Transkribus kimlik bilgilerini config dosyasına yaz."""
    try:
        existing: dict = {}
        if _config_path.exists():
            try:
                existing = json.loads(_config_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        existing["transkribus_email"]    = email.strip()
        existing["transkribus_password"] = password.strip()
        existing["transkribus_model_id"] = model_id
        _config_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def credentials_set() -> bool:
    cfg = get_config()
    return bool(cfg["email"] and cfg["password"])


# ---------------------------------------------------------------------------
# Oturum yönetimi
# ---------------------------------------------------------------------------

def _login(email: str, password: str) -> str:
    """Transkribus'a giriş yap, oturum ID'si döndür."""
    import requests

    global _session_id, _session_expires, _user_id, _user_name
    resp = requests.post(
        f"{_BASE}/auth/login",
        data={"user": email, "pw": password},
        headers={"Accept": "application/json"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Transkribus giris hatasi ({resp.status_code}): "
            f"E-posta/sifre kontrol edin."
        )
    data = resp.json()
    _session_id = data.get("sessionId", "")
    if not _session_id:
        raise RuntimeError("Transkribus: oturum ID'si alinamadi.")
    _session_expires = time.time() + 3500  # ~58 dakika
    _user_id   = int(data.get("userId", 0))
    _user_name = (data.get("firstname", "") + " " + data.get("lastname", "")).strip()
    return _session_id


def _get_session() -> str:
    """Geçerli oturum ID'si döndür; gerekirse yeniden giriş yap."""
    global _session_id, _session_expires
    if _session_id and time.time() < _session_expires:
        return _session_id
    cfg = get_config()
    if not cfg["email"] or not cfg["password"]:
        raise ValueError(
            "Transkribus kimlik bilgileri yapılandırılmamış.\n"
            "Dosya → Transkribus Ayarları menüsünden e-posta ve şifrenizi girin."
        )
    return _login(cfg["email"], cfg["password"])


def _headers(session_id: str) -> dict:
    """Temel başlıklar — Content-Type YOK (multipart upload bozmasın)."""
    return {
        "Cookie": f"JSESSIONID={session_id}",
        "Accept": "application/json",
    }


def _json_headers(session_id: str) -> dict:
    """JSON body gönderimler için Content-Type ekli başlıklar."""
    return {**_headers(session_id), "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Görüntü OCR pipeline
# ---------------------------------------------------------------------------

def ocr_with_transkribus(
    path: Path,
    lang_hint: str = "ara",
    manuscript_meta: dict | None = None,
    model_id: int | None = None,
    timeout: int = 120,
) -> tuple[str, list[dict]]:
    """Transkribus HTR API ile tek sayfa OCR.

    DURUM: Transkribus'un yeni Processing API'si (processing/v1/) yalnızca
    Keycloak JWT token kabul ediyor. Ancak auth servisi
    (account.transkribus.eu) DNS çözümlenemiyor — bu ağdan erişilemiyor.

    Çalışan alternatifler:
      • Claude API (claude ⚡) — Osmanlıca için en iyi kalite
      • Web arayüzü: https://app.transkribus.ai
    """
    import requests
    from .text_tools import find_suspicious_words, find_uncertain_words

    session = _get_session()
    hdrs_json = _json_headers(session)   # JSON body için (Content-Type: application/json)
    hdrs_bare = _headers(session)        # GET/multipart için (Content-Type YOK)
    cfg     = get_config()
    mid     = model_id or cfg["model_id"] or DEFAULT_MODEL_ID

    # ── 1. Kullanılabilir koleksiyonu bul / oluştur ───────────────────────
    r = requests.get(f"{_BASE}/collections", headers=hdrs_bare, timeout=15)
    r.raise_for_status()
    cols = r.json().get("trpCollection", [])
    col_id = None
    for c in cols:
        if "metin" in c.get("colName", "").lower():
            col_id = c["colId"]
            break
    if col_id is None and cols:
        col_id = cols[0]["colId"]  # ilk koleksiyonu kullan
    if col_id is None:
        raise RuntimeError("Transkribus'ta erişilebilir koleksiyon bulunamadı.")

    doc_id = None
    try:
        # ── 2. Upload slot oluştur ───────────────────────────────────────
        upload_meta = {
            "md": {"title": f"metin-atolyesi-{path.stem}"},
            "pageList": {"pages": [{"fileName": path.name, "pageNr": 1}]},
        }
        r = requests.post(
            f"{_BASE}/uploads",
            params={"collId": col_id},
            json=upload_meta,
            headers=hdrs_json,
            timeout=20,
        )
        r.raise_for_status()
        upload_id = r.json()["uploadId"]

        # ── 3. Görüntüyü yükle (multipart/form-data) ────────────────────
        r = requests.put(
            f"{_BASE}/uploads/{upload_id}",
            files={"img": (path.name, path.read_bytes(),
                           "image/png" if path.suffix.lower() == ".png" else "image/jpeg")},
            headers=hdrs_bare,
            timeout=60,
        )
        r.raise_for_status()
        doc_id = upload_id  # Transkribus uploadId == docId

        # Yükleme işleminin tamamlanmasını bekle
        for _ in range(10):
            time.sleep(2)
            r = requests.get(
                f"{_BASE}/collections/{col_id}/list",
                headers=hdrs_bare, timeout=15,
            )
            if r.ok:
                docs = [d for d in r.json() if d.get("docId") == doc_id]
                if docs:
                    break

        # ── 4. HTR işini başlat ──────────────────────────────────────────
        htr_payload = {
            "docList": {
                "docs": [{"docId": doc_id, "pageList": {"pages": [{"pageNr": 1}]}}]
            },
            "modelId": mid,
        }
        r = requests.post(
            f"{_BASE}/jobs/htrCITlab",
            json=htr_payload,
            headers=hdrs_json,
            timeout=30,
        )

        # 500 hatası: model erişimi yok (yeni ücretsiz hesaplar için yaygın)
        if r.status_code == 500:
            raise RuntimeError(
                "Transkribus HTR motoru bu hesap için erişilebilir değil.\n\n"
                "Olası nedenler:\n"
                "  • Ücretsiz hesaplarda API üzerinden HTR sınırlıdır\n"
                "  • Model ID mevcut değil (farklı bir model deneyin)\n\n"
                "Çözüm: Web arayüzünü kullanın →\n"
                "  https://transkribus.eu/r/read/login\n"
                "veya Claude API motoruna geçin."
            )
        r.raise_for_status()
        job_id = r.json().get("jobId") or r.json().get("id")

        # ── 5. İş tamamlanana kadar bekle ────────────────────────────────
        deadline = time.time() + timeout
        status   = ""
        while time.time() < deadline:
            time.sleep(3)
            r = requests.get(f"{_BASE}/jobs/{job_id}", headers=hdrs_bare, timeout=15)
            if r.ok:
                status = r.json().get("state", "")
                if status in ("FINISHED", "FAILED", "CANCELED"):
                    break

        if status != "FINISHED":
            raise RuntimeError(
                f"Transkribus HTR tamamlanamadi (durum: {status})."
            )

        # ── 6. Transkripsiyonu al ────────────────────────────────────────
        r = requests.get(
            f"{_BASE}/collections/{col_id}/documents/{doc_id}/pages/1/transcripts",
            headers=hdrs_bare, timeout=20,
        )
        r.raise_for_status()
        text = _extract_text_from_transcript(r.json())

    finally:
        # ── 7. Geçici belgeyi sil (koleksiyon korunur) ───────────────────
        if doc_id:
            try:
                requests.delete(
                    f"{_BASE}/collections/{col_id}/documents/{doc_id}",
                    headers=hdrs_bare, timeout=10,
                )
            except Exception:
                pass

    text = text.strip()
    suspicious = find_suspicious_words(text) + find_uncertain_words(text)
    return text, suspicious


def _extract_text_from_transcript(transcripts: list | dict) -> str:
    """Transkribus transkript JSON'undan düz metni çıkarır."""
    if isinstance(transcripts, list):
        # En yeni transkripti al
        if not transcripts:
            return ""
        ts = transcripts[0]
    else:
        ts = transcripts

    # PAGE XML veya JSON transkript
    # Önce JSON yapısını dene
    try:
        regions = ts.get("tpRegions", {}).get("tpRegions", [])
        lines: list[str] = []
        for region in regions:
            for line in region.get("tpLines", []):
                words = [
                    w.get("transcription", {}).get("textEquiv", "")
                    for w in line.get("tpWords", [])
                ]
                line_text = " ".join(w for w in words if w).strip()
                if line_text:
                    lines.append(line_text)
        if lines:
            return "\n".join(lines)
    except Exception:
        pass

    # PAGE XML yedek
    xml = ts.get("pageXmlUrl", "") or ts.get("url", "")
    if xml:
        try:
            import requests, re
            r = requests.get(xml, timeout=15)
            # Unicode string'den TextEquiv içeriğini çek
            matches = re.findall(r"<Unicode>(.*?)</Unicode>", r.text, re.DOTALL)
            return "\n".join(m.strip() for m in matches if m.strip())
        except Exception:
            pass

    # Düz metin alanı
    return ts.get("text", "") or ts.get("textResult", "")


# ---------------------------------------------------------------------------
# Kullanıcı kredi sorgulama
# ---------------------------------------------------------------------------

def get_credit_info() -> str:
    """Kalan HTR kredi miktarini sorgular (/credits endpoint)."""
    try:
        import requests
        session = _get_session()
        r = requests.get(
            f"{_BASE}/credits",
            headers=_headers(session),
            timeout=15,
        )
        if r.ok:
            data   = r.json()
            bal    = data.get("overallBalance", "?")
            pkgs   = data.get("trpCreditPackage", [])
            if pkgs:
                exp = pkgs[0].get("expirationDate", "")[:10]
                return f"Kalan kredi: {bal:.0f}  (son kullanim: {exp})"
            return f"Kalan kredi: {bal}"
        return f"Kredi bilgisi alinamadi ({r.status_code})."
    except Exception as e:
        return f"Kredi sorgulanamiyor: {e}"


def get_user_info() -> dict:
    """Oturum acik kullanicinin temel bilgilerini dondurur."""
    try:
        import requests
        session = _get_session()
        r = requests.get(
            f"{_BASE}/user/{_user_id}",
            headers=_headers(session),
            timeout=15,
        )
        if r.ok:
            return r.json()
    except Exception:
        pass
    return {}
