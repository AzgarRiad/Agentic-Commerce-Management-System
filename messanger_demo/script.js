/* ACMS Messenger-style frontend. No framework or external dependencies. */
(() => {
  const CHAT_ENDPOINT = "/chat"; // Served from http://localhost:8000, so this resolves to localhost:8000/chat.
  const MAX_MESSAGE_LENGTH = 4000;

  const appShell = document.getElementById("appShell");
  const chatList = document.getElementById("chatList");
  const searchInput = document.getElementById("searchInput");
  const messageForm = document.getElementById("messageForm");
  const messageInput = document.getElementById("messageInput");
  const sendButton = document.getElementById("sendButton");
  const messageList = document.getElementById("messageList");
  const messagesWrap = document.getElementById("messagesWrap");
  const typingRow = document.getElementById("typingRow");
  const conversationIntro = document.getElementById("conversationIntro");
  const headerName = document.getElementById("headerName");
  const headerStatus = document.getElementById("headerStatus");
  const headerAvatar = document.getElementById("headerAvatar");
  const detailsName = document.getElementById("detailsName");
  const detailsPanel = document.getElementById("detailsPanel");
  const toast = document.getElementById("toast");
  const connectionDot = document.getElementById("connectionDot");
  const connectionLabel = document.getElementById("connectionLabel");
  const detailsBackendStatus = document.getElementById("detailsBackendStatus");

  const nowTime = () => new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  let nextId = 5;
  let activeThreadId = "acms";
  let isSending = false;
  let toastTimeout = null;
  let selectedFilter = "all";

  const makeMessage = (role, text, extra = {}) => ({
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    text,
    time: nowTime(),
    ...extra,
  });

  const threads = [
    {
      id: "acms", name: "ACMS Store", subtitle: "AI assistant · Active now", initials: "AC", avatar: "avatar-store", online: true, unread: false, group: false,
      preview: "Test your ACMS AI assistant here",
      messages: [makeMessage("assistant", "Hi! Welcome to ACMS Store. 😊\n\nI'm your store assistant. Ask me about products, sizes, prices, stock, or delivery and I'll do my best to help.")],
    },
    {
      id: "product", name: "Product inquiry", subtitle: "Demo conversation · AI assistant", initials: "PI", avatar: "avatar-purple", online: false, unread: true, group: false,
      preview: "Try a product or price question",
      messages: [makeMessage("assistant", "This is a separate demo chat. Send a product question to test the ACMS backend.")],
    },
    {
      id: "delivery", name: "Delivery & orders", subtitle: "Demo conversation · AI assistant", initials: "DO", avatar: "avatar-coral", online: false, unread: true, group: false,
      preview: "Try a delivery or order question",
      messages: [makeMessage("assistant", "Use this thread to test a delivery or order-related message against your current /chat endpoint.")],
    },
    {
      id: "group", name: "ACMS test group", subtitle: "Demo group · AI assistant", initials: "AT", avatar: "avatar-green", online: false, unread: false, group: true,
      preview: "A mock group conversation",
      messages: [makeMessage("assistant", "This is only a frontend mock. Your API still receives one message string at a time, without a conversation ID.")],
    },
  ];

  function activeThread() {
    return threads.find((thread) => thread.id === activeThreadId) || threads[0];
  }

  function escapeText(value) {
    // Message content is inserted with textContent, never interpreted as HTML.
    return String(value ?? "");
  }

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("show");
    if (toastTimeout) clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => toast.classList.remove("show"), 3000);
  }

  function setConnection(isOnline, label) {
    connectionDot.classList.remove("unknown");
    connectionDot.classList.toggle("offline", !isOnline);
    connectionLabel.textContent = label || (isOnline ? "Local ACMS chat" : "Backend unavailable");
    detailsBackendStatus.textContent = label || (isOnline ? "Connection available" : "Backend unavailable");
  }

  function createAvatar(initials, avatarClass, withDot = false) {
    const avatar = document.createElement("div");
    avatar.className = `avatar ${avatarClass || "avatar-initial"}`;
    const letters = document.createElement("span");
    letters.textContent = initials;
    avatar.appendChild(letters);
    if (withDot) {
      const dot = document.createElement("i");
      dot.className = "online-dot";
      avatar.appendChild(dot);
    }
    return avatar;
  }

  function renderChatList() {
    const query = searchInput.value.trim().toLocaleLowerCase();
    chatList.replaceChildren();
    const matches = threads.filter((thread) => {
      const textMatches = `${thread.name} ${thread.preview} ${thread.subtitle}`.toLocaleLowerCase().includes(query);
      const filterMatches = selectedFilter === "all"
        || (selectedFilter === "unread" && thread.unread)
        || (selectedFilter === "groups" && thread.group);
      return textMatches && filterMatches;
    });

    if (!matches.length) {
      const empty = document.createElement("p");
      empty.className = "no-search-results";
      empty.textContent = "No chats found. Try a different search.";
      chatList.appendChild(empty);
      return;
    }

    for (const thread of matches) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = `chat-row${thread.id === activeThreadId ? " active" : ""}${thread.unread ? " unread" : ""}`;
      row.setAttribute("role", "option");
      row.setAttribute("aria-selected", thread.id === activeThreadId ? "true" : "false");
      row.addEventListener("click", () => selectThread(thread.id));

      row.appendChild(createAvatar(thread.initials, thread.avatar, thread.online));
      const copy = document.createElement("span");
      copy.className = "chat-row-copy";
      const top = document.createElement("span");
      top.className = "chat-row-top";
      const name = document.createElement("span");
      name.className = "chat-row-name";
      name.textContent = thread.name;
      const time = document.createElement("span");
      time.className = "chat-row-time";
      const last = thread.messages[thread.messages.length - 1];
      time.textContent = last?.time || "";
      top.append(name, time);
      const preview = document.createElement("span");
      preview.className = "chat-row-preview";
      const latest = last && last.role === "user" ? `You: ${last.text}` : (last?.text || thread.preview);
      preview.textContent = latest.replace(/\s+/g, " ");
      copy.append(top, preview);
      row.appendChild(copy);
      if (thread.unread && thread.id !== activeThreadId) {
        const unread = document.createElement("i");
        unread.className = "unread-dot";
        row.appendChild(unread);
      }
      chatList.appendChild(row);
    }
  }

  function renderMessages() {
    const thread = activeThread();
    messageList.replaceChildren();
    conversationIntro.classList.toggle("hidden", thread.messages.length > 1 || thread.id !== "acms");

    for (const message of thread.messages) {
      const row = document.createElement("div");
      row.className = `message-row ${message.role === "user" ? "user" : message.role === "error" ? "error" : message.role === "system" ? "system" : "assistant"}`;
      if (message.role === "assistant" || message.role === "error") {
        if (message.role === "assistant") row.appendChild(createMiniAvatar(thread));
      }

      const content = document.createElement("div");
      content.className = "message-content";
      const bubble = document.createElement("div");
      bubble.className = "message-bubble";
      bubble.textContent = escapeText(message.text);
      content.appendChild(bubble);

      if (message.role !== "system") {
        const meta = document.createElement("span");
        meta.className = "message-meta";
        meta.textContent = message.time || "";
        content.appendChild(meta);
      }
      row.appendChild(content);
      messageList.appendChild(row);
    }

    typingRow.classList.toggle("hidden", !isSending);
    scrollMessagesToBottom();
    renderChatList();
  }

  function createMiniAvatar(thread) {
    const avatar = document.createElement("div");
    avatar.className = `mini-avatar ${thread.avatar}`;
    const text = document.createElement("span");
    text.textContent = thread.initials;
    avatar.appendChild(text);
    return avatar;
  }

  function scrollMessagesToBottom() {
    requestAnimationFrame(() => {
      messagesWrap.scrollTop = messagesWrap.scrollHeight;
    });
  }

  function selectThread(id) {
    const found = threads.find((thread) => thread.id === id);
    if (!found) return;
    activeThreadId = id;
    found.unread = false;
    headerName.textContent = found.name;
    headerStatus.textContent = found.subtitle;
    detailsName.textContent = found.name;
    headerAvatar.className = `avatar ${found.avatar}`;
    headerAvatar.replaceChildren();
    const initials = document.createElement("span");
    initials.textContent = found.initials;
    headerAvatar.appendChild(initials);
    if (found.online) {
      const dot = document.createElement("i");
      dot.className = "online-dot";
      headerAvatar.appendChild(dot);
    }
    messageInput.placeholder = `Message ${found.name}…`;
    appShell.classList.add("show-conversation");
    renderMessages();
    messageInput.focus({ preventScroll: true });
  }

  function resizeInput() {
    messageInput.style.height = "auto";
    messageInput.style.height = `${Math.min(messageInput.scrollHeight, 130)}px`;
    sendButton.disabled = isSending || !messageInput.value.trim();
  }

  function addSystemMessage(text, role = "system") {
    activeThread().messages.push(makeMessage(role, text));
    renderMessages();
  }

  async function sendMessage(text) {
    const cleanMessage = text.trim();
    if (!cleanMessage || isSending) return;
    if (cleanMessage.length > MAX_MESSAGE_LENGTH) {
      showToast(`Messages must be ${MAX_MESSAGE_LENGTH.toLocaleString()} characters or fewer.`);
      return;
    }

    const thread = activeThread();
    thread.messages.push(makeMessage("user", cleanMessage));
    thread.preview = cleanMessage;
    thread.unread = false;
    messageInput.value = "";
    resizeInput();
    isSending = true;
    sendButton.disabled = true;
    headerStatus.textContent = "AI assistant · Typing…";
    renderMessages();

    try {
      const response = await fetch(CHAT_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({ message: cleanMessage }),
      });

      let payload;
      try {
        payload = await response.json();
      } catch {
        throw new Error(`The backend returned an invalid response (HTTP ${response.status}).`);
      }

      if (!response.ok) {
        const detail = typeof payload?.detail === "string"
          ? payload.detail
          : Array.isArray(payload?.detail)
            ? payload.detail.map((item) => item.msg || "Invalid request").join("; ")
            : `Request failed with HTTP ${response.status}.`;
        throw new Error(detail);
      }
      if (typeof payload?.reply !== "string" || !payload.reply.trim()) {
        throw new Error("The API response did not contain a non-empty string in `reply`.");
      }
      thread.messages.push(makeMessage("assistant", payload.reply.trim()));
      thread.preview = payload.reply.trim();
      setConnection(true, "Local ACMS chat");
    } catch (error) {
      const message = error instanceof TypeError
        ? "Couldn't reach the backend. Make sure your FastAPI app is running at http://localhost:8000 and open this page from that address."
        : (error?.message || "Something went wrong while contacting ACMS.");
      thread.messages.push(makeMessage("error", message));
      thread.preview = "Backend request failed";
      setConnection(false, "Backend unavailable");
    } finally {
      isSending = false;
      headerStatus.textContent = thread.subtitle;
      resizeInput();
      renderMessages();
      messageInput.focus({ preventScroll: true });
    }
  }

  messageForm.addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage(messageInput.value);
  });

  messageInput.addEventListener("input", resizeInput);
  messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      if (!sendButton.disabled) messageForm.requestSubmit();
    }
  });

  searchInput.addEventListener("input", renderChatList);
  document.querySelectorAll(".filter-tab").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".filter-tab").forEach((tab) => tab.classList.toggle("selected", tab === button));
      selectedFilter = button.dataset.filter || "all";
      renderChatList();
    });
  });

  document.getElementById("newChatButton").addEventListener("click", () => {
    const id = `new-${nextId++}`;
    const name = `New test chat ${nextId - 1}`;
    const thread = {
      id, name, subtitle: "Demo conversation · AI assistant", initials: "AI", avatar: "avatar-initial", online: false, unread: false, group: false,
      preview: "New test conversation",
      messages: [makeMessage("assistant", "New test conversation ready. Send a message to test your ACMS backend. Each request still sends only the latest message text.")],
    };
    threads.unshift(thread);
    selectThread(id);
    showToast("Created a local demo conversation.");
  });

  document.getElementById("clearChatButton").addEventListener("click", () => {
    if (isSending) {
      showToast("Wait for the current reply before clearing this chat.");
      return;
    }
    const thread = activeThread();
    thread.messages = [makeMessage("assistant", "Chat cleared. Send a message to test your ACMS AI assistant.")];
    thread.preview = "Chat cleared";
    renderMessages();
    showToast("Current demo conversation cleared.");
  });

  document.getElementById("mobileBackButton").addEventListener("click", () => {
    appShell.classList.remove("show-conversation");
  });

  document.getElementById("infoButton").addEventListener("click", () => {
    detailsPanel.classList.toggle("hidden");
  });
  document.getElementById("closeDetailsButton").addEventListener("click", () => detailsPanel.classList.add("hidden"));


  document.getElementById("emojiButton").addEventListener("click", () => {
    messageInput.value += "😊";
    messageInput.focus();
    resizeInput();
  });
  document.getElementById("inputEmojiButton").addEventListener("click", () => {
    messageInput.value += "😊";
    messageInput.focus();
    resizeInput();
  });

  document.querySelectorAll("[data-toast]").forEach((button) => {
    button.addEventListener("click", () => showToast(button.dataset.toast));
  });
  document.querySelector(".brand-mark").addEventListener("click", () => showToast("ACMS Messenger-style frontend demo"));

  selectThread(activeThreadId);
  renderChatList();
  resizeInput();
})();
