import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

NASA_API_KEY = os.getenv("NASA_API_KEY", "") or "x2T10KJ5od2qRSiod1yLTWThX9fSe8tfMOZLX5Nb"

DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
IMAGES_DIR = DATA_DIR / "images"
DB_PATH = BASE_DIR / "spacevault.db"
QSS_PATH = BASE_DIR / "style.qss"

IMAGES_DIR.mkdir(parents=True, exist_ok=True)

MISSION_KEYWORDS = {
    "Hubble": ["hubble"],
    "JWST": ["webb", "jwst", "james webb"],
    "Apollo": ["apollo"],
    "Mars": ["mars", "perseverance", "curiosity", "opportunity", "spirit"],
    "ISS": ["international space station", "iss"],
}