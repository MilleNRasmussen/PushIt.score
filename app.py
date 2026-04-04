import os 
import pymysql
import json
import asyncio
from fastapi import FastAPI, Request, UploadFile, File, Form
from typing import List, Optional
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi.responses import StreamingResponse
from fastapi.responses import JSONResponse
from fastapi import WebSocket 

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
    allow_origins=["*"],
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
    public_token: Optional[str] = None

class UserUpdate(BaseModel):
    name: str | None = None
    has_flic: int | None = None
    button_id: str | None = None


# =====================================================
# SSE EVENT STREAM
# =====================================================

# =====================================================
# SSE CLIENTS
# =====================================================
clients = []

# =====================================================
# SSE EVENT STREAM (FIXET VERSION)
# =====================================================
@app.get("/flic-events")
async def flic_events():
    queue = asyncio.Queue()
    clients.append(queue)
    
    print("🔥 CLIENT CONNECTED")
    print("🔥 TOTAL CLIENTS:", len(clients))
    print("🔥 INSTANCE ID:", os.getenv("RAILWAY_SERVICE_ID"))
    async def event_generator():
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=25)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    # 🔥 keep-alive ping (MEGET vigtigt for mobile/Samsung)
                    yield "data: {}\n\n"
        finally:
            clients.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

# =====================================================
# BROADCAST FUNCTIONS (beholdt)
# =====================================================
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
# MATCH ENDED EVENT (tilføj denne hvis ikke allerede)
# =====================================================
def broadcast_match_end(token):
    print("🔥 BROADCAST CALLED")
    print("🔥 CLIENT COUNT:", len(clients))

    for queue in clients:
        queue.put_nowait({
            "type": "matchEnded",
            "token": token
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
            AND COALESCE(md.LastPoint, mh.StartedAt) < NOW() - INTERVAL 5 MINUTE
        """)

        conn.commit()

    finally:
        conn.close()


# =====================================================
# CLOSE FINISHED MATCHES
# (placeholder så scheduler ikke crasher)
# =====================================================

def close_finished_matches():
    pass


# =====================================================
# USERS
# =====================================================

@app.get("/users")
@app.get("/Users/")
def read_users():

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
        ID as id,
        Navn as name,
        CONCAT('/avatars/', ID, '.png') as avatar,
        IF(ButtonID IS NULL, 0, 1) as has_flic
        FROM Users
    """)

    users = cur.fetchall()

    conn.close()

    return users






@app.get("/player-active-match/{player_id}")
def player_active_match(player_id: int):

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            u.Navn,
            mh.ID as match_id,
            mh.TableID
        FROM MatchPlayers mp
        JOIN MatchHeader mh ON mh.ID = mp.MatchID
        JOIN Users u ON u.ID = mp.PlayerID
        WHERE mp.PlayerID = %s
        AND mh.Status IN ('Live','FinishedPending')  
        LIMIT 1
    """, (player_id,))

    row = cur.fetchone()

    conn.close()

    if row:
        return {
            "active": True,
            "name": row["Navn"],
            "match_id": row["match_id"],
            "table_id": row["TableID"]
        }

    return {
        "active": False
    }








# ---------- CREATE USER + AVATAR ----------

@app.post("/users")
async def create_user(
    name: str = Form(...),
    email: str = Form(...),
    avatar: UploadFile | None = File(None)
):

    conn = get_conn()
    cur = conn.cursor()

    try:

        cur.execute(
            "INSERT INTO Users (Navn, Email) VALUES (%s,%s)",
            (name, email)
        )

        user_id = cur.lastrowid

        if avatar:

            os.makedirs("avatars", exist_ok=True)

            path = f"avatars/{user_id}.png"

            with open(path, "wb") as f:
                f.write(await avatar.read())

        conn.commit()

        return {"status": "ok"}

    except Exception as e:

        conn.rollback()
        return {"error": str(e)}

    finally:

        conn.close()


# ---------- UPDATE USER ----------

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




# ---------- CREATE MATCH ----------
@app.post("/MatchHeaderInsert/")
async def create_match(data: MatchCreate):
    conn = get_conn()
    cur = conn.cursor()

    try:
        # 🔎 check om spillere allerede er i aktiv kamp
        format_strings = ','.join(['%s'] * len(data.players))

        cur.execute(f"""
        SELECT 
               u.Navn,
               mh.ID AS match_id,
               mh.TableID
        FROM MatchPlayers mp
        JOIN MatchHeader mh ON mh.ID = mp.MatchID
        JOIN Users u ON u.ID = mp.PlayerID
        WHERE mp.PlayerID IN ({format_strings})
        AND mh.Status IN ('Live','FinishedPending')
        LIMIT 1
        """, tuple(data.players))

        existing = cur.fetchone()
        if existing:
            return {
                "error": f"{existing['Navn']} spiller allerede på bane {existing['TableID']} (match {existing['match_id']})"
            }

        # 🔥 OPTIONAL TOKEN
        table_id = None

        if data.public_token and data.public_token.strip():
            cur.execute("""
                SELECT ID
                FROM CustomerClub
                WHERE PublicToken = %s
                LIMIT 1
            """, (data.public_token,))
            
            table = cur.fetchone()

            if table:
                table_id = table["ID"]

        # 🔥 INSERT MATCH
        cur.execute("""
        INSERT INTO MatchHeader 
            (TableID, MatchTypeID, MatchGameModeID, PublicToken, Status, StartedAt, Timestamp)
        VALUES (%s, %s, %s, %s, 'Live', NOW(), NOW())
        """, (
            table_id,
            data.match_type_id,
            data.match_gamemode_id,
            data.public_token if data.public_token else None
        ))

        match_id = cur.lastrowid

        if not match_id:
            conn.rollback()
            return {"error": "Match blev ikke oprettet"}

        # 🔥 indsæt spillere
        player_number = 1
        for player_id in data.players:
            cur.execute("""
                INSERT INTO MatchPlayers (MatchID, PlayerID, PlayerNumber, Timestamp)
                VALUES (%s, %s, %s, NOW())
            """, (match_id, player_id, player_number))
            player_number += 1

        conn.commit()
        return {"match_id": match_id}

    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()

# ---------- LIVESCORE ----------
@app.get("/MatchLivescore/{match_id}")
def read_match_livescore(match_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            MatchHeaderID,
            HomeTeamPoint,
            HomeGame,
            HomeSet,
            AwayTeamPoint,
            AwayGame,
            AwaySet
        FROM MatchesScoreActual
        WHERE MatchHeaderID = %s
        LIMIT 1
    """, (match_id,))
    score = cur.fetchone()
    # HENT MATCH STATUS
    cur.execute("""
        SELECT Status
        FROM MatchHeader
        WHERE ID = %s
        LIMIT 1
    """, (match_id,))
    row = cur.fetchone()
    status = row["Status"] if row else "Live"
    cur.execute("""
        SELECT mp.PlayerNumber, u.Navn
        FROM MatchPlayers mp
        JOIN Users u ON u.ID = mp.PlayerID
        WHERE mp.MatchID = %s
        ORDER BY mp.PlayerNumber
    """, (match_id,))
    players = cur.fetchall()
    conn.close()
    if not score:
        score = {
            "MatchHeaderID": match_id,
            "HomeTeamPoint": 0,
            "HomeGame": 0,
            "HomeSet": 0,
            "AwayTeamPoint": 0,
            "AwayGame": 0,
            "AwaySet": 0
        }

    if len(players) == 2:
       home = [players[0]["Navn"]]
       away = [players[1]["Navn"]]
    else:
       home = [p["Navn"] for p in players if p["PlayerNumber"] in (1, 2)]
       away = [p["Navn"] for p in players if p["PlayerNumber"] in (3, 4)]

    
    return {
        "score": score,
        "status": status,
        "homePlayers": home,
        "awayPlayers": away
    }
