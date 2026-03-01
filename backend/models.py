"""SQLModel database models for Book Boyfriend."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel, Relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# --- User ---

class User(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=_utcnow)

    conversations: list["Conversation"] = Relationship(back_populates="user")


# --- Character ---

class Character(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(index=True)
    series: str = ""
    author: str = ""
    image_url: str = ""
    archetype: str = ""
    voice_id: str = ""
    created_at: datetime = Field(default_factory=_utcnow)

    profile: Optional["CharacterProfile"] = Relationship(back_populates="character")
    conversations: list["Conversation"] = Relationship(back_populates="character")


class CharacterProfile(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    character_id: str = Field(foreign_key="character.id", unique=True)
    identity: str = ""        # JSON string
    personality: str = ""     # JSON string
    relationships: str = ""   # JSON string
    arc: str = ""             # JSON string
    tropes: str = ""          # JSON string
    voice_guide: str = ""     # plain text
    boundaries: str = ""      # plain text
    iconic_moments: str = ""  # JSON string
    source_urls: str = ""     # JSON string

    character: Optional[Character] = Relationship(back_populates="profile")


# --- Conversation / Messages ---

class Conversation(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id")
    character_id: str = Field(foreign_key="character.id")
    created_at: datetime = Field(default_factory=_utcnow)

    user: Optional[User] = Relationship(back_populates="conversations")
    character: Optional[Character] = Relationship(back_populates="conversations")
    messages: list["Message"] = Relationship(back_populates="conversation")


class Message(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    conversation_id: str = Field(foreign_key="conversation.id", index=True)
    role: str  # "user" or "assistant"
    content: str
    created_at: datetime = Field(default_factory=_utcnow)

    conversation: Optional[Conversation] = Relationship(back_populates="messages")


# --- App Settings ---

class AppSettings(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str = ""
