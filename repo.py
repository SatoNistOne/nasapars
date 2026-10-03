from datetime import datetime
from sqlalchemy import select, func, desc, asc, or_
from sqlalchemy.orm import selectinload
from db import SessionLocal, Image, Tag, Mission, ImageTag, Collection, Asteroid
from config import IMAGES_DIR

def get_filters_data():
    with SessionLocal() as s:
        missions = s.execute(select(Mission).order_by(Mission.name)).scalars().all()
        tags = s.execute(select(Tag).order_by(Tag.name)).scalars().all()
        return missions, tags

def get_images(search="", sort="date_desc", mission_id=None, media_type=None,
               favorite_only=False, tag_id=None, date_from=None, date_to=None,
               offset=0, limit=60):
    with SessionLocal() as s:
        stmt = select(Image).options(selectinload(Image.mission))

        if search:
            search_pattern = f"%{search}%"
            stmt = stmt.outerjoin(ImageTag).outerjoin(Tag).where(
                or_(
                    Image.title.ilike(search_pattern),
                    Image.description.ilike(search_pattern),
                    Tag.name.ilike(search_pattern)
                )
            ).distinct()

        if mission_id:
            stmt = stmt.where(Image.mission_id == mission_id)
        if media_type:
            stmt = stmt.where(Image.media_type == media_type)
        if favorite_only:
            stmt = stmt.where(Image.is_favorite == True)
        if tag_id:
            stmt = stmt.join(ImageTag).where(ImageTag.tag_id == tag_id)
        if date_from:
            stmt = stmt.where(Image.date_created >= date_from)
        if date_to:
            stmt = stmt.where(Image.date_created <= date_to)

        if sort == "date_desc":
            stmt = stmt.order_by(desc(Image.date_created).nulls_last(), desc(Image.id))
        elif sort == "date_asc":
            stmt = stmt.order_by(asc(Image.date_created).nulls_last(), desc(Image.id))
        elif sort == "title":
            stmt = stmt.order_by(asc(Image.title).nulls_last(), desc(Image.id))
        elif sort == "rating":
            stmt = stmt.order_by(desc(Image.rating).nulls_last(), desc(Image.id))
        elif sort == "file_size":
            stmt = stmt.order_by(desc(Image.file_size).nulls_last(), desc(Image.id))
        elif sort == "mission":
            stmt = stmt.join(Mission, isouter=True).order_by(asc(Mission.name).nulls_last(), desc(Image.id))
        else:
            stmt = stmt.order_by(desc(Image.id))

        total = s.execute(select(func.count()).select_from(stmt.subquery())).scalar()
        images = s.execute(stmt.offset(offset).limit(limit)).scalars().all()
        return images, total

def get_image_by_id(image_id):
    with SessionLocal() as s:
        stmt = select(Image).options(selectinload(Image.tags), selectinload(Image.mission)).where(Image.id == image_id)
        return s.execute(stmt).scalar_one_or_none()

def update_image(image_id, **kwargs):
    with SessionLocal() as s:
        stmt = select(Image).where(Image.id == image_id)
        img = s.execute(stmt).scalar_one()
        for k, v in kwargs.items():
            if hasattr(img, k):
                setattr(img, k, v)
        s.commit()

def delete_image(image_id):
    with SessionLocal() as s:
        stmt = select(Image).where(Image.id == image_id)
        img = s.execute(stmt).scalar_one()
        file_path = img.file_path
        s.delete(img)
        s.commit()
        if file_path:
            path = IMAGES_DIR / file_path
            if path.exists():
                path.unlink()

def add_tag_to_image(image_id, tag_name):
    with SessionLocal() as s:
        stmt = select(Image).options(selectinload(Image.tags)).where(Image.id == image_id)
        img = s.execute(stmt).scalar_one()
        tag_name = tag_name.strip().lower()
        if not tag_name:
            return
        if len(tag_name) > 150:
            tag_name = tag_name[:150]
        
        tag = s.execute(select(Tag).where(Tag.name == tag_name)).scalar_one_or_none()
        if not tag:
            tag = Tag(name=tag_name)
            s.add(tag)
            s.flush()
            
        if not any(t.id == tag.id for t in img.tags):
            img.tags.append(tag)
        s.commit()

