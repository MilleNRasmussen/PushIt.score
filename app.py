import os 
import pymysql
import json
import asyncio
import time
from fastapi import FastAPI, Request, UploadFile, File, Form
from typing import List, Optional
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi.responses import StreamingResponse
from fastapi.responses import JSONResponse
from fastapi import WebSocket     


from fastapi import APIRouter, Request

router = APIRouter()



hold_state = {
    "home": 0,
    "away": 0
}

COMBO_WINDOW = 1000  # ms

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
    allow_origins=[
        "https://pushit.games",
        "https://www.pushit.games"
    ],
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
    print("PAIR EVENT:", button_id, flush=True)
   
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

def broadcast_corporate(button_id, description):
    print("CORPORATE EVENT:", button_id, description, flush=True)

    for queue in clients:
        queue.put_nowait({
            "type": "corporate",
            "flic_id": button_id,
            "description": description
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
# CLOSE FINISHED MATCHES
# (placeholder så scheduler ikke crasher)
# =====================================================

def close_finished_matches():
    print("🔥 Scheduler tick", flush=True)
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
                        
            UPDATE MatchHeader mh
            LEFT JOIN (
                SELECT
                MatchHeaderID,
                MAX(Timestamp) AS LastPoint
                FROM MatchDetailPoint
                WHERE Deleted = 0
                GROUP BY MatchHeaderID
            ) md ON md.MatchHeaderID = mh.ID

            SET mh.Status = 'Closed'

            WHERE mh.Status IN ( 'Live','Paused','SystemPaused','ManualPaused')
            AND COALESCE(
                  mh.PausedAt,
                  md.LastPoint,
                  mh.StartedAt
                ) < NOW() - INTERVAL 2 MINUTE;

           
        """)
        conn.commit()
    finally:
        conn.close()


# =====================================================
# USERS
# =====================================================




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
            mh.ID as MatchHeaderID,
            COALESCE(msa.HomeTeamPoint, 0) as HomeTeamPoint,
            COALESCE(msa.HomeGame, 0) as HomeGame,
            COALESCE(msa.HomeSet, 0) as HomeSet,
            COALESCE(msa.AwayTeamPoint, 0) as AwayTeamPoint,
            COALESCE(msa.AwayGame, 0) as AwayGame,
            COALESCE(msa.AwaySet, 0) as AwaySet,
            mt.SetDefault,
            mt.name
        FROM MatchHeader mh
        JOIN MatchType mt ON mt.ID = mh.MatchTypeID
        LEFT JOIN MatchesScoreActual msa ON mh.ID = msa.MatchHeaderID
        WHERE mh.ID = %s
        LIMIT 1
    """, (match_id,))
    score = cur.fetchone()

    set_default = score["SetDefault"] if score and "SetDefault" in score else 3
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
        "awayPlayers": away,
        "setDefault": set_default
        
    }



# =====================================================
# HELPER
# =====================================================

def check_button(cur, button_id):
    # Spiller?
    cur.execute("""
        SELECT Navn
        FROM Users
        WHERE ButtonID=%s
        LIMIT 1
    """, (button_id,))
    row = cur.fetchone()
    if row:
        return {
            "type": "player",
            "name": row["Navn"]
        }

    # Corporate?
    cur.execute("""
        SELECT Description, PublicToken
        FROM CorporateButtons
        WHERE ButtonID=%s
        LIMIT 1
    """, (button_id,))
    row = cur.fetchone()
    if row:
        return {
            "type": "corporate",
            "description": row["Description"],
            "public_token": row["PublicToken"]
        }

    return {"type": "unknown"}








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

        button = check_button(cur, button_id)
        print("CHECK:", button, flush=True)

        if button["type"] == "unknown":
            print("CASE: UNKNOWN", flush=True)
            broadcast_flic(button_id)
            return {"status": "pairing"}

        if button["type"] == "player":
            print("CASE: PLAYER", flush=True)
            broadcast_known(button_id, button["name"])

        if button["type"] == "corporate":
            print("CASE: CORPORATE", flush=True)
            broadcast_corporate(
                button_id,
                button["description"]
            )
            return {"status": "corporate"}

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

        button = check_button(cur, button_id)

        if button["type"] == "unknown":
            broadcast_flic(button_id)
            return {"status": "pairing"}

        if button["type"] == "player":
            broadcast_known(button_id, button["name"])

        if button["type"] == "corporate":
            broadcast_corporate(
                button_id,
                button["description"]
            )
            return {"status": "corporate"}


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

    try:

        # ==========================================
        # 1. Er token koblet til en turnering?
        # ==========================================
        cur.execute("""
            SELECT
                TournamentID,
                GroupName
            FROM TournamentGroups
            WHERE ScreenToken = %s
            ORDER BY CreatedAt DESC
            LIMIT 1
        """, (token,))

        group = cur.fetchone()

        # ==========================================
        # TURNERING
        # ==========================================
        if group:

            tournament_id = group["TournamentID"]
            group_name = group["GroupName"]
            group_no = ord(group_name.upper()) - 64

            # Find aktiv turneringskamp
            cur.execute("""
                SELECT
                    mh.ID,
                    mh.Status
                FROM MatchHeader mh
                JOIN Tournaments t
                    ON t.ID = mh.TournamentID
                WHERE mh.PublicToken = %s
                AND mh.TournamentID = %s
                AND mh.Status IN (
                    'Live',
                    'FinishedPending',
                    'SystemPaused'
                )
                AND t.Status <> 'Closed'
                ORDER BY mh.ID DESC
                LIMIT 1
            """, (
                token,
                tournament_id
            ))

            match = cur.fetchone()

            if match:
                return {
                    "match_id": match["ID"],
                    "status": match["Status"]
                }

            # ==========================================
            # Find næste kamp der mangler MatchID
            # ==========================================
            cur.execute("""
                SELECT
                    ID,
                    HomeTeamID,
                    AwayTeamID
                FROM TournamentMatches
                WHERE TournamentID = %s
                AND GroupNo = %s
                AND MatchID IS NULL
                ORDER BY Round, ID
                LIMIT 1
            """, (
                tournament_id,
                group_no
            ))

            tm = cur.fetchone()

            if not tm:
                return {
                    "match_id": None,
                    "status": "group_finished"
                }

            # ==========================================
            # Hent sport
            # ==========================================
            cur.execute("""
                SELECT Sport
                FROM Tournaments
                WHERE ID = %s
                LIMIT 1
            """, (tournament_id,))

            tournament = cur.fetchone()

            if not tournament:
                return {
                    "match_id": None,
                    "status": "tournament_missing"
                }

            match_type_id = tournament["Sport"]

            # ==========================================
            # Opret MatchHeader
            # ==========================================
            cur.execute("""
                INSERT INTO MatchHeader
                (
                    MatchTypeID,
                    MatchGameModeID,
                    PublicToken,
                    TournamentID,
                    Status,
                    StartedAt,
                    Timestamp
                )
                VALUES
                (
                    %s,
                    2,
                    %s,
                    %s,
                    'Live',
                    NOW(),
                    NOW()
                )
            """, (
                match_type_id,
                token,
                tournament_id
            ))

            match_id = cur.lastrowid

            # hjemmehold
            player_no = 1

            cur.execute("""
                SELECT PlayerID
                FROM TournamentTeamPlayers
                WHERE TournamentTeamID = %s
                ORDER BY Position
            """, (tm["HomeTeamID"],))

            for p in cur.fetchall():
                cur.execute("""
                    INSERT INTO MatchPlayers
                    (
                        MatchID,
                        PlayerID,
                        PlayerNumber,
                        Timestamp
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        NOW()
                    )
                """, (
                    match_id,
                    p["PlayerID"],
                    player_no
                ))
                player_no += 1

            # udehold
            cur.execute("""
                SELECT PlayerID
                FROM TournamentTeamPlayers
                WHERE TournamentTeamID = %s
                ORDER BY Position
            """, (tm["AwayTeamID"],))

            for p in cur.fetchall():
                cur.execute("""
                    INSERT INTO MatchPlayers
                    (
                        MatchID,
                        PlayerID,
                        PlayerNumber,
                        Timestamp
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        NOW()
                    )
                """, (
                    match_id,
                    p["PlayerID"],
                    player_no
                ))
                player_no += 1

            cur.execute("""
                UPDATE TournamentMatches
                SET MatchID = %s
                WHERE ID = %s
            """, (
                match_id,
                tm["ID"]
            ))

            conn.commit()

            return {
                "match_id": match_id,
                "status": "Live",
                "auto_created": True
            }

        # ==========================================
        # ALMINDELIGE KAMPE
        # ==========================================
        cur.execute("""
            SELECT
                ID,
                Status
            FROM MatchHeader
            WHERE PublicToken = %s
            AND TournamentID IS NULL
            AND Status IN (
                'Live',
                'FinishedPending',
                'SystemPaused'
            )
            ORDER BY ID DESC
            LIMIT 1
        """, (token,))

        match = cur.fetchone()

        if match:
            return {
                "match_id": match["ID"],
                "status": match["Status"]
            }

        return {
            "match_id": None,
            "status": None
        }

    except Exception as e:
        conn.rollback()
        return {
            "error": str(e)
        }

    finally:
        conn.close()























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
    close_finished_matches,
    "interval",
    minutes=1
)

