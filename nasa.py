import io
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import requests
from PIL import Image as PILImage
from sqlalchemy import select

from config import IMAGES_DIR, MISSION_KEYWORDS, NASA_API_KEY
from db import Asteroid, Image, ImageTag, Mission, SessionLocal, Tag


STOP_WORDS = [
    "logo", "patch", "emblem", "insignia", "badge", "poster",
    "diagram", "chart", "map", "blueprint", "document", "newspaper",
    "article", "clipping", "signature", "autograph", "photo illustration"
]


def is_excluded_content(title: str | None, desc: str | None, keywords: list[str] | None) -> bool:
    text_parts = [title or "", desc or "", " ".join(keywords or [])]
    text = " ".join(text_parts).lower()
    for word in STOP_WORDS:
        if word in text:
            return True
    return False


def fetch_url(url: str, timeout: int = 15) -> bytes | None:
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.content
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
        except requests.RequestException:
            time.sleep(1)
    return None


def fetch_json(url: str, timeout: int = 15) -> dict | list | None:
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
        except requests.RequestException:
            time.sleep(1)
    return None


def pick_image_url(files: list[str]) -> str | None:
    valid = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    if not valid:
        return None
    for suffix in ["~medium", "~small", "~large", "~orig"]:
        for f in valid:
            if suffix in f.split("/")[-1]:
                return f
    return valid[0]


def pick_video_url(files: list[str]) -> str | None:
    valid = [f for f in files if f.lower().endswith(".mp4")]
    if not valid:
        return None
    for f in valid:
        name = f.split("/")[-1]
        if re.search(r"~(mobile|small|medium)\.mp4$", name):
            return f
    for f in valid:
        name = f.split("/")[-1]
        if "~orig" not in name:
            return f
    return valid[0]


def make_thumbnail(img_bytes: bytes) -> bytes | None:
    try:
        img = PILImage.open(io.BytesIO(img_bytes))
        img.thumbnail((320, 320))
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return buf.getvalue()
    except Exception:
        return None


def detect_mission(title: str | None, desc: str | None, keywords: list[str] | None) -> str | None:
    text_parts = [title or "", desc or "", " ".join(keywords or [])]
    text = " ".join(text_parts).lower()
    for mission, words in MISSION_KEYWORDS.items():
        for w in words:
            if w in text:
                return mission
    return None


def get_or_create_mission(session, name: str) -> int | None:
    if not name:
        return None
    stmt = select(Mission).where(Mission.name == name)
    mission = session.execute(stmt).scalar_one_or_none()
    if not mission:
        mission = Mission(name=name)
        session.add(mission)
        session.flush()
    return mission.id


def get_or_create_tag(session, name: str) -> int | None:
    if not isinstance(name, str):
        return None
    name = name.strip().lower()
    if len(name) > 150:
        name = name[:150]
    if not name:
        return None
    stmt = select(Tag).where(Tag.name == name)
    tag = session.execute(stmt).scalar_one_or_none()
    if not tag:
        tag = Tag(name=name)
        session.add(tag)
        session.flush()
    return tag.id


