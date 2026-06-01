"""PyInstaller giriş noktası — MetinAtolyesi.exe"""
import sys
from pathlib import Path

# Dondurulmuş (frozen) exe modunda sistem yolu ayarla
if getattr(sys, "frozen", False):
    _base = Path(sys.executable).parent
    sys.path.insert(0, str(_base))

from metin_atolyesi.app import main

if __name__ == "__main__":
    main()