scheduler.start()

print("✅ Scheduler started", flush=True)
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


# ===============================
# HELPER
# ===============================



def get_match_data(cur, button_id):

    # =====================================
    # NORMAL PLAYER FLIC
    # =====================================
    cur.execute("""
        SELECT
            mh.ID as match_id,
            mp.PlayerNumber,
            (
                SELECT COUNT(*)
                FROM MatchPlayers
                WHERE MatchID = mh.ID
            ) as total_players
        FROM Users u
        JOIN MatchPlayers mp ON mp.PlayerID = u.ID
        JOIN MatchHeader mh ON mh.ID = mp.MatchID
        WHERE u.ButtonID = %s
        AND mh.Status IN ('Live','Paused','ManualPaused','FinishedPending')
        ORDER BY mh.ID DESC
        LIMIT 1
    """, (button_id,))

    row = cur.fetchone()

    if row:

        if row["total_players"] == 2:
            is_home = row["PlayerNumber"] == 1
        else:
            is_home = row["PlayerNumber"] in (1, 2)

        return {
            "match_id": row["match_id"],
            "team": "home" if is_home else "away"
        }

    # =====================================
    # TOURNAMENT FLIC
    # =====================================
    cur.execute("""
        SELECT
            mh.ID as match_id,
            CASE
                WHEN tg.HomeFlicID = %s THEN 'home'
                ELSE 'away'
            END as team
        FROM TournamentGroups tg
        JOIN MatchHeader mh
            ON mh.PublicToken = tg.ScreenToken
        WHERE (
            tg.HomeFlicID = %s
            OR tg.AwayFlicID = %s
        )
        AND mh.Status IN (
            'Live',
            'Paused',
            'ManualPaused',
            'FinishedPending'
        )
        ORDER BY mh.ID DESC
        LIMIT 1
    """, (
        button_id,
        button_id,
        button_id
    ))

    row = cur.fetchone()

    if row:
        return {
            "match_id": row["match_id"],
            "team": row["team"]
        }

    return None
















@app.post("/webhook_point")
async def webhook_point(request: Request):
    conn = get_conn()
    cur = conn.cursor()

    try:
        print("ENDPOINT: POINT", flush=True)

        button_id = request.headers.get("button-serial-number")

        if not button_id:
            return {"error": "No button id"}

        # =====================================
        # 1. FIND MATCH (SPILLER ELLER TURNERING)
        # =====================================
        data = get_match_data(cur, button_id)

        print("MATCH DATA:", data, flush=True)

        if data:
            is_home = 1 if data["team"] == "home" else 0

            print(
                "SP_InsertScore",
                button_id,
                is_home,
                flush=True
            )

            cur.callproc(
                "SP_InsertScore",
                (
                    button_id,
                    "single",
                    is_home
                )
            )

            conn.commit()

            return {
                "status": "ok"
            }

        # =====================================
        # 2. FINDES KNAPPEN PÅ EN BRUGER?
        # =====================================
        cur.execute("""
            SELECT Navn
            FROM Users
            WHERE ButtonID = %s
        """, (button_id,))

        user = cur.fetchone()

        print("USER:", user, flush=True)

        if user:
            broadcast_known(
                button_id,
                user["Navn"]
            )

            return {
                "status": "known_no_match"
            }

        cur.execute("""
            SELECT Description
            FROM CorporateButtons
            WHERE ButtonID = %s
            LIMIT 1
        """, (button_id,))

        corp = cur.fetchone()
        print("CORPORATE:", corp, flush=True)

        if corp:
            broadcast_corporate(
                button_id,
                corp["Description"]
            )
            return {
                "status": "corporate"
            }

        # =====================================
        # 3. UKENDT KNAP -> PAIRING
        # =====================================
        print("BROADCAST: pairing", flush=True)

        broadcast_flic(button_id)

        return {
            "status": "pairing"
        }

    except Exception as e:
        print("ERROR:", str(e), flush=True)

        conn.rollback()

        return {
            "error": str(e)
        }

    finally:
        conn.close()


