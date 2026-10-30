"""One society, several towers, many flats and potentially many households per flat."""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.extensions import db


class SocietyProfile(db.Model):
    __tablename__ = "society_profile"
    __table_args__ = (CheckConstraint("id = 1", name="single_society_row"),)

    # One row only. No society foreign key is needed on other V1 models.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    locality: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)


class Tower(db.Model):
    __tablename__ = "towers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    flats: Mapped[list["Flat"]] = relationship("Flat", back_populates="tower")

    @validates("name")
    def uppercase_name(self, key: str, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("Tower name cannot be empty.")
        return cleaned


class Flat(db.Model):
    __tablename__ = "flats"
    __table_args__ = (
        UniqueConstraint("tower_id", "flat_number", name="tower_flat_number"),
        CheckConstraint("floor_number >= 0", name="nonnegative_floor"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tower_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("towers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    flat_number: Mapped[str] = mapped_column(String(16), nullable=False)
    floor_number: Mapped[int] = mapped_column(Integer, nullable=False)

    tower: Mapped["Tower"] = relationship("Tower", back_populates="flats")
    households: Mapped[list["Household"]] = relationship("Household", back_populates="flat")

    @validates("flat_number")
    def normalize_flat_number(self, key: str, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("Flat number cannot be empty.")
        return cleaned


class Household(db.Model):
    __tablename__ = "households"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    flat_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("flats.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(100), nullable=False)

    flat: Mapped["Flat"] = relationship("Flat", back_populates="households")
    memberships: Mapped[list["Membership"]] = relationship("Membership", back_populates="household")
