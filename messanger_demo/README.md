# ACMS Messenger-style frontend

A static Messenger-inspired chat UI made with plain HTML, CSS, and vanilla JavaScript. It sends messages to the FastAPI endpoint already in your app:

```http
POST /chat
Content-Type: application/json

{"message": "Hello"}
```

It expects a JSON response shaped like:

```json
{"reply": "Hello! How can I help?"}
```

## Run it

Start the app from the project root (see the main README), then open **http://localhost:8000/messenger**. Do not open `index.html` as a `file://` URL; the page uses the same-origin `/chat` endpoint.

## Included

- Messenger-style navigation rail, chat list, search and filters
- Responsive conversation area and mobile chat navigation
- Message bubbles, Enter-to-send, Shift+Enter for a newline, typing indicator, and auto-scroll
- Loading/error handling for HTTP failures, invalid responses and backend connection problems
- Details panel with connection status updated after a real `/chat` request

## Important limitation in the current API

The frontend sends only the **latest message** as `{"message": "..."}` because that is what your `ChatRequest` accepts. The messages visible in the browser are not automatically sent as conversation history. If `gemini_chat()` does not maintain conversation history internally, follow-up messages such as “what about the cheaper one?” will reach the model without the previous turns.

The toolbar's attachment, call, video, and GIF controls are visual placeholders because the current `/chat` endpoint accepts plain text only. The frontend does not call `/intro`; sending a message is what tests the API connection. No third-party libraries are used.
