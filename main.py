from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes
import os, uuid, json, asyncio

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")  # e.g., https://yourdomain.com/ludo

app = FastAPI()
bot_app = Application.builder().token(BOT_TOKEN).build()

# Active games and players (In-memory, use DB in production)
rooms = {}  # room_id: {"players": [], "chat": []}
connections = {}  # websocket: {"room_id": ..., "name": ..., "color": ...}

# WebSocket endpoint
@app.websocket("/ws/{room_id}/{player_name}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_name: str):
    await websocket.accept()
    color = ["red", "blue", "green", "yellow"][len(rooms.get(room_id, {}).get("players", [])) % 4]
    connections[websocket] = {"room_id": room_id, "name": player_name, "color": color}

    if room_id not in rooms:
        rooms[room_id] = {"players": [], "chat": []}
    rooms[room_id]["players"].append({"name": player_name, "color": color})

    await broadcast(room_id, {"type": "player_joined", "name": player_name, "color": color})

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            if message["type"] == "chat":
                chat_data = {
                    "type": "chat",
                    "name": player_name,
                    "color": color,
                    "text": message["text"]
                }
                rooms[room_id]["chat"].append(chat_data)
                await broadcast(room_id, chat_data)
            elif message["type"] == "move":
                await broadcast(room_id, {
                    "type": "move",
                    "from": player_name,
                    "move": message["move"]
                })
    except WebSocketDisconnect:
        rooms[room_id]["players"] = [p for p in rooms[room_id]["players"] if p["name"] != player_name]
        del connections[websocket]
        await broadcast(room_id, {"type": "player_left", "name": player_name})

# Broadcast to all players in a room
async def broadcast(room_id, message):
    for ws, info in connections.items():
        if info["room_id"] == room_id:
            try:
                await ws.send_text(json.dumps(message))
            except:
                pass

# Telegram bot command to start game
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    room_id = str(uuid.uuid4())[:8]
    join_url = f"{WEBAPP_URL}?room_id={room_id}&name={user.first_name}"
    keyboard = [[InlineKeyboardButton("Play Ludo", web_app=WebAppInfo(url=join_url))]]
    await update.message.reply_text(
        f"Welcome {user.first_name}! Click below to start or share the link with friends.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

bot_app.add_handler(CommandHandler("start", start))

@app.on_event("startup")
async def on_startup():
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()

@app.on_event("shutdown")
async def on_shutdown():
    await bot_app.updater.stop()
    await bot_app.stop()

@app.get("/")
def root():
    return {"status": "Ludo Mini App bot is running"}