@app.post("/webhook_delete_point")
async def webhook_delete_point(request: Request):
    conn = get_conn()
    cur = conn.cursor()
    try:
        button_id = request.headers.get("button-serial-number")
        if not button_id:
            return {"error": "No button id"}

        data = get_match_data(cur, button_id)
        if not data:
            cur.execute("""
                SELECT Navn
                FROM Users
                WHERE ButtonID = %s
            """, (button_id,))
            user = cur.fetchone()
            if user:
                broadcast_known(button_id, user["Navn"])
                return {"status": "known"}
            broadcast_flic(button_id)
            return {"status": "pairing"}

        print("MATCH ID:", data["match_id"], flush=True)
        print("ENDPOINT: DELETE", flush=True)

        team = data["team"]  # 🔥 vigtigt: "home" eller "away"

        cur.execute("""
            UPDATE MatchDetailPoint
            SET Deleted = 1
            WHERE ID = (
                SELECT ID FROM (
                    SELECT ID
                    FROM MatchDetailPoint
                    WHERE MatchHeaderID = %s
                    AND Deleted = 0
                    AND (
                        (%s = 'home' AND HomeTeamPoint > AwayTeamPoint)
                        OR
                        (%s = 'away' AND AwayTeamPoint > HomeTeamPoint)
                    )
                    ORDER BY ID DESC
                    LIMIT 1
                ) as tmp
            )
        """, (data["match_id"], team, team))

        conn.commit()
        return {"status": "ok"}

    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()

    




@app.post("/webhook_end_game")
async def webhook_end_game(request: Request):
    print("WEBHOOK HIT", flush=True)

    conn = get_conn()
    cur = conn.cursor()

    try:
        button_id = request.headers.get("button-serial-number")
        if not button_id:
            return {"error": "No button id"}

        data = get_match_data(cur, button_id)
        if not data:
            return {"status": "no_match"}

        match_id = data["match_id"]
        team = data["team"]  # "home" / "away"
        now = int(time.time() * 1000)

        print("TEAM:", team, flush=True)

        # 🔥 reset gammel state
        if now - hold_state["home"] > COMBO_WINDOW:
            hold_state["home"] = 0
        if now - hold_state["away"] > COMBO_WINDOW:
            hold_state["away"] = 0

        # 🔥 registrer hold
        hold_state[team] = now

        # 🔥 hent status
        cur.execute("""
            SELECT Status, PublicToken
            FROM MatchHeader
            WHERE ID = %s
        """, (match_id,))
        row = cur.fetchone()

        if not row:
            return {"error": "Match not found"}

        current_status = row["Status"]
        token = row["PublicToken"]

        print("STATUS BEFORE:", current_status, flush=True)
        print("STATE:", hold_state, flush=True)

        # 💥 COMBO → CLOSE MATCH
        if (
            hold_state["home"]
            and hold_state["away"]
            and abs(hold_state["home"] - hold_state["away"]) < COMBO_WINDOW
        ):
            print("COMBO TRIGGERED → CLOSE", flush=True)

            cur.execute("""
                UPDATE MatchHeader
                SET Status = 'Closed'
                WHERE ID = %s
            """, (match_id,))

            
            cur.execute("""
                SELECT TournamentID
                FROM MatchHeader
                WHERE ID = %s
            """, (match_id,))

            row = cur.fetchone()

            if row and row["TournamentID"]:

                tournament_id = row["TournamentID"]

                cur.execute("""
                    SELECT COUNT(*) AS Remaining
                    FROM TournamentMatches tm
                    JOIN MatchHeader mh
                        ON mh.ID = tm.MatchID
                    WHERE tm.TournamentID = %s
                    AND tm.Stage = 'group'
                    AND (
                         mh.ID IS NULL
                         OR mh.Status <> 'Closed'
                    )
                """, (tournament_id,))

                remaining = cur.fetchone()["Remaining"]

                if remaining == 0:
                    generate_placement_matches(cur, tournament_id)

            conn.commit()




















            

            # 🔥 NEW: generate KPI cache
            calculate_kpi(match_id)
            
            # reset
            hold_state["home"] = 0
            hold_state["away"] = 0

            # broadcast close
            if token:
                broadcast_match_end(token)

            return {"status": "closed"}

        # 🔥 NORMAL TOGGLE (pause/resume)
        if current_status in ["Paused", "ManualPaused", "SystemPaused"]:
            new_status = "Live"
        else:
            new_status = "Paused"

        print("UPDATING TO:", new_status, flush=True)

        cur.execute("""
            UPDATE MatchHeader
            SET Status = %s
            WHERE ID = %s
        """, (new_status, match_id))

        conn.commit()

        # 🔥 broadcast pause/resume
        for queue in clients:
            queue.put_nowait({
                "type": "matchStatusChanged",
                "match_id": match_id,
                "status": new_status
            })

        return {"status": new_status}

    except Exception as e:
        print("ERROR:", str(e), flush=True)
        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()







@app.get("/matchtypes")
def get_matchtypes():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT ID, Name, PlayerPerTeamDefault FROM MatchType")

    rows = cur.fetchall()
    conn.close()

    return rows