def search_nasa(query: str, media_type: str, page_size: int = 100) -> list[dict]:
    url = f"https://images-api.nasa.gov/search?q={query}&media_type={media_type}&page_size={page_size}"
    data = fetch_json(url)
    if not data or not isinstance(data, dict):
        return []
    collection = data.get("collection", {})
    if not isinstance(collection, dict):
        return []
    items = collection.get("items", [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def get_asset_files(nasa_id: str) -> list[str]:
    url = f"https://images-api.nasa.gov/asset/{nasa_id}"
    data = fetch_json(url)
    if not data or not isinstance(data, dict):
        return []
    collection = data.get("collection", [])
    if not isinstance(collection, list):
        return []
    result = []
    for item in collection:
        if isinstance(item, dict) and item.get("href"):
            result.append(item["href"])
        elif isinstance(item, str):
            result.append(item)
    return result


def get_thumbnail_url(item: dict) -> str | None:
    if not isinstance(item, dict):
        return None
    links = item.get("links", [])
    if not isinstance(links, list):
        return None
    for link in links:
        if isinstance(link, dict) and link.get("render") == "image":
            return link.get("href")
    return None


def process_image_item(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    data_list = item.get("data", [])
    if not isinstance(data_list, list) or not data_list:
        return None
    data = data_list[0]
    if not isinstance(data, dict):
        return None

    nasa_id = data.get("nasa_id")
    if not nasa_id:
        return None

    thumb_url = get_thumbnail_url(item)
    thumb_bytes = b""
    if thumb_url:
        thumb_bytes = fetch_url(thumb_url) or b""

    files = get_asset_files(nasa_id)
    file_url = pick_image_url(files)

    file_bytes = None
    file_path = None
    file_size = None
    if file_url:
        file_bytes = fetch_url(file_url)
        if file_bytes:
            ext = ".png" if file_url.lower().endswith(".png") else ".jpg"
            file_path = f"{nasa_id}{ext}"
            file_size = len(file_bytes)

    if not file_bytes and not thumb_bytes:
        return None

    if not thumb_bytes and file_bytes:
        thumb_bytes = make_thumbnail(file_bytes) or b""

    title = data.get("title", "Untitled")
    desc = data.get("description", "")

    keywords = data.get("keywords", [])
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]

    if is_excluded_content(title, desc, keywords):
        return None

    date_str = data.get("date_created")
    date_obj = None
    if date_str:
        try:
            date_obj = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            pass

    credit = data.get("photographer") or data.get("center") or data.get("secondary_creator")
    mission_name = detect_mission(title, desc, keywords)

    return {
        "nasa_id": nasa_id,
        "media_type": "image",
        "title": title,
        "description": desc,
        "keywords": keywords,
        "date_created": date_obj,
        "credit": credit,
        "mission_name": mission_name,
        "file_path": file_path,
        "file_size": file_size,
        "file_bytes": file_bytes,
        "thumbnail": thumb_bytes,
    }


def process_video_item(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    data_list = item.get("data", [])
    if not isinstance(data_list, list) or not data_list:
        return None
    data = data_list[0]
    if not isinstance(data, dict):
        return None

    nasa_id = data.get("nasa_id")
    if not nasa_id:
        return None

    thumb_url = get_thumbnail_url(item)
    thumb_bytes = b""
    if thumb_url:
        thumb_bytes = fetch_url(thumb_url) or b""

    files = get_asset_files(nasa_id)
    video_url = pick_video_url(files) or "unavailable"

    title = data.get("title", "Untitled")
    desc = data.get("description", "")

    keywords = data.get("keywords", [])
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]

    if is_excluded_content(title, desc, keywords):
        return None

    date_str = data.get("date_created")
    date_obj = None
    if date_str:
        try:
            date_obj = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            pass

    credit = data.get("photographer") or data.get("center") or data.get("secondary_creator")
    mission_name = detect_mission(title, desc, keywords)

    return {
        "nasa_id": nasa_id,
        "media_type": "video",
        "title": title,
        "description": desc,
        "keywords": keywords,
        "date_created": date_obj,
        "credit": credit,
        "mission_name": mission_name,
        "file_path": None,
        "file_size": None,
        "file_bytes": None,
        "thumbnail": thumb_bytes,
        "video_url": video_url,
    }


def save_to_db(item: dict) -> None:
    with SessionLocal() as session:
        stmt = select(Image).where(Image.nasa_id == item["nasa_id"])
        existing = session.execute(stmt).scalar_one_or_none()
        if existing:
            return

        mission_id = get_or_create_mission(session, item.get("mission_name"))

        file_bytes = item.get("file_bytes")
        file_path = item.get("file_path")
        if file_bytes and file_path:
            dest = IMAGES_DIR / file_path
            dest.write_bytes(file_bytes)

        image = Image(
            nasa_id=item["nasa_id"],
            media_type=item["media_type"],
            title=item["title"],
            description=item.get("description"),
            date_created=item.get("date_created"),
            credit=item.get("credit"),
            mission_id=mission_id,
            file_path=file_path,
            file_size=item.get("file_size"),
            thumbnail=item.get("thumbnail"),
            video_url=item.get("video_url"),
        )
        session.add(image)
        session.flush()

        added_tag_ids = set()
        for kw in item.get("keywords", []):
            if isinstance(kw, str):
                tag_id = get_or_create_tag(session, kw)
                if tag_id and tag_id not in added_tag_ids:
                    session.add(ImageTag(image_id=image.id, tag_id=tag_id))
                    added_tag_ids.add(tag_id)

        session.commit()


def import_search_results(query: str, media_type: str, count: int = 20) -> None:
    items = search_nasa(query, media_type, page_size=count)

    def process(item: dict) -> dict | None:
        if media_type == "image":
            return process_image_item(item)
        return process_video_item(item)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(process, item): item for item in items}
        for future in as_completed(futures):
            result = future.result()
            if result:
                save_to_db(result)


def process_apod(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    date_str = item.get("date")
    if not date_str:
        return None
    nasa_id = f"apod-{date_str}"
    media_type = item.get("media_type", "image")

    if media_type == "video":
        video_url = item.get("url")
        thumb_url = item.get("thumbnail_url")
        thumb_bytes = fetch_url(thumb_url) if thumb_url else b""
        return {
            "nasa_id": nasa_id,
            "media_type": "video",
            "title": item.get("title", "APOD"),
            "description": item.get("explanation", ""),
            "keywords": ["apod"],
            "date_created": datetime.strptime(date_str, "%Y-%m-%d"),
            "credit": item.get("copyright") or "NASA APOD",
            "mission_name": None,
            "file_path": None,
            "file_size": None,
            "file_bytes": None,
            "thumbnail": thumb_bytes,
            "video_url": video_url,
        }

    img_url = item.get("url")
    img_bytes = fetch_url(img_url) if img_url else None
    if not img_bytes:
        return None
    thumb_bytes = make_thumbnail(img_bytes) or b""
    file_path = f"{nasa_id}.jpg"
    return {
        "nasa_id": nasa_id,
        "media_type": "image",
        "title": item.get("title", "APOD"),
        "description": item.get("explanation", ""),
        "keywords": ["apod"],
        "date_created": datetime.strptime(date_str, "%Y-%m-%d"),
        "credit": item.get("copyright") or "NASA APOD",
        "mission_name": None,
        "file_path": file_path,
        "file_size": len(img_bytes),
        "file_bytes": img_bytes,
        "thumbnail": thumb_bytes,
    }


def import_apod_range(days: int = 14) -> None:
    if not NASA_API_KEY:
        return
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days - 1)
    url = (
        f"https://api.nasa.gov/planetary/apod?api_key={NASA_API_KEY}"
        f"&start_date={start_date.strftime('%Y-%m-%d')}"
        f"&end_date={end_date.strftime('%Y-%m-%d')}&thumbs=true"
    )
    data = fetch_json(url)
    if not data or not isinstance(data, list):
        return

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(process_apod, item): item for item in data if isinstance(item, dict)}
        for future in as_completed(futures):
            result = future.result()
            if result:
                save_to_db(result)


