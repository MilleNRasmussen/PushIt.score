import os
import pymysql
from fastapi import FastAPI, Request
from typing import List
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

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
        NULL as avatar
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
            MatchID as MatchHeaderID,
            HomeTeamPoint,
            HomeGame,
            HomeSet,
            AwayTeamPoint,
            AwayGame,
            AwaySet
        FROM MatchesScoreActual
        WHERE MatchID = %s
    """, (match_id,))

    row = cur.fetchone()

    conn.close()

    if not row:
        return [{
            "MatchHeaderID": match_id,
            "HomeTeamPoint": 0,
            "HomeGame": 0,
            "HomeSet": 0,
            "AwayTeamPoint": 0,
            "AwayGame": 0,
            "AwaySet": 0
        }]

    return [row]


# ---------- CREATE MATCH ----------

@app.post("/MatchHeaderInsert/")
def insert_matchheader(data: MatchCreate):

    if len(data.players) < 2:
        return {"error": "Der skal vælges mindst 2 spillere"}

    conn = get_conn()
    cur = conn.cursor()

    try:

        cur.execute("""
            INSERT INTO MatchHeader (TableID, Timestamp, MatchTypeID, MatchGamemodeID)
            VALUES (1, NOW(), %s, %s)
        """, (data.match_type_id, data.match_gamemode_id))

        match_id = cur.lastrowid

        for index, user_id in enumerate(data.players, start=1):
            cur.execute("""
                INSERT INTO MatchPlayers
                (MatchHeaderID, PlayerNumber, PlayerID, Timestamp)
                VALUES (%s, %s, %s, NOW())
            """, (match_id, index, user_id))

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

@app.post("/DeletePointTest/")
def delete_home():

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.callproc("SP_DeleteIntoMatchDetailPoint")
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