@app.get("/recent-matches")
def recent_matches():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT ID, MatchTypeID
            FROM MatchHeader
            WHERE Status = 'Closed'
            ORDER BY ID DESC
            LIMIT 20
        """)
        matches = cur.fetchall()
        result = []

        for m in matches:
            match_id = m["ID"]
            match_type_id = m["MatchTypeID"]

            # 🏓 BORDTENNIS (FIXED)
            if match_type_id == 6:
                cur.execute("""
                    SELECT 
                        HomeTeamPoint,
                        AwayTeamPoint,
                        ClosedRow
                    FROM MatchDetailPoint
                    WHERE MatchHeaderID = %s
                    AND Deleted = 0
                    ORDER BY ID
                """, (match_id,))

                rows = cur.fetchall()
                sets_formatted = []

                # 🔥 find set = rækken før ClosedRow
                for i in range(1, len(rows)):
                    if rows[i]["ClosedRow"] == 1:
                        prev = rows[i - 1]
                        sets_formatted.append(
                            f"{prev['HomeTeamPoint']}-{prev['AwayTeamPoint']}"
                        )

                home_sets = sum(
                    1 for s in sets_formatted
                    if int(s.split("-")[0]) > int(s.split("-")[1])
                )

                away_sets = sum(
                    1 for s in sets_formatted
                    if int(s.split("-")[1]) > int(s.split("-")[0])
                )

            # 🎾 PADEL / TENNIS (UÆNDRET)
            else:
                cur.execute("""
                    SELECT 
                        SetNo,
                        HomeGames,
                        AwayGames
                    FROM MatchSetScore
                    WHERE MatchHeaderID = %s
                    ORDER BY SetNo
                """, (match_id,))

                sets = cur.fetchall()


                home_sets = 0
                away_sets = 0

                for s in sets:
                    home = s["HomeGames"]
                    away = s["AwayGames"]

                    if home > away:
                        home_sets += 1
                    elif away > home:
                        away_sets += 1
                    else:
                        # 🔥 6-6 → afgøres af tiebreak
                        cur.execute(
                            "SELECT HomeTeamPoint, AwayTeamPoint FROM MatchDetailPoint WHERE MatchHeaderID = %s AND Deleted = 0 AND HomeGame = 6 AND AwayGame = 6 ORDER BY ID DESC LIMIT 1",
                            (match_id,)
                        )
                        tb = cur.fetchone()

                        if tb:
                            if tb["HomeTeamPoint"] > tb["AwayTeamPoint"]:
                                home_sets += 1
                            else:
                                away_sets += 1














                

                sets_formatted = []

                for s in sets:
                    score = str(s["HomeGames"]) + "-" + str(s["AwayGames"])

                    if s["HomeGames"] == 6 and s["AwayGames"] == 6:
                        cur.execute(
                            "SELECT HomeTeamPoint, AwayTeamPoint FROM MatchDetailPoint WHERE MatchHeaderID = %s AND Deleted = 0 AND HomeGame = 6 AND AwayGame = 6 AND ClosedRow = 0 ORDER BY ID DESC LIMIT 1",
                            (match_id,)
                        )
                        tb = cur.fetchone()

                        if tb:
                            home_tb = tb["HomeTeamPoint"] if tb["HomeTeamPoint"] else 0
                            away_tb = tb["AwayTeamPoint"] if tb["AwayTeamPoint"] else 0
                            score = score + " (" + str(home_tb) + "-" + str(away_tb) + ")"

                    sets_formatted.append(score)













            
            # 🔥 timestamp
            cur.execute("""
                SELECT Timestamp
                FROM MatchDetailPoint
                WHERE MatchHeaderID = %s
                AND Deleted = 0
                ORDER BY ID DESC
                LIMIT 1
            """, (match_id,))

            last = cur.fetchone() or {}

            # 🔥 spillere
            cur.execute("""
                SELECT mp.PlayerNumber, u.Navn, mp.PlayerID
                FROM MatchPlayers mp
                JOIN Users u ON u.ID = mp.PlayerID
                WHERE mp.MatchID = %s
                ORDER BY mp.PlayerNumber
            """, (match_id,))

            players = cur.fetchall()

            if len(players) == 2:
                home = [{
                    "name": players[0]["Navn"],
                    "playerid": players[0]["PlayerID"]
                }]
                away = [{
                    "name": players[1]["Navn"],
                    "playerid": players[1]["PlayerID"]
                }]
            else:
                home = [
                    {
                        "name": p["Navn"],
                        "playerid": p["PlayerID"]
                    }
                    for p in players if p["PlayerNumber"] in (1, 2)
                ]

                away = [
                    {
                        "name": p["Navn"],
                        "playerid": p["PlayerID"]
                    }
                    for p in players if p["PlayerNumber"] in (3, 4)
                ]

            result.append({
                "id": match_id,
                "homePlayers": home,
                "awayPlayers": away,
                "homeSet": home_sets,
                "awaySet": away_sets,
                "sets": sets_formatted,
                "playedAt": last.get("Timestamp") or "",
                "matchTypeId": match_type_id
            })

        return result

    except Exception as e:
        print("ERROR recent-matches:", e, flush=True)
        return {"error": str(e)}

    finally:
        conn.close()











@app.get("/match-points/{match_id}")
def get_match_points(match_id: int):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
              MatchHeaderID,
              SetNo,
              GameNo,
              HomeTeamPoint AS homePoint ,
              AwayTeamPoint AS awayPoint,
              Winner,
              HomeGame AS homeGame,
              Awaygame AS awayGame,
              GameType AS gameType
            FROM MatchGamesSet
            WHERE MatchHeaderID = %s
            ORDER BY SetNo, GameNo;
        """, (match_id,))
        rows = cur.fetchall()

        sets = {}

        for r in rows:
            # ✅ brug view felter (IKKE HomeSet/HomeGame)
            set_no = r["SetNo"]
            game_no = r["GameNo"]

            if set_no not in sets:
                sets[set_no] = {}

            if game_no not in sets[set_no]:
                sets[set_no][game_no] = []

            sets[set_no][game_no].append({
                # ❌ ID og Timestamp findes ikke i view → fjernet
                "team": r["Winner"],  # ✅ brug direkte fra view
                "homePoint": r["homePoint"],
                "awayPoint": r["awayPoint"],
                "homeGame": r["homeGame"],
                "awayGame": r["awayGame"],
                "gameType": r["gameType"]
                })

        return sets

    except Exception as e:
        print("ERROR:", e)
        return {"error": str(e)}

    finally:
        conn.close()


@app.get("/match-timeline/{match_id}")
def get_match_timeline(match_id: int):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            HomeSet,
            AwaySet,
            HomePoint,
            AwayPoint
        FROM MatchDetailPoint
        WHERE MatchHeaderID = %s
        AND Deleted = 0
        ORDER BY ID ASC
    """, (match_id,))

    rows = cur.fetchall()

    sets = {}


    conn.close()
    return {
        "points": rows
    }


@app.get("/match-points-tabletennis/{match_id}")
def get_tabletennis_points(match_id: int):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            HomeSet,
            HomeTeamPoint,
            AwayTeamPoint,
            ClosedRow
        FROM MatchDetailPoint
        WHERE MatchHeaderID = %s
        AND Deleted = 0
        ORDER BY ID
    """, (match_id,))

    rows = cur.fetchall()

    sets = {}
    current_set = 1

    for r in rows:
        if current_set not in sets:
            sets[current_set] = {}

        # 🔥 fake game = 1 (så frontend virker)
        if 1 not in sets[current_set]:
            sets[current_set][1] = []

        sets[current_set][1].append({
            "team": 1 if r["HomeTeamPoint"] > r["AwayTeamPoint"] else 0,
            "homePoint": r["HomeTeamPoint"],
            "awayPoint": r["AwayTeamPoint"]
        })

        if r["ClosedRow"] == 1:
            current_set += 1

    return sets



    

