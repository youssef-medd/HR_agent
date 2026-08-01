"""A1 — skills taxonomy (ESCO-style canonical labels).

A small seeded table of canonical skill labels. A1 normalizes the skills it
extracts from a JD against these so scoring compares like-for-like; unmatched
skills are kept verbatim.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EscoSkill(Base):
    __tablename__ = "esco_skills"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    # Lowercased label for case-insensitive matching.
    normalized: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
