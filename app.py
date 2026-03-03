import os
import pymysql
from fastapi import FastAPI, Request
from typing import List
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

# ---------- USERS (Padel page) ----------

@app.get("/users")
def get_users():

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

# ---------- MATCH TYPES ----------

@app.get("/MatchType/")
def read_matchtype():

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM MatchType")

    rows = cur.fetchall()

    conn.close()

    return rows


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
            (TableID, Timestamp, MatchTypeID, MatchGamemodeID)
            VALUES (1, NOW(), %s, %s)
        """, (data.match_type_id, data.match_gamemode_id))

        match_id = cur.lastrowid


        # ---------- INSERT PLAYERS ----------

        for index, user_id in enumerate(data.players, start=1):

            cur.execute("""
                INSERT INTO MatchPlayers
                (MatchID, PlayerNumber, PlayerID, Timestamp)
                VALUES (%s,%s,%s,NOW())
            """, (match_id, index, user_id))


        # ---------- CREATE START SCORE ----------

        cur.execute("""
            INSERT INTO MatchScoreActual
            (MatchHeaderID,HomeTeamPoint,HomeGame,HomeSet,
             AwayTeamPoint,AwayGame,AwaySet)
            VALUES (%s,0,0,0,0,0,0)
        """,(match_id,))


        conn.commit()

        return {
            "status":"ok",
            "match_id":match_id
        }

    except Exception as e:

        conn.rollback()

        return {"error":str(e)}

    finally:

        conn.close()


# ---------- LIVESCORE ----------

@app.get("/MatchLivescore/{match_id}")
def read_match_livescore(match_id:int):

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
        FROM MatchScoreActual
        WHERE MatchHeaderID=%s
    """,(match_id,))

    rows = cur.fetchall()

    conn.close()

    return rows


# ---------- PADDEL BUTTONS ----------

@app.post("/InsertPointPadelHome/")
def insert_home_point():

    conn = get_conn()
    cur = conn.cursor()

    try:

        cur.callproc("SP_InsertIntoMatchDetailPadel_Home")

        conn.commit()

        return {"status":"ok"}

    except Exception as e:

        conn.rollback()

        return {"error":str(e)}

    finally:

        conn.close()


@app.post("/InsertPointPadelAway/")
def insert_away_point():

    conn = get_conn()
    cur = conn.cursor()

    try:

        cur.callproc("SP_InsertIntoMatchDetailPadel_Away")

        conn.commit()

        return {"status":"ok"}

    except Exception as e:

        conn.rollback()

        return {"error":str(e)}

    finally:

        conn.close()


# ---------- FLIC WEBHOOKS ----------

@app.post("/flic-webhook_Home/")
async def flic_home(request: Request):

    conn = get_conn()
    cur = conn.cursor()

    try:

        button_id = request.headers.get("button-serial-number")

        if not button_id:
            return {"error":"No button id"}

        cur.callproc("SP_InsertIntoMatchDetailPadel_Home",(button_id,))

        conn.commit()

        return {"status":"ok"}

    except Exception as e:

        conn.rollback()

        return {"error":str(e)}

    finally:

        conn.close()


@app.post("/flic-webhook_Away/")
async def flic_away(request: Request):

    conn = get_conn()
    cur = conn.cursor()

    try:

        button_id = request.headers.get("button-serial-number")

        if not button_id:
            return {"error":"No button id"}

        cur.callproc("SP_InsertIntoMatchDetailPadel_Away",(button_id,))

        conn.commit()

        return {"status":"ok"}

    except Exception as e:

        conn.rollback()

        return {"error":str(e)}

    finally:

        conn.close()