# =====================================================
# KPI
# =====================================================

@app.get("/KPI")
def read_KPI():

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
        Name,
        KPI 
        FROM SystemStatistics;
    """)

    KPI = cur.fetchall()

    conn.close()

    return KPI








class TeamInput(BaseModel):
    name: str
    players: list[int]

class TournamentCreate(BaseModel):
    name: str
    matchTypeId: int 
    mode: str
    matchType: str
    duration: Optional[int] = None
    rounds: Optional[int] = None
    players: Optional[List[int]] = None
    teams: Optional[List[TeamInput]] = None
    createdBy: int
    groupCount: Optional[int] = 2


@app.post("/tournaments")
def create_tournament(data: TournamentCreate):
    conn = get_conn()
    cur = conn.cursor()
    try:
        # 🔥 1. GET matchtype info
        cur.execute("""
            SELECT PlayerPerTeamDefault
            FROM MatchType
            WHERE ID = %s
        """, (data.matchTypeId,))
        
        mt = cur.fetchone()
        if not mt:
            return {"error": "Invalid match type"}

        players_per_team = mt["PlayerPerTeamDefault"]
        group_count = data.groupCount or 2

        # 🔥 VALIDATION
        if players_per_team == 1 and not data.players:
            return {"error": "players missing"}

        if players_per_team > 1 and not data.teams:
            return {"error": "teams missing"}

        # 🔥 2. CREATE TOURNAMENT
        cur.execute("""
            INSERT INTO Tournaments (
                Name,
                Sport,
                Mode,
                MatchType,
                MatchDurationMinutes,
                TotalRounds,
                Status,
                CreatedBy,
                CreatedAt,
                GroupCount
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s, NOW(), %s)
        """, (
            data.name,
            data.matchTypeId,
            data.mode,
            data.matchType,
            data.duration,
            data.rounds,
            data.createdBy,
            group_count
        ))

        tournament_id = cur.lastrowid

        # =====================================================
        # 🔥 SINGLE PLAYER MODE
        # =====================================================
        if players_per_team == 1:
            for player_id in data.players:
                cur.execute("""
                    INSERT INTO TournamentPlayers (TournamentId, PlayerId)
                    VALUES (%s, %s)
                """, (tournament_id, player_id))

        # =====================================================
        # 🔥 TEAM MODE
        # =====================================================
        else:
            team_ids = []

            for i, team in enumerate(data.teams):
                cur.execute("""
                    INSERT INTO TournamentTeams (TournamentID, Name, Seed)
                    VALUES (%s, %s, %s)
                """, (
                    tournament_id,
                    team.name,
                    i + 1
                ))

                team_id = cur.lastrowid
                team_ids.append(team_id)

                for pos, player_id in enumerate(team.players):
                    cur.execute("""
                        INSERT INTO TournamentTeamPlayers 
                        (TournamentTeamID, PlayerID, Position)
                        VALUES (%s, %s, %s)
                    """, (team_id, player_id, pos + 1))

            generate_groups_and_matches(cur, tournament_id, team_ids, group_count)

        conn.commit()

        return {
            "success": True,
            "tournamentId": tournament_id
        }

    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()









@app.get("/api/test-kpi/{match_id}")
def test_kpi(match_id: int):
    conn = get_conn()
    cur = conn.cursor()

    try:
        calculate_kpi(match_id)

        cur.execute("""
            SELECT *
            FROM MatchKpiCache
            WHERE MatchHeaderID = %s
        """, (match_id,))

        row = cur.fetchone()

        if not row:
            return {"error": "No KPI data"}

        return row

    finally:
        conn.close()



@app.post("/flic-webhook-tournament")
async def flic_webhook_tournament(request: Request):
    conn = get_conn()
    cur = conn.cursor()

    try:
        try:
            data = await request.json()
        except:
            data = {}

        button_id = request.headers.get("button-serial-number")

        if not button_id:
            return {"error": "No button id"}

        # 🔥 find aktiv turnering (eller hardcode hvis kun 1)
        cur.execute("""
            SELECT ID
            FROM Tournaments
            WHERE Status = 'active'
            ORDER BY ID DESC
            LIMIT 1
        """)
        t = cur.fetchone()

        if not t:
            return {"status": "no_active_tournament"}

        tournament_id = t["ID"]

        # 🔥 find group + team
        cur.execute("""
            SELECT 
                GroupName,
                CASE 
                    WHEN HomeFlicID = %s THEN 'home'
                    WHEN AwayFlicID = %s THEN 'away'
                END as team
            FROM TournamentFlics
            WHERE TournamentID = %s
            AND (HomeFlicID = %s OR AwayFlicID = %s)
            LIMIT 1
        """, (button_id, button_id, tournament_id, button_id, button_id))

        mapping = cur.fetchone()

        if not mapping:
            return {"status": "unknown_flic"}

        group_name = mapping["GroupName"]
        team = mapping["team"]

        # 🔥 find aktiv kamp i gruppen
        cur.execute("""
            SELECT ID
            FROM MatchHeader
            WHERE GroupName = %s
            AND Status = 'Live'
            ORDER BY ID DESC
            LIMIT 1
        """, (group_name,))

        match = cur.fetchone()

        if not match:
            return {"status": "no_active_match"}

        is_home = 1 if team == "home" else 0

        cur.callproc(
            "SP_InsertScore",
            (button_id, "single", is_home)
        )

        conn.commit()

        return {"status": "ok"}

    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()


# =====================================================
# TOKENS
# =====================================================
@app.get("/api/tokens")
def get_tokens():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT PublicToken,
                   DefaultMatchTypeID,
                   ClubName
            FROM CustomerClub
            WHERE IsActive = 1
        """)
        
        rows = cur.fetchall()

        return rows

    except Exception as e:
        print("ERROR tokens:", e)
        return []
    finally:
        conn.close()


