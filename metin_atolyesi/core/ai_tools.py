from __future__ import annotations

import subprocess

from .dependencies import command_available


def local_ai_available() -> bool:
    return command_available("ollama")


def run_local_ai(command: str, text: str, examples: str = "", model: str = "llama3.1") -> str:
    if not local_ai_available():
        return "Yerel yapay zeka hazir degil. Ollama kuruldugunda bu komut calisir."
    prompt = (
        "Transkripsiyon isaretlerini kesinlikle koru. "
        "Supheli okumalari [SUPHELI: ...] biciminde belirt.\n\n"
        f"Referans okuma bilgileri:\n{examples}\n\n"
        f"Kullanici komutu:\n{command}\n\n"
        f"Metin:\n{text}"
    )
    completed = subprocess.run(
        ["ollama", "run", model, prompt],
        check=False,
        text=True,
        capture_output=True,
        timeout=180,
    )
    if completed.returncode != 0:
        return completed.stderr.strip() or "Yerel yapay zeka komutu tamamlanamadi."
    return completed.stdout.strip()
