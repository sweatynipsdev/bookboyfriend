/* ============ Book Boyfriend — Frontend App ============ */

(() => {
  "use strict";

  // ---- State ----
  let token = localStorage.getItem("bb_token") || "";
  let currentCharacter = null; // { id, name, series, archetype }
  let conversationId = null;
  let voiceEnabled = false;
  let isAuthRegister = false;
  let isSending = false;

  // ---- DOM refs ----
  const $ = (sel) => document.querySelector(sel);
  const screens = {
    auth: $("#auth-screen"),
    characters: $("#characters-screen"),
    chat: $("#chat-screen"),
  };

  // Auth
  const authForm = $("#auth-form");
  const authEmail = $("#auth-email");
  const authPassword = $("#auth-password");
  const authSubmit = $("#auth-submit");
  const authError = $("#auth-error");
  const authToggleText = $("#auth-toggle-text");
  const authToggleLink = $("#auth-toggle-link");

  // Characters
  const charactersGrid = $("#characters-grid");
  const logoutBtn = $("#logout-btn");

  // Chat
  const chatCharName = $("#chat-char-name");
  const chatCharSeries = $("#chat-char-series");
  const chatMessages = $("#chat-messages");
  const chatForm = $("#chat-form");
  const chatInput = $("#chat-input");
  const chatSend = $("#chat-send");
  const chatBack = $("#chat-back");
  const voiceToggle = $("#voice-toggle");
  const ttsAudio = $("#tts-audio");

  // ---- API ----
  const API = {
    async request(method, path, body) {
      const opts = {
        method,
        headers: { "Content-Type": "application/json" },
      };
      if (token) opts.headers["Authorization"] = `Bearer ${token}`;
      if (body) opts.body = JSON.stringify(body);

      const res = await fetch(path, opts);
      if (res.status === 401) {
        logout();
        throw new Error("Session expired");
      }
      return res;
    },

    async json(method, path, body) {
      const res = await this.request(method, path, body);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Request failed");
      return data;
    },

    register: (email, password) =>
      API.json("POST", "/auth/register", { email, password }),

    login: (email, password) =>
      API.json("POST", "/auth/login", { email, password }),

    getCharacters: () => API.json("GET", "/characters"),

    chat: (characterId, message, convId) =>
      API.json("POST", `/characters/${characterId}/chat`, {
        message,
        conversation_id: convId || null,
      }),

    async chatVoice(characterId, message, convId) {
      const res = await this.request(
        "POST",
        `/characters/${characterId}/chat/voice`,
        { message, conversation_id: convId || null }
      );
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Voice request failed");
      }
      const textReply = res.headers.get("X-Text-Reply") || "";
      const newConvId = res.headers.get("X-Conversation-Id") || "";
      const audioBlob = await res.blob();
      return { reply: textReply, conversation_id: newConvId, audio: audioBlob };
    },

    getMessages: (convId) => API.json("GET", `/conversations/${convId}/messages`),
  };

  // ---- Screen Router ----
  function showScreen(name) {
    Object.values(screens).forEach((s) => (s.hidden = true));
    screens[name].hidden = false;

    if (name === "characters") loadCharacters();
    if (name === "chat") chatInput.focus();
  }

  // ---- Auth ----
  function updateAuthUI() {
    authSubmit.textContent = isAuthRegister ? "Create Account" : "Sign In";
    authToggleText.textContent = isAuthRegister
      ? "Already have an account?"
      : "Don't have an account?";
    authToggleLink.textContent = isAuthRegister ? "Sign in" : "Create one";
    authError.hidden = true;
  }

  authToggleLink.addEventListener("click", (e) => {
    e.preventDefault();
    isAuthRegister = !isAuthRegister;
    updateAuthUI();
  });

  authForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    authError.hidden = true;
    authSubmit.disabled = true;

    try {
      const fn = isAuthRegister ? API.register : API.login;
      const data = await fn(authEmail.value.trim(), authPassword.value);
      token = data.access_token;
      localStorage.setItem("bb_token", token);
      authForm.reset();
      showScreen("characters");
    } catch (err) {
      authError.textContent = err.message;
      authError.hidden = false;
    } finally {
      authSubmit.disabled = false;
    }
  });

  function logout() {
    token = "";
    localStorage.removeItem("bb_token");
    currentCharacter = null;
    conversationId = null;
    showScreen("auth");
  }

  logoutBtn.addEventListener("click", logout);

  // ---- Characters ----
  async function loadCharacters() {
    charactersGrid.innerHTML = "";

    try {
      const characters = await API.getCharacters();

      if (characters.length === 0) {
        charactersGrid.innerHTML =
          '<p style="color: var(--text-dim); text-align: center; padding: 40px;">No characters yet.</p>';
        return;
      }

      characters.forEach((char) => {
        const card = document.createElement("div");
        card.className = "character-card";
        card.innerHTML = `
          <h3>${esc(char.name)}</h3>
          <p class="series">${esc(char.series)}</p>
          ${char.archetype ? `<span class="archetype">${esc(char.archetype)}</span>` : ""}
        `;
        card.addEventListener("click", () => openChat(char));
        charactersGrid.appendChild(card);
      });
    } catch (err) {
      charactersGrid.innerHTML = `<p class="error-text">${esc(err.message)}</p>`;
    }
  }

  // ---- Chat ----
  function openChat(char) {
    currentCharacter = char;
    conversationId = null;
    chatCharName.textContent = char.name;
    chatCharSeries.textContent = char.series;
    chatMessages.innerHTML = "";

    // Add a greeting
    addMessage(
      "assistant",
      `*${char.name} looks up, a slow smile forming*\n\nWell... hello there.`
    );

    showScreen("chat");
  }

  chatBack.addEventListener("click", () => {
    currentCharacter = null;
    conversationId = null;
    showScreen("characters");
  });

  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text || isSending || !currentCharacter) return;

    isSending = true;
    chatSend.disabled = true;
    chatInput.value = "";

    addMessage("user", text);
    const typingEl = addMessage("assistant typing", "");

    try {
      if (voiceEnabled) {
        const result = await API.chatVoice(
          currentCharacter.id,
          text,
          conversationId
        );
        conversationId = result.conversation_id;
        typingEl.remove();
        addMessage("assistant", result.reply);
        playAudio(result.audio);
      } else {
        const result = await API.chat(
          currentCharacter.id,
          text,
          conversationId
        );
        conversationId = result.conversation_id;
        typingEl.remove();
        addMessage("assistant", result.reply);
      }
    } catch (err) {
      typingEl.remove();
      addMessage("assistant", `Something went wrong: ${err.message}`);
    } finally {
      isSending = false;
      chatSend.disabled = false;
      chatInput.focus();
    }
  });

  function addMessage(classes, text) {
    const div = document.createElement("div");
    div.className = `message ${classes}`;

    if (classes.includes("typing")) {
      div.innerHTML = '<span class="typing-dots">Thinking</span>';
    } else {
      div.textContent = text;
    }

    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return div;
  }

  // ---- Voice ----
  voiceToggle.addEventListener("click", () => {
    voiceEnabled = !voiceEnabled;
    voiceToggle.classList.toggle("active", voiceEnabled);
  });

  function playAudio(blob) {
    if (!blob || blob.size === 0) return;
    const url = URL.createObjectURL(blob);
    ttsAudio.src = url;
    ttsAudio.play().catch(() => {});
    ttsAudio.addEventListener(
      "ended",
      () => URL.revokeObjectURL(url),
      { once: true }
    );
  }

  // ---- Util ----
  function esc(str) {
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  // ---- Init ----
  updateAuthUI();
  if (token) {
    showScreen("characters");
  } else {
    showScreen("auth");
  }
})();
