import os
import pymysql
from fastapi import FastAPI
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
class TextInput(BaseModel):
    text: str

class TournamentIn(BaseModel):
    text: str
    tournament_type_id: int
    tournament_gamemode_id: int
    players: List[int]

# ---------- GET ENDPOINTS ----------
@app.get("/MatchHeader/")
def read_matchheader():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM MatchHeader")
    rows = cur.fetchall()
    conn.close()
    return rows

@app.get("/TournamentGamemode/")
def read_tournament_gamemode():
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

@app.get("/MatchScoreActual/")
def read_matchscoreactual():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM MatchScoreActual")
    rows = cur.fetchall()
    conn.close()
    return rows

@app.get("/Users/")
def read_users():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM Users")
    rows = cur.fetchall()
    conn.close()
    return rows

@app.get("/Tournament_Type/")
def read_tournament_type():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM Tournament_Type")
    rows = cur.fetchall()
    conn.close()
    return rows

# ---------- POST ENDPOINTS ----------
@app.post("/MatchHeaderInsert/")
def insert_matchheader(data: TournamentIn):
    if len(data.players) < 2:
        return {"error": "Der skal vælges mindst 2 spillere"}

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO MatchHeader (TableID, Timestamp, MatchTypeID, MatchGamemodeID)
            VALUES (1, NOW(), %s, %s)
        """, (data.tournament_type_id, data.tournament_gamemode_id))

        match_id = cur.lastrowid

        for index, user_id in enumerate(data.players, start=1):
            cur.execute("""
                INSERT INTO TournamentPlayers
                (TournamentID, PlayerNumber, PlayerID, Timestamp)
                VALUES (%s, %s, %s, NOW())
            """, (match_id, index, user_id))

        conn.commit()
        return {"status": "ok", "match_id": match_id}

    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()

@app.post("/InsertTest/")
def insert_test():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO MatchHeader (TableID, Timestamp, MatchTypeID, MatchGamemodeID)
            VALUES (1, NOW(), 2, 2)
        """)
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()

@app.post("/InsertPointHomeTest/")
def insert_home_test():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.callproc("SP_InsertIntoMatchDetailPoint_Test")
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()

@app.post("/InsertPointAwayTest/")
def insert_away_test():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.callproc("SP_InsertIntoMatchDetailPoint_TestAway")
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()

@app.post("/DeletePointTest/")
def delete_home_test():
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

@app.post("/DeletePointTest_Away/")
def delete_away_test():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.callproc("SP_DeleteIntoMatchDetailPoint_Test")
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()




@app.post("/InsertIntoMatchHeader/")
def delete_away_test():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.callproc("SP_InserIntoMatchHeader")
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()
