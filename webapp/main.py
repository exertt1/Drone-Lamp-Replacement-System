from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI

@app.websocket("/prototype")
async def ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_text
            await ws.send_text(f"эхо: {msg}")
    except WebSocketDisconnect:
        pass