# =====================================================
# FLIC BUTTONS
# =====================================================

@app.post("/flic-webhook_Home/")
async def flic_webhook_home(request: Request):

    conn = get_conn()
    cur = conn.cursor()

    try:

        try:
            data = await request.json()
        except:
            data = {}

        button_id = request.headers.get("button-serial-number")
        click_type = data.get("click_type", "ButtonSingleClick")

        print("BUTTON:", button_id)
        print("CLICK:", click_type)

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

        cur.callproc(
            "SP_InsertIntoMatchDetailPadel_Home",
            (button_id, click_type)
        )

        conn.commit()

        return {"status": "point"}

    except Exception as e:
        print("ERROR:", e)
        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()

@app.post("/flic-webhook_Away/")
async def flic_webhook_away(request: Request):

    conn = get_conn()
    cur = conn.cursor()

    try:

        # Flic sender ofte ingen JSON body
        try:
            data = await request.json()
        except:
            data = {}

        button_id = request.headers.get("button-serial-number")
        click_type = data.get("click_type", "ButtonSingleClick")

        print("BUTTON:", button_id)
        print("CLICK:", click_type)

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

        cur.callproc(
            "SP_InsertIntoMatchDetailPadel_Away",
            (button_id, click_type)
        )

        conn.commit()

        return {"status": "point"}

    except Exception as e:
        print("ERROR:", e)
        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()



# =====================================================
# Live token
# =====================================================


@app.get("/api/live/{token}")
def get_live_match(token: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT ID, Status
        FROM MatchHeader
        WHERE PublicToken = %s
        AND Status IN ('Live','FinishedPending')
        ORDER BY ID DESC
        LIMIT 1
    """, (token,))

    match = cur.fetchone()
    conn.close()

    if match:
        return {"match_id": match["ID"],
                "status": match["Status"]
               }
    
    return {
         "match_id": None,
         "status": None
    }




# ---------- DELETE POINT ----------
@app.post("/DeleteLastPoint/")
async def delete_last_point(request: Request):

    conn = get_conn()
    cur = conn.cursor()

    try:

        button_id = request.headers.get("button-serial-number")

        if not button_id:
            return {"error": "No button id"}

        cur.callproc("SP_DeleteLastPointPadel", (button_id,))
        conn.commit()

        return {"status": "ok"}

    except Exception as e:

        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()








# =====================================================
# START SCHEDULER
# =====================================================

scheduler = BackgroundScheduler()

scheduler.add_job(
    pause_inactive_matches,
    "interval",
    minutes=1
)

scheduler.add_job(
    close_finished_matches,
    "interval",
    minutes=1
)

scheduler.start()


# =====================================================
# WEBSOCKET
# =====================================================



ws_connections = []

@app.websocket("/ws/livescore")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_connections.append(websocket)

    try:
        while True:
            await websocket.receive_text()  # keep alive
    except:
        ws_connections.remove(websocket)



@app.get("/test-event")
def test_event():
    broadcast_match_end("217")

    print("🔥 INSTANCE ID:", os.getenv("RAILWAY_SERVICE_ID"))
    return {"sent": True}




@app.get("/api/match/{match_id}")
def get_match_token(match_id: int):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT PublicToken
        FROM MatchHeader
        WHERE ID = %s
        LIMIT 1
    """, (match_id,))

    row = cur.fetchone()
    conn.close()

    if row:
        return {"token": row["PublicToken"]}

    return {"token": None}
