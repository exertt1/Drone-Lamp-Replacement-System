from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pathlib import Path

app = FastAPI()

@app.websocket("/prototype")
async def ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_text()
            await ws.send_text(f"эхо: {msg}")
    except WebSocketDisconnect:
        pass

@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = Path("C:/Users/aidar/tupolev/Drone-Lamp-Replacement-System/webapp/frontend/index.html")
    print(html_path)
    html_content = html_path.read_text(encoding='utf-8')
    print(html_content)
    return HTMLResponse(content=html_content)
