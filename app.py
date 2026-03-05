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
        NULL as avatar
        FROM Users
    """)

    users = cur.fetchall()

    conn.close()

    return users


# ---------- MATCH HEADER ----------
@app.post("/MatchHeaderInsert/")
async def MatchHeaderInsert(data: MatchCreate):

    conn = get_conn()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO MatchHeader (MatchTypeId, MatchGameModeId)
            VALUES (%s, %s)
            """,
            (data.match_type_id, data.match_gamemode_id)
        )

        match_id = cursor.lastrowid

        for index, user_id in enumerate(data.players, start=1):

            # 1v1
            if len(data.players) == 2:
                if index == 1:
                    player_number = 1
                else:
                    player_number = 3

            # 2v2
            else:
                player_number = index

            cursor.execute(
                """
                INSERT INTO MatchPlayers (MatchID, PlayerID, PlayerNumber)
                VALUES (%s, %s, %s)
                """,
                (match_id, user_id, player_number)
            )

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

    cur.execute("""
        SELECT mp.PlayerNumber, u.Navn
        FROM MatchPlayers mp
        JOIN Users u ON u.ID = mp.PlayerID
        WHERE mp.MatchID = %s
        ORDER BY mp.PlayerNumber
    """, (match_id,))

    players = cur.fetchall()

    conn.close()

    home = [p["Navn"] for p in players if p["PlayerNumber"] in (1,2)]
    away = [p["Navn"] for p in players if p["PlayerNumber"] in (3,4)]

    return {
        "score": score,
        "homePlayers": home,
        "awayPlayers": away
    }
