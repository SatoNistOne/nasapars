from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)
from sqlalchemy.sql import func

import config


class Base(DeclarativeBase):
    pass


class Mission(Base):
    __tablename__ = "missions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    images: Mapped[list["Image"]] = relationship(back_populates="mission")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)

    images: Mapped[list["Image"]] = relationship(
        secondary="image_tags",
        back_populates="tags",
    )


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    images: Mapped[list["Image"]] = relationship(
        secondary="collection_images",
        back_populates="collections",
    )


class Image(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(primary_key=True)
    nasa_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    date_created: Mapped[datetime | None] = mapped_column(DateTime)
    credit: Mapped[str | None] = mapped_column(String(255))
    mission_id: Mapped[int | None] = mapped_column(ForeignKey("missions.id"))
    file_path: Mapped[str | None] = mapped_column(String(255))
    file_size: Mapped[int | None] = mapped_column(Integer)
    thumbnail: Mapped[bytes | None] = mapped_column(Integer)
    video_url: Mapped[str | None] = mapped_column(String(500))
    rating: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)

    mission: Mapped["Mission | None"] = relationship(back_populates="images")
    tags: Mapped[list["Tag"]] = relationship(
        secondary="image_tags",
        back_populates="images",
    )
    collections: Mapped[list["Collection"]] = relationship(
        secondary="collection_images",
        back_populates="images",
    )


class ImageTag(Base):
    __tablename__ = "image_tags"

    image_id: Mapped[int] = mapped_column(
        ForeignKey("images.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )


class CollectionImage(Base):
    __tablename__ = "collection_images"

    collection_id: Mapped[int] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"),
        primary_key=True,
    )
    image_id: Mapped[int] = mapped_column(
        ForeignKey("images.id", ondelete="CASCADE"),
        primary_key=True,
    )


class Asteroid(Base):
    __tablename__ = "asteroids"

    id: Mapped[int] = mapped_column(primary_key=True)
    neo_id: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    diameter_max_m: Mapped[float] = mapped_column(Float)
    is_hazardous: Mapped[bool] = mapped_column(Boolean)
    approach_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    velocity_kms: Mapped[float] = mapped_column(Float)
    miss_distance_km: Mapped[float] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint("neo_id", "approach_date", name="uq_asteroid_date"),
        Index("ix_asteroids_approach_date", "approach_date"),
    )


Index("ix_images_date_created", Image.date_created)
Index("ix_images_rating", Image.rating)
Index("ix_images_mission_id", Image.mission_id)
Index("ix_images_media_type", Image.media_type)


engine = create_engine(f"sqlite:///{config.DB_PATH}", pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)