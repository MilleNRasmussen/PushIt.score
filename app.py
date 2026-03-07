import os
import pymysql
from fastapi import FastAPI, Request
from typing import List
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

app = FastAPI()

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
        autocommit=False
    )

# ---------- MODELS ----------
class MatchCreate(BaseModel):
    match_type_id: int
    match_gamemode_id: int
    players: List[int]



# =====================================================
# BACKGROUND SCHEDULER
# Automatically pauses inactive matches after 10 minutes
# Runs every 1 minute
# =====================================================
# ---------- AUTO PAUSE JOB ----------
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
            AND COALESCE(
                md.LastPoint,
                mh.StartedAt
            ) < NOW() - INTERVAL 10 MINUTE
        """)

        print("Paused matches:", cur.rowcount)

        conn.commit()

    finally:
        conn.close()

# ---------- GET ----------
@app.get("/MatchHeader/")
def read_matchheader():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM MatchHeader")
    rows = cur.fetchall()
    conn.close()
    return rows

@app.get("/Gamemode/")
def read_gamemode():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT ID, Value, TournamentTypeID AS Tournament_TypeID
        FROM TournamentGameMode
    """)
    rows = cur.fetchall()
    conn.close()
    return rows

@app.get("/MatchDetail/")
def read_matchdetail():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM MatchDetail")
    rows = cur.fetchall()
    conn.close()
    return rows

@app.get("/MatchScore/")
def read_matchscore():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM MatchScore")
    rows = cur.fetchall()
    conn.close()
    return rows

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

@app.get("/MatchType/")
def read_matchtype():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM MatchType")
    rows = cur.fetchall()
    conn.close()
    return rows


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

    home = [p["Navn"] for p in players if p["PlayerNumber"] in (1, 2)]
    away = [p["Navn"] for p in players if p["PlayerNumber"] in (3, 4)]

    return {
        "score": score,
        "status": status,
        "homePlayers": home,
        "awayPlayers": away
    }




# ---------- CREATE MATCH ----------
@app.post("/MatchHeaderInsert/")
def insert_matchheader(data: MatchCreate):

    if len(data.players) < 2:
        return {"error": "Der skal vælges mindst 2 spillere"}

    conn = get_conn()
    cur = conn.cursor()

    try:

        cur.execute("""
            INSERT INTO MatchHeader
            (TableID, `Timestamp`, MatchTypeID, MatchGamemodeID, StartedAt, Status)
            VALUES (1, NOW(), %s, %s, NOW(), 'Live')
        """, (data.match_type_id, data.match_gamemode_id))

        match_id = cur.lastrowid

        for index, user_id in enumerate(data.players, start=1):

            if len(data.players) == 2:
                player_number = 1 if index == 1 else 3
            else:
                player_number = index

            cur.execute("""
                INSERT INTO MatchPlayers
                (MatchID, PlayerNumber, PlayerID, Timestamp)
                VALUES (%s, %s, %s, NOW())
            """, (match_id, player_number, user_id))

        conn.commit()

        return {
            "status": "ok",
            "match_id": match_id
        }

    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()

# ---------- MATCH PLAYERS ----------
@app.get("/MatchPlayers/{match_id}")
def get_match_players(match_id: int):

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT mp.PlayerNumber, u.Navn
        FROM MatchPlayers mp
        JOIN Users u ON u.ID = mp.PlayerID
        WHERE mp.MatchID = %s
        ORDER BY mp.PlayerNumber
    """, (match_id,))

    players = cur.fetchall()

    conn.close()

    return players

# ---------- POINTS ----------
@app.post("/InsertPointPadelHome/")
def insert_home():

    conn = get_conn()
    cur = conn.cursor()

    try:

        cur.callproc("SP_InsertIntoMatchDetailPadel_Home")

        conn.commit()

        return {"status": "ok"}

    except Exception as e:

        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()

@app.post("/InsertPointPadelAway/")
def insert_away():

    conn = get_conn()
    cur = conn.cursor()

    try:

        cur.callproc("SP_InsertIntoMatchDetailPadel_Away")

        conn.commit()

        return {"status": "ok"}

    except Exception as e:

        conn.rollback()
        return {"error": str(e)}

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

# ---------- FLIC BUTTONS ----------
@app.post("/flic-webhook_Home/")
async def flic_webhook_home(request: Request):

    conn = get_conn()
    cur = conn.cursor()

    try:

        button_id = request.headers.get("button-serial-number")

        if not button_id:
            return {"error": "No button id"}

        cur.callproc("SP_InsertIntoMatchDetailPadel_Home", (button_id,))

        conn.commit()

        return {"status": "ok"}

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

        cur.callproc("SP_InsertIntoMatchDetailPadel_Away", (button_id,))

        conn.commit()

        return {"status": "ok"}

    except Exception as e:

        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()


# =====================================================
# BACKGROUND SCHEDULER
# Automatically pauses inactive matches after 10 minutes
# Runs every 1 minute
# =====================================================

# ---------- START SCHEDULER ----------
scheduler = BackgroundScheduler()
scheduler.add_job(pause_inactive_matches, "interval", minutes=1)
scheduler.start()
