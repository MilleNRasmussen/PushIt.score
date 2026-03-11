import os
import pymysql
import json
import asyncio
from fastapi import FastAPI, Request
from typing import List
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi.responses import StreamingResponse

app = FastAPI()

# ---------- SSE CLIENTS ----------
clients = []

# ---------- CORS ----------
origins = [
    "https://pushit.games",
    "https://www.pushit.games",
    "http://localhost:3000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- DATABASE ----------
def get_conn():
    return pymysql.connect(
        host=os.environ["MYSQLHOST"],
        user=os.environ["MYSQLUSER"],
        password=os.environ["MYSQLPASSWORD"],
        database=os.environ["MYSQLDATABASE"],
        port=int(os.environ["MYSQLPORT"]),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        charset="utf8mb4"
    )

# ---------- MODELS ----------
class MatchCreate(BaseModel):
    match_type_id: int
    match_gamemode_id: int
    players: List[int]

# =====================================================
# SSE EVENT STREAM
# =====================================================

@app.get("/flic-events")
async def flic_events():

    queue = asyncio.Queue()
    clients.append(queue)

    async def event_generator():
        try:
            while True:
                data = await queue.get()
                yield f"data: {json.dumps(data)}\n\n"
        finally:
            clients.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def broadcast_flic(button_id):
    for queue in clients:
        queue.put_nowait({
            "type": "pairing",
            "flic_id": button_id
        })


def broadcast_known(button_id, name):
    for queue in clients:
        queue.put_nowait({
            "type": "known",
            "flic_id": button_id,
            "name": name
        })

# =====================================================
# AUTO PAUSE JOB
# =====================================================

def pause_inactive_matches():
    conn = get_conn()
    cur = conn.cursor()

    try:

        cur.execute("""
            UPDATE MatchHeader mh
            LEFT JOIN (
                SELECT HeaderID, MAX(Timestamp) AS LastPoint
                FROM MatchDetail
                GROUP BY HeaderID
            ) md ON md.HeaderID = mh.ID
            SET mh.Status='SystemPaused',
                PausedAt = NOW()
            WHERE mh.Status='Live'
            AND COALESCE(md.LastPoint, mh.StartedAt) < NOW() - INTERVAL 20 MINUTE
        """)

        print("Paused matches:", cur.rowcount)

        conn.commit()

    finally:
        conn.close()

# ---------- USERS ----------
@app.get("/users")
@app.get("/Users/")
def read_users():

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
        ID as id,
        Navn as name,
        CONCAT('/avatars/', Avatar) as avatar,
        IF(ButtonID IS NULL, 0, 1) as has_flic
        FROM Users
    """)

    users = cur.fetchall()

    conn.close()

    return users

# =====================================================
# UPDATE USER (PAIR FLIC)
# =====================================================

class UserUpdate(BaseModel):
    name: str | None = None
    has_flic: int | None = None
    button_id: str | None = None


@app.put("/users/{user_id}")
async def update_user(user_id: int, data: UserUpdate):

    conn = get_conn()
    cur = conn.cursor()

    try:

        if data.name is not None:
            cur.execute(
                "UPDATE Users SET Navn=%s WHERE ID=%s",
                (data.name, user_id)
            )

        if data.has_flic == 0:
            cur.execute(
                "UPDATE Users SET ButtonID=NULL WHERE ID=%s",
                (user_id,)
            )

        if data.button_id:
            cur.execute(
                "UPDATE Users SET ButtonID=%s WHERE ID=%s",
                (data.button_id, user_id)
            )

        conn.commit()

        return {"status": "ok"}

    except Exception as e:

        conn.rollback()
        return {"error": str(e)}

    finally:

        conn.close()

# =====================================================
# FLIC BUTTONS
# =====================================================

@app.post("/flic-webhook_Home/")
async def flic_webhook_home(request: Request):

    conn = get_conn()
    cur = conn.cursor()

    try:

        button_id = request.headers.get("button-serial-number")

        if not button_id:
            return {"error": "No button id"}

        # find spiller
        cur.execute("""
            SELECT Navn
            FROM Users
            WHERE ButtonID = %s
        """, (button_id,))

        user = cur.fetchone()

        # hvis knappen ikke findes → pairing modal
        if not user:
            broadcast_flic(button_id)
            return {"status": "pairing"}

        # knappen findes → vis hvem den tilhører
        broadcast_known(button_id, user["Navn"])

        # registrer point
        cur.callproc("SP_InsertIntoMatchDetailPadel_Home", (button_id,))
        conn.commit()

        return {"status": "point"}

    except Exception as e:

        conn.rollback()
        return {"error": str(e)}

    finally:

        conn.close()


@app.post("/flic-webhook_Away/")
async def flic_webhook_away(request: Request):

    conn = get_conn()
    cur = conn.cursor()

    try:

        button_id = request.headers.get("button-serial-number")

        if not button_id:
            return {"error": "No button id"}

        cur.execute("""
            SELECT Navn
            FROM Users
            WHERE ButtonID = %s
        """, (button_id,))

        user = cur.fetchone()

        if not user:
            broadcast_flic(button_id)
            return {"status": "pairing"}

        broadcast_known(button_id, user["Navn"])

        cur.callproc("SP_InsertIntoMatchDetailPadel_Away", (button_id,))
        conn.commit()

        return {"status": "point"}

    except Exception as e:

        conn.rollback()
        return {"error": str(e)}

    finally:

        conn.close()

# =====================================================
# START SCHEDULER
# =====================================================

scheduler = BackgroundScheduler()
scheduler.add_job(pause_inactive_matches, "interval", minutes=1)
scheduler.start()
