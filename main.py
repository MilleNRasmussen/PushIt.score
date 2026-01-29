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

# ---------- POST ENDPOINTS ----------

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