def generate_groups_and_matches(cur, tournament_id, team_ids, group_count):
    import random

    random.shuffle(team_ids)

    groups = [[] for _ in range(group_count)]

    for i, team in enumerate(team_ids):
        groups[i % group_count].append(team)

    def round_robin(teams, group_no):
        teams = teams[:]

        if len(teams) % 2:
            teams.append(None)

        rounds = len(teams) - 1

        for round_no in range(rounds):

            for i in range(len(teams) // 2):
                home = teams[i]
                away = teams[-1 - i]
            
                if home and away:
                    cur.execute("""
                        INSERT INTO TournamentMatches (
                            TournamentID,
                            HomeTeamID,
                            AwayTeamID,
                            Round,
                            Stage,
                            GroupNo,
                            Status,
                            CreatedAt
                        )
                       VALUES (%s, %s, %s, %s, %s, %s, 'pending', NOW())
                   """, (
                       tournament_id,
                       home,
                       away,
                       round_no + 1,
                       "group",
                       group_no
                   ))
          
            teams = (
                [teams[0]]
                + [teams[-1]]
                + teams[1:-1]
          )





   

    for index, group in enumerate(groups):
        group_no = index + 1
        group_name = chr(65 + index)

        round_robin(group, group_no)

        for team_id in group:
            cur.execute("""
                UPDATE TournamentTeams
                SET GroupName = %s
                WHERE ID = %s
            """, (group_name, team_id))


@app.get("/tournaments")
def get_tournaments():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            ID as id,
            Name as name
        FROM Tournaments
        ORDER BY ID DESC
    """)

    rows = cur.fetchall()
    conn.close()

    return rows


@app.get("/tournaments/{tournament_id}/plan")
def get_tournament_plan(tournament_id: int):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        
        SELECT
            tm.ID,
            tm.GroupNo,
            tm.MatchID,
            tm.Stage,
            tm.Round,
            ht.Name AS HomeTeam,
            at.Name AS AwayTeam,
            msa.HomeTeamPoint AS HomeScore,
            msa.AwayTeamPoint AS AwayScore,
            mh.Status
        FROM TournamentMatches tm
        LEFT JOIN TournamentTeams ht
        ON ht.ID = tm.HomeTeamID
        LEFT JOIN TournamentTeams at
        ON at.ID = tm.AwayTeamID
        LEFT JOIN MatchesScoreActual msa
        ON msa.MatchHeaderID = tm.MatchID
        LEFT JOIN MatchHeader mh
        ON mh.ID = tm.MatchID
        WHERE tm.TournamentID = %s
        ORDER BY tm.GroupNo, tm.Round, tm.ID


        
    """, (tournament_id,))

    rows = cur.fetchall()
    conn.close()

    return rows


class TournamentGroupCreate(BaseModel):
    group: str
    screenToken: str | None = None
    homeFlic: str | None = None
    awayFlic: str | None = None


@app.post("/tournaments/{tournament_id}/groups")
def create_tournament_groups(
    tournament_id: int,
    groups: list[TournamentGroupCreate]
):
    conn = get_conn()
    cur = conn.cursor()

    try:
        for g in groups:
            cur.execute("""
                INSERT INTO TournamentGroups (
                    TournamentID,
                    GroupName,
                    ScreenToken,
                    HomeFlicID,
                    AwayFlicID
                )
                VALUES (%s,%s,%s,%s,%s)
            """, (
                tournament_id,
                g.group,
                g.screenToken,
                g.homeFlic,
                g.awayFlic
            ))

        conn.commit()

        return {"success": True}

    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()



@app.get("/tournaments/{tournament_id}/full-view")
def get_full_view_v2(tournament_id: int):
    conn = get_conn()
    cur = conn.cursor()

    # Hold
    cur.execute("""
        SELECT
            ID as TeamID,
            Name,
            GroupName
        FROM TournamentTeams
        WHERE TournamentID = %s
    """, (tournament_id,))

    teams = cur.fetchall()

    stats = {}

    for t in teams:
        stats[t["TeamID"]] = {
            "TeamID": t["TeamID"],
            "Name": t["Name"],
            "GroupName": t["GroupName"],
            "Played": 0,
            "Wins": 0,
            "Draws": 0,
            "GoalsScored": 0,
            "GoalsAgainst": 0,
            "Points": 0
        }

    # Spillede kampe
    cur.execute("""
        SELECT
            tm.HomeTeamID,
            tm.AwayTeamID,
            msa.HomeTeamPoint,
            msa.AwayTeamPoint
        FROM TournamentMatches tm
        JOIN MatchHeader mh
            ON mh.ID = tm.MatchID
        JOIN MatchesScoreActual msa
            ON msa.MatchHeaderID = mh.ID
        WHERE tm.TournamentID = %s
        AND mh.Status IN ('Finished','FinishedPending','Closed')
    """, (tournament_id,))

    matches = cur.fetchall()

    for m in matches:

        home = stats.get(m["HomeTeamID"])
        away = stats.get(m["AwayTeamID"])

        if not home or not away:
            continue

        home_score = m["HomeTeamPoint"] or 0
        away_score = m["AwayTeamPoint"] or 0

        home["Played"] += 1
        away["Played"] += 1

        home["GoalsScored"] += home_score
        home["GoalsAgainst"] += away_score

        away["GoalsScored"] += away_score
        away["GoalsAgainst"] += home_score

        if home_score > away_score:
            home["Wins"] += 1
            home["Points"] += 2

        elif away_score > home_score:
            away["Wins"] += 1
            away["Points"] += 2

        else:
            home["Draws"] += 1
            away["Draws"] += 1

            home["Points"] += 1
            away["Points"] += 1

    groups = {}

    for team in stats.values():

        group = team["GroupName"] or "A"

        if group not in groups:
            groups[group] = []

        groups[group].append(team)

    # Sortering
    for group in groups:

        groups[group].sort(
            key=lambda t: (
                t["Points"],
                t["GoalsScored"] - t["GoalsAgainst"],
                t["GoalsScored"]
            ),
            reverse=True
        )

    conn.close()

    return {
        "groups": groups,
        "finals": []
    }



def generate_placement_matches(cur, tournament_id):


    # Undgå dobbelt-oprettelse
    cur.execute("""
        SELECT COUNT(*) AS Cnt
        FROM TournamentMatches
        WHERE TournamentID = %s
        AND Stage = 'placement'
    """, (tournament_id,))

    if cur.fetchone()["Cnt"] > 0:
        return
    
    groups = get_group_standings(cur, tournament_id)

    if "A" not in groups or "B" not in groups:
        return

    groupA = groups["A"]
    groupB = groups["B"]

    max_matches = min(len(groupA), len(groupB))

    for i in range(max_matches):

        # Finalen får højeste round
        round_no = max_matches - i

        group_no = 1 if i % 2 == 0 else 2
        
        cur.execute("""
            INSERT INTO TournamentMatches (
                TournamentID,
                HomeTeamID,
                AwayTeamID,
                Round,
                GroupNo,
                Stage,
                Status,
                CreatedAt
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                'placement',
                'pending',
                NOW()
            )
        """, (
            tournament_id,
            groupA[i]["TeamID"],
            groupB[i]["TeamID"],
            round_no,
            group_no
        ))

