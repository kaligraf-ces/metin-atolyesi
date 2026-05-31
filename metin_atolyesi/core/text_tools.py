from __future__ import annotations

import re
from .models import TRANSCRIPTION_CHARS, VocabularyItem


SUSPICIOUS_PATTERN = re.compile(r"[�□]|[A-Za-zÇĞİÖŞÜçğıöşü]?\?+")
HEADWORD_SPLIT_PATTERN = re.compile(r"\s*(?::|;|\t| - | – )\s*")


def preserve_transcription(text: str) -> str:
    # Keep combining marks and Ottoman/Turkological transcription signs intact.
    return text.replace("\r\n", "\n").replace("\r", "\n")


def find_suspicious_words(text: str) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for match in re.finditer(r"\S+", text):
        word = match.group(0)
        if SUSPICIOUS_PATTERN.search(word) or len([c for c in word if c == "."]) > 2:
            found.append({"word": word, "start": match.start(), "end": match.end(), "confidence": 0.3})
    return found


def find_uncertain_words(text: str) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    likely_confusions = re.compile(r"[|]{1}|rn|vv|0|1|lI|[A-Za-zÇĞİÖŞÜçğıöşüāīūḳġḥṣṭẓñʿʾ]{18,}")
    for match in re.finditer(r"\S+", text):
        word = match.group(0)
        if SUSPICIOUS_PATTERN.search(word):
            continue
        if likely_confusions.search(word):
            found.append({"word": word, "start": match.start(), "end": match.end(), "confidence": 0.65, "level": "uncertain"})
    return found


def extract_vocabulary(text: str, location: str = "") -> list[VocabularyItem]:
    items: list[VocabularyItem] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = HEADWORD_SPLIT_PATTERN.split(line, maxsplit=1)
        if len(parts) == 2 and 1 < len(parts[0]) < 80:
            headword = parts[0].strip()
            rest = parts[1].strip()
            origin = ""
            origin_match = re.search(r"\b(Ar\.|Far\.|T\.|Yun\.|Arapça|Farsça|Türkçe)\b", rest, re.I)
            if origin_match:
                origin = origin_match.group(0)
            items.append(VocabularyItem(headword=headword, origin=origin, meaning=rest, location=location))
    return items


def extract_suffix_candidates(text: str) -> list[str]:
    candidates = set()
    for token in re.findall(r"(?:\+|-)[A-Za-zÇĞİÖŞÜçğıöşüāīūḳġḥṣṭẓñʿʾ]+", text):
        candidates.add(token)
    return sorted(candidates)


def apply_command(text: str, command: str) -> tuple[str, list[VocabularyItem], str]:
    cmd = command.lower()
    items: list[VocabularyItem] = []
    report = "Komut yorumlandi."
    if "madde" in cmd or "baş" in cmd or "bas" in cmd:
        items = extract_vocabulary(text)
        if "sadece" in cmd:
            output = "\n".join(item.headword for item in items)
        else:
            output = "\n".join(
                f"{item.headword}\t{item.origin}\t{item.meaning}" for item in items
            )
        return output, items, f"{len(items)} madde adayi bulundu."
    if "ek" in cmd:
        suffixes = extract_suffix_candidates(text)
        return "\n".join(suffixes), [], f"{len(suffixes)} ek adayi bulundu."
    if "şüpheli" in cmd or "supheli" in cmd or "emin" in cmd:
        suspicious = find_suspicious_words(text)
        words = "\n".join(item["word"] for item in suspicious)
        return words, [], f"{len(suspicious)} supheli okuma adayi bulundu."
    return text, [], report
