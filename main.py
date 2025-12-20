import json
from typing import List, Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        # 房間管理
        self.active_rooms: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        if room_id not in self.active_rooms:
            self.active_rooms[room_id] = []
        self.active_rooms[room_id].append(websocket)
        
        # ★ Debug 重點：有人加入時，印出 Log 並廣播給所有人
        count = len(self.active_rooms[room_id])
        print(f"[{room_id}] 新連線加入。目前人數: {count}")
        
        # 發送系統訊息給該房間所有人
        await self.broadcast_system_message(f"新成員加入！目前房內人數：{count}", room_id)

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_rooms:
            if websocket in self.active_rooms[room_id]:
                self.active_rooms[room_id].remove(websocket)
                
                count = len(self.active_rooms[room_id])
                print(f"[{room_id}] 連線移除。目前人數: {count}")
                
                # 如果房間空了就刪除
                if count == 0:
                    del self.active_rooms[room_id]
                else:
                    # 還有人的話，通知剩餘的人
                    # 注意：這裡不能用 await，因為 disconnect 不一定是 async，
                    # 為了簡單起見，斷線我們只在後端印 Log，不強制廣播避免錯誤
                    pass

    async def broadcast_to_others(self, message: dict, room_id: str, sender_socket: WebSocket):
        """傳送位置資訊 (排除發送者)"""
        if room_id in self.active_rooms:
            for connection in self.active_rooms[room_id]:
                if connection != sender_socket:
                    try:
                        await connection.send_json(message)
                    except Exception as e:
                        print(f"傳送失敗: {e}")

    async def broadcast_system_message(self, text: str, room_id: str):
        """★ 傳送系統訊息 (給所有人，包含自己)"""
        if room_id in self.active_rooms:
            message = {"type": "system", "msg": text}
            for connection in self.active_rooms[room_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    print(f"系統訊息發送失敗: {e}")

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
            
            # 處理心跳包
            if data.get("type") == "ping":
                continue
                
            # 建構位置資料
            response_data = {
                "type": "location", # 標記這是位置資料
                "lat": data.get("lat"),
                "lng": data.get("lng"),
                "name": data.get("name"),
                "avatar": data.get("avatar")
            }
            
            # 廣播給其他人
            await manager.broadcast_to_others(response_data, room_id, websocket)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
    except Exception as e:
        print(f"WebSocket Error: {e}")
        manager.disconnect(websocket, room_id)