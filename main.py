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

class TextInput(BaseModel):
    text: str

class TournamentIn(BaseModel):
    text: str
    tournament_type_id: int
    tournament_gamemode_id: int
    players:List[int]

@app.get("/MatchHeader/")
def red_MatchHeader():
    conn = pymysql.connect(
        host="localhost",
        user="ClausRasmussen",
        password="Aa12345678",
        database="Tournament"
    )
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM MatchHeader")
    rows = cur.fetchall()
    conn.close()
    return rows



@app.get("/TournamentGamemode/")
def red_TournamentGamemode():
    conn = pymysql.connect(
        host="localhost",
        user="ClausRasmussen",
        password="Aa12345678",
        database="Tournament"
    )
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT ID, Value, TournamentTypeID AS Tournament_TypeID FROM TournamentGameMode")
    rows = cur.fetchall()
    conn.close()
    return rows







@app.get("/MatchDetail/")
def red_MatchDetail():
    conn = pymysql.connect(
        host="localhost",
        user="ClausRasmussen",
        password="Aa12345678",
        database="Tournament"
    )
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM MatchDetail")
    rows = cur.fetchall()
    conn.close()
    return rows


@app.get("/MatchScore/")
def red_MatchScore():
    conn = pymysql.connect(
        host="localhost",
        user="ClausRasmussen",
        password="Aa12345678",
        database="Tournament"
    )
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM MatchScore")
    rows = cur.fetchall()
    conn.close()
    return rows


@app.get("/MatchScoreActual/")
def red_MatchScoreDetail():
    conn = pymysql.connect(
        host="localhost",
        user="ClausRasmussen",
        password="Aa12345678",
        database="Tournament",        
    )
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM MatchScoreActual")
    rows = cur.fetchall()
    conn.close()
    return rows


@app.get("/Users/")
def red_Users():
    conn = pymysql.connect(
        host="localhost",
        user="ClausRasmussen",
        password="Aa12345678",
        database="Tournament",        
    )
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM Users")
    rows = cur.fetchall()
    conn.close()
    return rows


@app.get("/Tournament_Type/")
def red_Tournament_Type():
    conn = pymysql.connect(
        host="localhost",
        user="ClausRasmussen",
        password="Aa12345678",
        database="Tournament",        
    )
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM Tournament_Type")
    rows = cur.fetchall()
    conn.close()
    return rows

@app.post("/MatchHeaderInsert/")
def Insert_matchheader(data: TournamentIn):

    if len(data.players) < 2:
        return {"error": "Der skal vælges mindst 2 spillere"}

    conn = pymysql.connect(
        host="localhost",
        user="ClausRasmussen",
        password="Aa12345678",
        database="Tournament",
        autocommit=False
    )

    cur = conn.cursor()

    try:
        # Indsæt turnering
        cur.execute(
            """
            INSERT INTO MatchHeader (TableID,  Timestamp, MatchTypeID, MatchGamemodeID)
            VALUES (1,NOW(),%s,%s)
            """,
            (data.tournament_type_id,data.tournament_gamemode_id)
        )
 
        turnering_id = cur.lastrowid

        # Indsæt spillere
        #for index,user_id in data.players,start1:
        for index,user_id in enumerate(data.players,start=1):   
            cur.execute(
                """
                INSERT INTO TournamentPlayers (TournamentID, PlayerNumber, PlayerID, Timestamp)
                VALUES (%s,  %s, %s, NOW())
                """,
                (turnering_id, index, user_id)
            )

        conn.commit()
        return {
            "status": "ok",
            "turnering_id": turnering_id,
            "players": data.players
        }

    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()


@app.post("/TournamentInsert/")
def Insert_tournament(data: TournamentIn):

    if len(data.players) < 2:
        return {"error": "Der skal vælges mindst 2 spillere"}

    conn = pymysql.connect(
        host="localhost",
        user="ClausRasmussen",
        password="Aa12345678",
        database="Tournament",
        autocommit=False
    )

    cur = conn.cursor()

    try:
        # Indsæt turnering
        cur.execute(
            """
            INSERT INTO Tournament (Name, TableID, Timestamp, TournamentTypeID, TournamentGamemodeID)
            VALUES (%s, 1, NOW(),%s,%s)
            """,
            (data.text,data.tournament_type_id,data.tournament_gamemode_id)
        )
 
        turnering_id = cur.lastrowid

        # Indsæt spillere
        #for index,user_id in data.players,start1:
 #       for index,user_id in enumerate(data.players,start=1):   
 #           cur.execute(
 #               """
 #               INSERT INTO TournamentPlayers (TournamentID, PlayerNumber, PlayerID, Timestamp)
 #               VALUES (%s,  %s, %s, NOW())
 #               """,
 #               (turnering_id, index, user_id)
 #           )

        conn.commit()
        return {
            "status": "ok",
            "turnering_id": turnering_id,
            "players": data.players
        }

    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()


@app.post("/InsertTest/")
def Insert_Test():

    conn = pymysql.connect(
        host="localhost",
        user="ClausRasmussen",
        password="Aa12345678",
        database="Tournament",
        autocommit=False
    )

    cur = conn.cursor()

    try:
        # Indsæt turnering
        cur.execute(
            """
            INSERT INTO MatchHeader (TableID,  Timestamp, MatchTypeID, MatchGamemodeID)
            VALUES (1,NOW(),2,2)
            """
        )
 
        turnering_id = cur.lastrowid

        conn.commit()
        return {
            "status": "ok"
           
        }

    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()



@app.post("/InsertPointHomeTest/")
def Insert_HomeTest():

    conn = pymysql.connect(
        host="localhost",
        user="ClausRasmussen",
        password="Aa12345678",
        database="Tournament",
        autocommit=False
    )

    cur = conn.cursor()

    try:
        # Indsæt turnering
        cur.callproc(
            "SP_InsertIntoMatchDetailPoint_Test"
        )
 
        conn.commit()
        return {
            "status": "ok"
           
        }

    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()






@app.post("/InsertPointAwayTest/")
def Insert_AwayTest():

    conn = pymysql.connect(
        host="localhost",
        user="ClausRasmussen",
        password="Aa12345678",
        database="Tournament",
        autocommit=False
    )

    cur = conn.cursor()

    try:
        # Indsæt turnering
        cur.callproc(
            "SP_InsertIntoMatchDetailPoint_TestAway"
        )
 
        conn.commit()
        return {
            "status": "ok"
           
        }

    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()




@app.post("/DeletePointTest/")
def Delete_HomeTest():

    conn = pymysql.connect(
        host="localhost",
        user="ClausRasmussen",
        password="Aa12345678",
        database="Tournament",
        autocommit=False
    )

    cur = conn.cursor()

    try:
        # Indsæt turnering
        cur.callproc(
            "SP_DeleteIntoMatchDetailPoint"
        )
 
        conn.commit()
        return {
            "status": "ok"
           
        }

    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()



@app.post("/DeletePointTest_Away/")
def Delete_AwayTest():

    conn = pymysql.connect(
        host="localhost",
        user="ClausRasmussen",
        password="Aa12345678",
        database="Tournament",
        autocommit=False
    )

    cur = conn.cursor()

    try:
        # Indsæt turnering
        cur.callproc(
            "SP_DeleteIntoMatchDetailPoint_Test"
        )
 
        conn.commit()
        return {
            "status": "ok"
           
        }

    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

    finally:
        conn.close()