def get_group_standings(cur, tournament_id):

    cur.execute("""
        SELECT
            ID as TeamID,
            Name,
            GroupName
        FROM TournamentTeams
        WHERE TournamentID = %s
    """, (tournament_id,))

    teams = cur.fetchall()

    stats = {}

    for t in teams:
        stats[t["TeamID"]] = {
            "TeamID": t["TeamID"],
            "Name": t["Name"],
            "GroupName": t["GroupName"],
            "Played": 0,
            "Wins": 0,
            "Draws": 0,
            "GoalsScored": 0,
            "GoalsAgainst": 0,
            "Points": 0
        }

    cur.execute("""
        SELECT
            tm.HomeTeamID,
            tm.AwayTeamID,
            msa.HomeTeamPoint,
            msa.AwayTeamPoint
        FROM TournamentMatches tm
        JOIN MatchHeader mh
            ON mh.ID = tm.MatchID
        JOIN MatchesScoreActual msa
            ON msa.MatchHeaderID = mh.ID
        WHERE tm.TournamentID = %s
        AND tm.Stage = 'group'
        AND mh.Status = 'Closed'
    """, (tournament_id,))

    matches = cur.fetchall()

    for m in matches:

        home = stats[m["HomeTeamID"]]
        away = stats[m["AwayTeamID"]]

        hs = m["HomeTeamPoint"] or 0
        aw = m["AwayTeamPoint"] or 0

        home["Played"] += 1
        away["Played"] += 1

        home["GoalsScored"] += hs
        home["GoalsAgainst"] += aw

        away["GoalsScored"] += aw
        away["GoalsAgainst"] += hs

        if hs > aw:
            home["Points"] += 2
        elif aw > hs:
            away["Points"] += 2
        else:
            home["Points"] += 1
            away["Points"] += 1

    groups = {}

    for team in stats.values():

        group = team["GroupName"]

        if group not in groups:
            groups[group] = []

        groups[group].append(team)

    for group in groups:

        groups[group].sort(
            key=lambda t: (
                t["Points"],
                t["GoalsScored"] - t["GoalsAgainst"],
                t["GoalsScored"]
            ),
            reverse=True
        )

    return groups


@app.post("/tournaments/{tournament_id}/generate-placement")
def generate_placement(tournament_id: int):
    conn = get_conn()
    cur = conn.cursor()

    try:
        generate_placement_matches(cur, tournament_id)
        conn.commit()

        return {
            "success": True
        }

    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()



@app.get("/matches/{match_id}/timeline")
def get_match_timeline(match_id: int):

    conn = get_conn()
    cur = conn.cursor()

    # Match info
    cur.execute("""
        SELECT
            tm.ID,
            ht.Name AS HomeTeam,
            at.Name AS AwayTeam,
            A.HomeTeamPoint AS HomeScore,
            A.AwayTeamPoint AS AwayScore
        FROM TournamentMatches tm
        LEFT JOIN TournamentTeams ht
            ON ht.ID = tm.HomeTeamID
        LEFT JOIN TournamentTeams at
            ON at.ID = tm.AwayTeamID
        LEFT JOIN MatchDetailPoint A
            ON A.MatchHeaderID = tm.MatchID
        WHERE tm.MatchID = %s
        AND Deleted = 0
        
    """, (match_id,))
    

    match = cur.fetchone()

    if not match:
        return {
            "success": False,
            "message": "Match not found"
        }

    # Goals
    cur.execute("""
        SELECT
            ID,
            HomeTeamPoint,
            AwayTeamPoint,
            Timestamp AS CreatedAt
        FROM MatchDetailPoint
        WHERE MatchHeaderID = %s
        AND Deleted = 0
        ORDER BY Timestamp
    """, (match_id,))

    points = cur.fetchall()

    timeline = []
    first_time = None

    previous_home = 0
    previous_away = 0

    for goal_number, p in enumerate(points, start=1):

        if first_time is None:
            first_time = p["CreatedAt"]

        seconds = int(
            (p["CreatedAt"] - first_time).total_seconds()
        )

        scoring_team = "home"

        if p["AwayTeamPoint"] > previous_away:
            scoring_team = "away"

        timeline.append({
            "goalNumber": goal_number,
            "matchDetailPointId": p["ID"],
            "scoreHome": p["HomeTeamPoint"],
            "scoreAway": p["AwayTeamPoint"],
            "scoringTeam": scoring_team,
            "timestamp": p["CreatedAt"].isoformat(),
            "seconds": seconds
        })

        previous_home = p["HomeTeamPoint"]
        previous_away = p["AwayTeamPoint"]

    return {
        "success": True,
        "matchId": match["ID"],
        "homeTeam": match["HomeTeam"],
        "awayTeam": match["AwayTeam"],
        "homeScore": match["HomeScore"],
        "awayScore": match["AwayScore"],
        "goalCount": len(timeline),
        "timeline": timeline
    }




# ---------- User groups ----------

@app.get("/player-groups")
def get_player_groups(club_id: int | None = None):
    conn = get_conn()
    cur = conn.cursor()

    if club_id is not None:
        cur.execute("""
            SELECT ID, Name, ClubID
            FROM PlayerGroups
            WHERE ClubID = %s
            OR ClubID IS NULL
            ORDER BY Name
        """, (club_id,))
    else:
        cur.execute("""
            SELECT ID, Name, ClubID
            FROM PlayerGroups
            ORDER BY Name
        """)

    rows = cur.fetchall()
    conn.close()
    return rows

class PlayerGroupCreate(BaseModel):
    name: str
    club_id: int | None = None



@app.post("/player-groups")
def create_player_group(data: PlayerGroupCreate):
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO PlayerGroups
            (
                Name,
                ClubID
            )
            VALUES
            (
                %s,
                %s
            )
        """, (
            data.name,
            data.club_id
        ))

        conn.commit()

        return {
            "id": cur.lastrowid,
            "success": True
        }

    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()


class PlayerGroupUpdate(BaseModel):
    name: str


@app.put("/player-groups/{group_id}")
def update_player_group(group_id: int, data: PlayerGroupUpdate):
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE PlayerGroups
            SET Name = %s
            WHERE ID = %s
        """, (
            data.name,
            group_id
        ))
        if cur.rowcount == 0:
            return {"error": "Group not found"}
        conn.commit()

        return {
            "success": True
        }

    except Exception as e:
        conn.rollback()
        return {
            "error": str(e)
        }

    finally:
        conn.close()



