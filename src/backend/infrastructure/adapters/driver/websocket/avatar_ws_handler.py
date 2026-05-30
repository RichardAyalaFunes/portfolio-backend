"""
Avatar WebSocket bridge — driver adapter (inbound).

Provides a WebSocket endpoint that bidirectionally proxies messages
between the frontend and the LiveAvatar session WebSocket.

Frontend → Backend → LiveAvatar:  agent.speak, agent.interrupt,
                                   agent.speak_end, agent.start_listening,
                                   agent.stop_listening, session.keep_alive

LiveAvatar → Backend → Frontend:  session.state_updated,
                                   agent.speak_started, agent.speak_ended

Audio format for agent.speak:
  PCM 16-bit, 24 kHz, mono — Base64 encoded.
  Recommended packet size ≈ 1 second of audio (< 1 MB).
"""

from __future__ import annotations

import asyncio
import json
import logging

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["avatar-ws"])
logger = logging.getLogger(__name__)

# Outbound commands the frontend is allowed to send to LiveAvatar
_ALLOWED_CLIENT_EVENT_TYPES = {
    "agent.speak",
    "agent.interrupt",
    "agent.speak_end",
    "agent.start_listening",
    "agent.stop_listening",
    "session.keep_alive",
}


@router.websocket("/ws/avatar/{liveavatar_ws_url:path}")
async def avatar_websocket_bridge(
    frontend_ws: WebSocket,
    liveavatar_ws_url: str,
) -> None:
    """
    WebSocket bridge: connects the frontend to the LiveAvatar session WebSocket.

    Usage: ws://backend/ws/avatar/<liveavatar_ws_url>

    The frontend's ws_url (returned in /api/avatar/token) should be
    URL-encoded and passed as the path parameter.

    Note: This path-based approach avoids needing a separate connection
    handshake. The frontend opens one WS to the backend, which in turn
    opens one WS to LiveAvatar.
    """
    await frontend_ws.accept()
    logger.info("Frontend WebSocket connected for avatar bridge url=%s", liveavatar_ws_url)

    try:
        # Decode the URL parameter if needed (FastAPI passes it decoded already)
        target_url = liveavatar_ws_url if liveavatar_ws_url.startswith("wss://") else f"wss://{liveavatar_ws_url}"

        async with websockets.connect(target_url) as liveavatar_ws:
            logger.info("Connected to LiveAvatar WebSocket: %s", target_url)

            async def frontend_to_liveavatar() -> None:
                """Relay messages from the frontend to LiveAvatar."""
                try:
                    while True:
                        raw = await frontend_ws.receive_text()
                        try:
                            payload = json.loads(raw)
                            event_type = payload.get("type", "")
                            if event_type not in _ALLOWED_CLIENT_EVENT_TYPES:
                                logger.warning("Blocked unknown event type from frontend: %s", event_type)
                                continue
                        except json.JSONDecodeError:
                            logger.warning("Non-JSON message from frontend, discarding.")
                            continue

                        await liveavatar_ws.send(raw)
                except WebSocketDisconnect:
                    logger.info("Frontend disconnected from avatar bridge.")

            async def liveavatar_to_frontend() -> None:
                """Relay messages from LiveAvatar back to the frontend."""
                try:
                    async for message in liveavatar_ws:
                        if isinstance(message, bytes):
                            await frontend_ws.send_bytes(message)
                        else:
                            await frontend_ws.send_text(message)  # type: ignore[arg-type]
                except websockets.exceptions.ConnectionClosed:
                    logger.info("LiveAvatar WebSocket closed.")

            # Run both directions concurrently until one side disconnects
            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(frontend_to_liveavatar()),
                    asyncio.create_task(liveavatar_to_frontend()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

    except WebSocketDisconnect:
        logger.info("Frontend disconnected before bridge was established.")
    except Exception as exc:
        logger.exception("Unexpected error in avatar WebSocket bridge: %s", exc)
        await frontend_ws.close(code=1011)