def process_asteroid(obj: dict, date_key: str) -> None:
    if not isinstance(obj, dict):
        return

    neo_id = obj.get("id")
    name = obj.get("name")

    est_diam_dict = obj.get("estimated_diameter", {})
    if not isinstance(est_diam_dict, dict):
        est_diam_dict = {}
    meters_dict = est_diam_dict.get("meters", {})
    if not isinstance(meters_dict, dict):
        meters_dict = {}
    est_diam = meters_dict.get("estimated_diameter_max")

    is_hazardous = obj.get("is_potentially_hazardous_asteroid", False)

    approach_data = obj.get("close_approach_data", [])
    if not isinstance(approach_data, list):
        return

    for approach in approach_data:
        if not isinstance(approach, dict):
            continue
        if approach.get("close_approach_date") == date_key:
            vel_dict = approach.get("relative_velocity", {})
            if not isinstance(vel_dict, dict):
                vel_dict = {}
            miss_dict = approach.get("miss_distance", {})
            if not isinstance(miss_dict, dict):
                miss_dict = {}

            vel_str = vel_dict.get("kilometers_per_second")
            miss_str = miss_dict.get("kilometers")

            vel = float(vel_str) if vel_str else 0.0
            miss = float(miss_str) if miss_str else 0.0

            with SessionLocal() as session:
                stmt = select(Asteroid).where(
                    Asteroid.neo_id == neo_id,
                    Asteroid.approach_date == datetime.strptime(date_key, "%Y-%m-%d"),
                )
                existing = session.execute(stmt).scalar_one_or_none()
                if existing:
                    continue

                asteroid = Asteroid(
                    neo_id=neo_id,
                    name=name,
                    diameter_max_m=est_diam,
                    is_hazardous=is_hazardous,
                    approach_date=datetime.strptime(date_key, "%Y-%m-%d"),
                    velocity_kms=vel,
                    miss_distance_km=miss,
                )
                session.add(asteroid)
                try:
                    session.commit()
                except Exception:
                    session.rollback()


def import_neows_range(days: int = 14, start_date: datetime | None = None, end_date: datetime | None = None) -> None:
    if not NASA_API_KEY:
        return

    if start_date is None or end_date is None:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days - 1)

    current = start_date
    while current <= end_date:
        window_end = min(current + timedelta(days=6), end_date)
        url = (
            f"https://api.nasa.gov/neo/rest/v1/feed?"
            f"start_date={current.strftime('%Y-%m-%d')}"
            f"&end_date={window_end.strftime('%Y-%m-%d')}"
            f"&api_key={NASA_API_KEY}"
        )
        data = fetch_json(url)

        if data and isinstance(data, dict) and "near_earth_objects" in data:
            neos = data.get("near_earth_objects", {})
            if isinstance(neos, dict):
                for date_key, objects in neos.items():
                    if isinstance(objects, list):
                        for obj in objects:
                            if isinstance(obj, dict):
                                process_asteroid(obj, date_key)

        current = window_end + timedelta(days=1)