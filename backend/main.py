"""Book Boyfriend — FastAPI application."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
    verify_ws_token,
)
from backend.characters.prompt_builder import (
    RHYSAND_CHARACTER,
    RHYSAND_PROFILE,
    build_system_prompt,
)
from backend.database import create_db_and_tables, engine, get_session
from backend.models import (
    AppSettings,
    Character,
    CharacterProfile,
    Conversation,
    Message,
    User,
)
from backend.providers import get_llm_provider, get_tts_provider
from backend.scraper import scrape_urls
from backend.characters.profile_builder import build_profile
from backend.characters.embedder import embed_character_content
from backend.rag.retriever import retrieve

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan: seed DB with hardcoded Rhysand on first run
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    _seed_characters()
    yield


def _seed_characters() -> None:
    """Insert the hardcoded Phase-1 test character if not present."""
    with Session(engine) as session:
        existing = session.exec(
            select(Character).where(Character.name == "Rhysand")
        ).first()
        if existing:
            return

        char = Character(**RHYSAND_CHARACTER)
        session.add(char)
        session.flush()

        profile_data = {**RHYSAND_PROFILE, "character_id": char.id}
        session.add(CharacterProfile(**profile_data))
        session.commit()
        logger.info("Seeded character: Rhysand")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Book Boyfriend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic request / response schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str

class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None

class ChatResponse(BaseModel):
    reply: str
    conversation_id: str

class CharacterOut(BaseModel):
    id: str
    name: str
    series: str
    author: str
    image_url: str
    archetype: str

class CharacterDetailOut(CharacterOut):
    voice_guide: str = ""
    tropes: list[str] = []

class ConversationOut(BaseModel):
    id: str
    character_id: str
    character_name: str
    created_at: str

class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: str

class CharacterBuildRequest(BaseModel):
    name: str
    series: str
    author: str
    source_urls: list[str]
    archetype: str = ""
    image_url: str = ""

class CharacterBuildResponse(BaseModel):
    character_id: str
    name: str
    series: str
    profile_summary: dict
    chunks_embedded: int
    warnings: list[str]

class SettingOut(BaseModel):
    key: str
    value: str

class SettingUpdate(BaseModel):
    value: str


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.post("/auth/register", response_model=TokenResponse)
def register(body: RegisterRequest, session: Session = Depends(get_session)):
    existing = session.exec(select(User).where(User.email == body.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(email=body.email, hashed_password=hash_password(body.password))
    session.add(user)
    session.commit()
    session.refresh(user)

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@app.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == body.email)).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@app.post("/auth/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, session: Session = Depends(get_session)):
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


# ---------------------------------------------------------------------------
# Character endpoints
# ---------------------------------------------------------------------------

@app.get("/characters", response_model=list[CharacterOut])
def list_characters(session: Session = Depends(get_session)):
    characters = session.exec(select(Character)).all()
    return characters


@app.get("/characters/{character_id}", response_model=CharacterDetailOut)
def get_character(character_id: str, session: Session = Depends(get_session)):
    char = session.get(Character, character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")

    profile = session.exec(
        select(CharacterProfile).where(CharacterProfile.character_id == character_id)
    ).first()

    tropes = []
    voice_guide = ""
    if profile:
        try:
            tropes = json.loads(profile.tropes) if profile.tropes else []
        except json.JSONDecodeError:
            tropes = []
        voice_guide = profile.voice_guide or ""

    return CharacterDetailOut(
        id=char.id,
        name=char.name,
        series=char.series,
        author=char.author,
        image_url=char.image_url,
        archetype=char.archetype,
        voice_guide=voice_guide,
        tropes=tropes,
    )


# ---------------------------------------------------------------------------
# Admin: character builder
# ---------------------------------------------------------------------------

@app.post("/admin/characters/build", response_model=CharacterBuildResponse)
async def build_character(
    body: CharacterBuildRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Scrape source URLs and build a complete character profile via LLM."""
    if not body.source_urls:
        raise HTTPException(status_code=400, detail="At least one source URL is required")

    # 1. Scrape all URLs concurrently
    scraped = await scrape_urls(body.source_urls)

    successful = [s for s in scraped if s.success]
    if not successful:
        errors = "; ".join(s.error for s in scraped if s.error)
        raise HTTPException(status_code=422, detail=f"All source URLs failed: {errors}")

    # 2. Build profile via LLM
    try:
        profile_result = await build_profile(
            character_name=body.name,
            series=body.series,
            author=body.author,
            scraped=scraped,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # 3. Save Character + CharacterProfile
    character = Character(
        name=body.name,
        series=body.series,
        author=body.author,
        image_url=body.image_url,
        archetype=body.archetype,
    )
    session.add(character)
    session.flush()

    char_profile = CharacterProfile(
        character_id=character.id,
        identity=json.dumps(profile_result.identity),
        personality=json.dumps(profile_result.personality),
        relationships=json.dumps(profile_result.relationships),
        arc=json.dumps(profile_result.arc),
        tropes=json.dumps(profile_result.tropes),
        voice_guide=profile_result.voice_guide,
        boundaries=profile_result.boundaries,
        iconic_moments=json.dumps(profile_result.iconic_moments),
        source_urls=json.dumps(profile_result.source_urls),
    )
    session.add(char_profile)
    session.commit()
    session.refresh(character)

    # 4. Embed scraped content for RAG
    chunks_embedded = embed_character_content(character.id, scraped)

    return CharacterBuildResponse(
        character_id=character.id,
        name=character.name,
        series=character.series,
        profile_summary={
            "identity_keys": list(profile_result.identity.keys()),
            "trait_count": len(profile_result.personality.get("core_traits", [])),
            "trope_count": len(profile_result.tropes),
            "moments_count": len(profile_result.iconic_moments),
        },
        chunks_embedded=chunks_embedded,
        warnings=profile_result.warnings,
    )


# ---------------------------------------------------------------------------
# Chat endpoints
# ---------------------------------------------------------------------------

@app.post("/characters/{character_id}/chat", response_model=ChatResponse)
async def chat_text(
    character_id: str,
    body: ChatRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    char = session.get(Character, character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")

    profile = session.exec(
        select(CharacterProfile).where(CharacterProfile.character_id == character_id)
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Character profile not found")

    # Get or create conversation
    conversation = None
    if body.conversation_id:
        conversation = session.get(Conversation, body.conversation_id)
        if not conversation or conversation.user_id != user.id:
            raise HTTPException(status_code=404, detail="Conversation not found")

    if not conversation:
        conversation = Conversation(user_id=user.id, character_id=character_id)
        session.add(conversation)
        session.commit()
        session.refresh(conversation)

    # Build message history
    history = session.exec(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at)
    ).all()

    messages = [{"role": m.role, "content": m.content} for m in history]
    messages.append({"role": "user", "content": body.message})

    # Build system prompt
    system_prompt = build_system_prompt(char, profile)

    # RAG: retrieve relevant wiki chunks to enhance context
    try:
        rag_chunks = retrieve(
            query=body.message,
            notebook_id=character_id,
            top_k=3,
            score_threshold=0.3,
        )
        if rag_chunks:
            rag_context = "\n\n".join(
                f"[Source detail]: {chunk.text}" for chunk in rag_chunks
            )
            system_prompt += (
                f"\n\n## Relevant Background Knowledge\n"
                f"Use these details naturally in your response if relevant:\n"
                f"{rag_context}"
            )
    except Exception as e:
        logger.warning(f"RAG retrieval failed for character {character_id}: {e}")

    # Get LLM response
    llm = get_llm_provider()
    reply = await llm.chat(messages, system=system_prompt)

    # Save messages
    session.add(Message(conversation_id=conversation.id, role="user", content=body.message))
    session.add(Message(conversation_id=conversation.id, role="assistant", content=reply))
    session.commit()

    return ChatResponse(reply=reply, conversation_id=conversation.id)


@app.post("/characters/{character_id}/chat/voice")
async def chat_voice(
    character_id: str,
    body: ChatRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Text chat that returns MP3 audio of the character's reply."""
    # Get text reply first
    chat_result = await chat_text(character_id, body, user, session)

    tts = get_tts_provider()
    if not tts:
        raise HTTPException(status_code=503, detail="TTS not configured")

    audio = await tts.generate(chat_result.reply)
    # HTTP headers can't contain newlines — URL-encode the reply text
    from urllib.parse import quote
    safe_reply = quote(chat_result.reply, safe="")
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={
            "X-Text-Reply": safe_reply,
            "X-Conversation-Id": chat_result.conversation_id,
        },
    )


# ---------------------------------------------------------------------------
# Conversation history
# ---------------------------------------------------------------------------

@app.get("/characters/{character_id}/conversations", response_model=list[ConversationOut])
def list_conversations(
    character_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    convos = session.exec(
        select(Conversation)
        .where(Conversation.user_id == user.id, Conversation.character_id == character_id)
        .order_by(Conversation.created_at.desc())
    ).all()

    char = session.get(Character, character_id)
    char_name = char.name if char else "Unknown"

    return [
        ConversationOut(
            id=c.id,
            character_id=c.character_id,
            character_name=char_name,
            created_at=c.created_at.isoformat(),
        )
        for c in convos
    ]


@app.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(
    conversation_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    convo = session.get(Conversation, conversation_id)
    if not convo or convo.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs = session.exec(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    ).all()

    return [
        MessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            created_at=m.created_at.isoformat(),
        )
        for m in msgs
    ]


# ---------------------------------------------------------------------------
# WebSocket voice streaming
# ---------------------------------------------------------------------------

@app.websocket("/ws/{character_id}")
async def ws_voice(websocket: WebSocket, character_id: str):
    await websocket.accept()

    # Authenticate via query param
    token = websocket.query_params.get("token", "")
    with Session(engine) as session:
        user = verify_ws_token(token, session)
        if not user:
            await websocket.close(code=4001, reason="Unauthorized")
            return

        char = session.get(Character, character_id)
        if not char:
            await websocket.close(code=4004, reason="Character not found")
            return

        profile = session.exec(
            select(CharacterProfile).where(CharacterProfile.character_id == character_id)
        ).first()
        if not profile:
            await websocket.close(code=4004, reason="Character profile not found")
            return

        system_prompt = build_system_prompt(char, profile)

        # Create conversation for this WS session
        conversation = Conversation(user_id=user.id, character_id=character_id)
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
        conversation_id = conversation.id

    llm = get_llm_provider()
    tts = get_tts_provider()
    messages: list[dict] = []

    try:
        while True:
            data = await websocket.receive_text()
            user_text = data.strip()
            if not user_text:
                continue

            messages.append({"role": "user", "content": user_text})

            reply = await llm.chat(messages, system=system_prompt)
            messages.append({"role": "assistant", "content": reply})

            # Persist messages
            with Session(engine) as session:
                session.add(Message(conversation_id=conversation_id, role="user", content=user_text))
                session.add(Message(conversation_id=conversation_id, role="assistant", content=reply))
                session.commit()

            # Send text reply
            await websocket.send_json({"type": "text", "content": reply, "conversation_id": conversation_id})

            # Send audio if TTS is available
            if tts:
                try:
                    audio = await tts.generate(reply)
                    if audio:
                        await websocket.send_bytes(audio)
                except Exception as e:
                    logger.warning(f"TTS failed: {e}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: user={user.id} character={character_id}")


# ---------------------------------------------------------------------------
# Settings endpoints
# ---------------------------------------------------------------------------

@app.get("/settings", response_model=list[SettingOut])
def list_settings(
    _user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return session.exec(select(AppSettings)).all()


@app.put("/settings/{key}", response_model=SettingOut)
def update_setting(
    key: str,
    body: SettingUpdate,
    _user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    setting = session.get(AppSettings, key)
    if setting:
        setting.value = body.value
    else:
        setting = AppSettings(key=key, value=body.value)
        session.add(setting)
    session.commit()
    session.refresh(setting)
    return setting


# ---------------------------------------------------------------------------
# Static frontend (must be LAST — catches all unmatched routes)
# ---------------------------------------------------------------------------

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