def remove_tag_from_image(image_id, tag_id):
    with SessionLocal() as s:
        stmt = select(Image).options(selectinload(Image.tags)).where(Image.id == image_id)
        img = s.execute(stmt).scalar_one()
        tag = s.execute(select(Tag).where(Tag.id == tag_id)).scalar_one()
        if tag in img.tags:
            img.tags.remove(tag)
        s.commit()

def get_tags_for_image(image_id):
    with SessionLocal() as s:
        stmt = select(Image).options(selectinload(Image.tags)).where(Image.id == image_id)
        img = s.execute(stmt).scalar_one()
        return list(img.tags)

def get_all_tags():
    with SessionLocal() as s:
        return s.execute(select(Tag).order_by(Tag.name)).scalars().all()

def rename_tag(tag_id, new_name):
    with SessionLocal() as s:
        tag = s.execute(select(Tag).where(Tag.id == tag_id)).scalar_one()
        tag.name = new_name.strip().lower()[:150]
        s.commit()

def delete_tag(tag_id):
    with SessionLocal() as s:
        tag = s.execute(select(Tag).where(Tag.id == tag_id)).scalar_one()
        s.delete(tag)
        s.commit()

def get_collections():
    with SessionLocal() as s:
        return s.execute(select(Collection).order_by(Collection.created_at.desc())).scalars().all()

def create_collection(name, description=""):
    with SessionLocal() as s:
        c = Collection(name=name, description=description)
        s.add(c)
        s.commit()
        return c.id

def rename_collection(collection_id, name):
    with SessionLocal() as s:
        c = s.execute(select(Collection).where(Collection.id == collection_id)).scalar_one()
        c.name = name
        s.commit()

def delete_collection(collection_id):
    with SessionLocal() as s:
        c = s.execute(select(Collection).where(Collection.id == collection_id)).scalar_one()
        s.delete(c)
        s.commit()

def get_collection_images(collection_id):
    with SessionLocal() as s:
        c = s.execute(select(Collection).options(selectinload(Collection.images)).where(Collection.id == collection_id)).scalar_one()
        return list(c.images)

def get_collection_count(collection_id):
    with SessionLocal() as s:
        c = s.execute(select(Collection).options(selectinload(Collection.images)).where(Collection.id == collection_id)).scalar_one()
        return len(c.images)

def add_image_to_collection(collection_id, image_id):
    with SessionLocal() as s:
        c = s.execute(select(Collection).options(selectinload(Collection.images)).where(Collection.id == collection_id)).scalar_one()
        img = s.execute(select(Image).where(Image.id == image_id)).scalar_one()
        if img not in c.images:
            c.images.append(img)
            s.commit()

def remove_image_from_collection(collection_id, image_id):
    with SessionLocal() as s:
        c = s.execute(select(Collection).options(selectinload(Collection.images)).where(Collection.id == collection_id)).scalar_one()
        img = s.execute(select(Image).where(Image.id == image_id)).scalar_one()
        if img in c.images:
            c.images.remove(img)
            s.commit()

def get_all_images_for_dialog(search=""):
    with SessionLocal() as s:
        stmt = select(Image)
        if search:
            stmt = stmt.where(Image.title.ilike(f"%{search}%"))
        return s.execute(stmt.order_by(Image.title).limit(100)).scalars().all()

def get_asteroids(start_date: datetime | None = None, end_date: datetime | None = None, hazardous_only: bool = False):
    with SessionLocal() as s:
        stmt = select(Asteroid)
        if start_date:
            stmt = stmt.where(Asteroid.approach_date >= start_date)
        if end_date:
            stmt = stmt.where(Asteroid.approach_date <= end_date)
        if hazardous_only:
            stmt = stmt.where(Asteroid.is_hazardous == True)
        return s.execute(stmt.order_by(Asteroid.approach_date)).scalars().all()