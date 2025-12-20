import json
from typing import List, Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_rooms: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        if room_id not in self.active_rooms:
            self.active_rooms[room_id] = []
        self.active_rooms[room_id].append(websocket)
        
        count = len(self.active_rooms[room_id])
        # 廣播系統訊息
        await self.broadcast_system_message(f"新成員加入！目前人數：{count}", room_id)

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_rooms and websocket in self.active_rooms[room_id]:
            self.active_rooms[room_id].remove(websocket)
            if len(self.active_rooms[room_id]) == 0:
                del self.active_rooms[room_id]

    async def broadcast_to_others(self, message: dict, room_id: str, sender_socket: WebSocket):
        if room_id in self.active_rooms:
            for connection in self.active_rooms[room_id]:
                if connection != sender_socket:
                    try:
                        await connection.send_json(message)
                    except:
                        pass

    # ★ 新增：廣播給所有人 (包含自己)，用於集合點更新
    async def broadcast_to_all(self, message: dict, room_id: str):
        if room_id in self.active_rooms:
            for connection in self.active_rooms[room_id]:
                try:
                    await connection.send_json(message)
                except:
                    pass

    async def broadcast_system_message(self, text: str, room_id: str):
        await self.broadcast_to_all({"type": "system", "msg": text}, room_id)

manager = ConnectionManager()

@app.get("/")
async def get():
    with open("map.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await manager.connect(websocket, room_id)
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "ping":
                continue
            
            # 1. 位置更新 (廣播給別人)
            elif msg_type == "location":
                await manager.broadcast_to_others(data, room_id, websocket)
            
            # 2. 狀態氣泡 (廣播給別人)
            elif msg_type == "status":
                await manager.broadcast_to_others(data, room_id, websocket)

            # 3. 設定集合點 (廣播給所有人，包含自己，確保同步)
            elif msg_type == "flag":
                await manager.broadcast_to_all(data, room_id)

    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
    except Exception:
        manager.disconnect(websocket, room_id)