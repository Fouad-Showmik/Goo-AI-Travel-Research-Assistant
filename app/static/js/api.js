const GENERIC_ERROR = "Sorry, I couldn't get a reply right now. Please try again.";
const NETWORK_ERROR = "Network problem. Please check your connection and try again.";

// Send a message and consume the application's SSE response stream.
export async function sendMessageStream(sessionId, message, onEvent) {
  let response;

  try {
    response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ session_id: sessionId, message }),
    });
  } catch {
    throw new Error(NETWORK_ERROR);
  }

  if (!response.ok) {
    let data = {};
    try {
      data = await response.json();
    } catch {
      // Use the generic message when the server did not return JSON.
    }
    const detail = typeof data?.detail === "string" ? data.detail.trim() : "";
    throw new Error(detail || GENERIC_ERROR);
  }

  if (!response.body) {
    throw new Error("Streaming is not supported by this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatchFrame = (frame) => {
    let eventName = "message";
    const dataLines = [];

    for (const line of frame.split(/\r?\n/)) {
      if (!line || line.startsWith(":")) continue;
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).replace(/^ /, ""));
      }
    }

    if (!dataLines.length) return;

    try {
      const event = JSON.parse(dataLines.join("\n"));
      if (!event.type) event.type = eventName;
      onEvent(event);
    } catch (error) {
      if (error instanceof SyntaxError) {
        throw new Error("The server sent an invalid streaming event.");
      }
      throw error;
    }
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() ?? "";
      for (const frame of frames) dispatchFrame(frame);
    }

    buffer += decoder.decode();
    if (buffer.trim()) dispatchFrame(buffer);
  } catch (error) {
    if (error instanceof Error && error.message !== "Failed to fetch") throw error;
    throw new Error(NETWORK_ERROR);
  } finally {
    reader.releaseLock();
  }
}

// Try to clear server-side memory without interrupting the new chat flow.
export async function deleteChat(sessionId) {
  try {
    const response = await fetch(`/api/chat/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    });

    if (!response.ok) {
      console.warn("Could not clear the previous chat on the server.");
    }
  } catch {
    console.warn("Could not reach the server to clear the previous chat.");
  }
}