@app.delete("/player-groups/{group_id}")
def delete_player_group(group_id: int):
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            DELETE
            FROM PlayerGroups
            WHERE ID = %s
        """, (group_id,))

        if cur.rowcount == 0:
            return {"error": "Group not found"}
        
        conn.commit()

        return {
            "success": True
        }

    except Exception as e:
        conn.rollback()
        return {
            "error": str(e)
        }

    finally:
        conn.close()



class PlayerGroupMember(BaseModel):
    player_id: int
    group_id: int


@app.get("/users/{user_id}/groups")
def get_user_groups(user_id: int):
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                pg.ID,
                pg.Name,
                pg.ClubID
            FROM PlayerGroupMembers pgm
            JOIN PlayerGroups pg
                ON pg.ID = pgm.GroupID
            WHERE pgm.PlayerID = %s
            ORDER BY pg.Name
        """, (user_id,))

        return cur.fetchall()

    except Exception as e:
        return {
            "error": str(e)
        }

    finally:
        conn.close()



@app.post("/users/{user_id}/groups/{group_id}")
def add_user_to_group(user_id: int, group_id: int):
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT IGNORE INTO PlayerGroupMembers
            (
                PlayerID,
                GroupID
            )
            VALUES
            (
                %s,
                %s
            )
        """, (
            user_id,
            group_id
        ))

        conn.commit()

        return {
            "success": True
        }

    except Exception as e:
        conn.rollback()
        return {
            "error": str(e)
        }

    finally:
        conn.close()



@app.delete("/users/{user_id}/groups/{group_id}")
def remove_user_from_group(user_id: int, group_id: int):
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            DELETE
            FROM PlayerGroupMembers
            WHERE PlayerID = %s
            AND GroupID = %s
        """, (
            user_id,
            group_id
        ))

        conn.commit()

        return {
            "success": True
        }

    except Exception as e:
        conn.rollback()
        return {
            "error": str(e)
        }

    finally:
        conn.close()



@app.get("/users")
def read_users(group_id: int | None = None):
    conn = get_conn()
    cur = conn.cursor()

    try:
        if group_id is None:
            cur.execute("""
                SELECT
                    ID as id,
                    Navn as name,
                    CONCAT('/avatars/', ID, '.png') as avatar,
                    IF(ButtonID IS NULL, 0, 1) as has_flic
                FROM Users
                ORDER BY Navn
            """)
        
        elif group_id == -1:
           cur.execute("""
               SELECT
                   u.ID as id,
                   u.Navn as name,
                   CONCAT('/avatars/', u.ID, '.png') as avatar,
                   IF(u.ButtonID IS NULL, 0, 1) as has_flic
                FROM Users u
                LEFT JOIN PlayerGroupMembers pgm
                    ON pgm.PlayerID = u.ID
                WHERE pgm.PlayerID IS NULL
                ORDER BY u.Navn
            """)
        
        
        
        
        else:
            cur.execute("""
                SELECT DISTINCT
                    u.ID as id,
                    u.Navn as name,
                    CONCAT('/avatars/', u.ID, '.png') as avatar,
                    IF(u.ButtonID IS NULL, 0, 1) as has_flic
                FROM Users u
                JOIN PlayerGroupMembers pgm
                    ON pgm.PlayerID = u.ID
                WHERE pgm.GroupID = %s
                ORDER BY u.Navn
            """, (group_id,))
        

        rows = cur.fetchall()
        return rows

    except Exception as e:
        return {
            "error": str(e)
        }

    finally:
        conn.close()


@app.get("/club/{token}")
def get_club(token: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT ClubName
        FROM CustomerClub
        WHERE PublicToken = %s
        LIMIT 1
    """, (token,))

    row = cur.fetchone()
    conn.close()

    return {
        "clubName": row["ClubName"] if row else ""
    }




class CorporateButtonCreate(BaseModel):
    button_id: str
    public_token: str
    description: str


class CorporateButtonCheck(BaseModel):
    button_id: str


@app.get("/corporate-buttons")
def get_corporate_buttons():

    conn = get_conn()
    cur = conn.cursor()

    try:

        cur.execute("""
            SELECT
                cb.ID,
                cb.ButtonID,
                cb.PublicToken,
                cb.Description,
                cb.Active,
                cb.CreatedDate,
                c.ClubName
            FROM CorporateButtons cb
            LEFT JOIN CustomerClub c
            ON cb.PublicToken = c.PublicToken
            ORDER BY Description
        """)

        return cur.fetchall()

    finally:
        conn.close()



@app.post("/corporate-buttons")
def create_corporate_button(data: CorporateButtonCreate):

    conn = get_conn()
    cur = conn.cursor()

    try:

        cur.execute("""
            INSERT INTO CorporateButtons
            (
                ButtonID,
                PublicToken,
                Description
            )
            VALUES
            (
                %s,
                %s,
                %s
            )
        """,
        (
            data.button_id,
            data.public_token,
            data.description
        ))

        conn.commit()

        return {
            "success": True,
            "id": cur.lastrowid
        }

    except Exception as e:

        conn.rollback()

        return {
            "error": str(e)
        }

    finally:

        conn.close()



@app.delete("/corporate-buttons/{button_id}")
def delete_corporate_button(button_id:int):

    conn = get_conn()
    cur = conn.cursor()

    try:

        cur.execute("""
            DELETE
            FROM CorporateButtons
            WHERE ID=%s
        """,(button_id,))

        conn.commit()

        return {
            "success":True
        }

    except Exception as e:

        conn.rollback()

        return {
            "error":str(e)
        }

    finally:

        conn.close()




@app.post("/corporate-buttons/check")
def check_corporate_button(data: CorporateButtonCheck):

    conn = get_conn()
    cur = conn.cursor()

    try:

        # Findes den på en spiller?
        cur.execute("""
            SELECT Navn
            FROM Users
            WHERE ButtonID=%s
            LIMIT 1
        """,(data.button_id,))

        user = cur.fetchone()

        if user:

            return {
                "status":"player",
                "name":user["Navn"]
            }

        # Findes den som corporate?

        cur.execute("""
            SELECT ID
            FROM CorporateButtons
            WHERE ButtonID=%s
            LIMIT 1
        """,(data.button_id,))

        corp = cur.fetchone()

        if corp:

            return {
                "status":"corporate"
            }

        return {
            "status":"free"
        }

    finally:

        conn.close()




@router.post("/webhook_test/{action}")
async def webhook_test(action: str, request: Request):
    print(f"\n=== FLIC TEST ({action}) ===")

    print("\nHeaders:")
    for key, value in request.headers.items():
        print(f"{key}: {value}")

    body = await request.body()

    print("\nBody:")
    print(body.decode())

    print("============================\n")

    return {
        "success": True,
        "action": action,
    }
