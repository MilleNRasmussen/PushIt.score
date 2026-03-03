"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"

type Player = {
  id: number
  name: string
  avatar?: string
}

export default function Page(){

const router = useRouter()

const [players,setPlayers] = useState<Player[]>([])
const [search,setSearch] = useState("")
const [mode,setMode] = useState<"1v1"|"2v2">("2v2")
const [teamA,setTeamA] = useState<(Player|null)[]>([null,null])
const [teamB,setTeamB] = useState<(Player|null)[]>([null,null])
const [showPopup,setShowPopup] = useState(false)
const [countdown,setCountdown] = useState(3)

useEffect(()=>{

 fetch("https://pushitscore-production.up.railway.app/Users/")
  .then(res=>res.json())
  .then(data=>{

    console.log("Users API:",data)

    if(Array.isArray(data)){
      setPlayers(data)
    }else{
      console.error("Users API returnerede ikke en array")
      setPlayers([])
    }

  })
  .catch(err=>{
    console.error("Users fetch fejl:",err)
    setPlayers([])
  })

},[])

function addPlayer(player:Player){

 if(!teamA[0]){
   setTeamA([player,teamA[1]])
   setPlayers(players.filter(p=>p.id!==player.id))
   return
 }

 if(mode==="2v2" && !teamA[1]){
   setTeamA([teamA[0],player])
   setPlayers(players.filter(p=>p.id!==player.id))
   return
 }

 if(!teamB[0]){
   setTeamB([player,teamB[1]])
   setPlayers(players.filter(p=>p.id!==player.id))
   return
 }

 if(mode==="2v2" && !teamB[1]){
   setTeamB([teamB[0],player])
   setPlayers(players.filter(p=>p.id!==player.id))
   return
 }

}

function removePlayer(team:"A"|"B",index:number){

 if(team==="A"){
   const player=teamA[index]
   const updated=[...teamA]
   updated[index]=null
   setTeamA(updated)
   if(player) setPlayers([...players,player])
 }

 if(team==="B"){
   const player=teamB[index]
   const updated=[...teamB]
   updated[index]=null
   setTeamB(updated)
   if(player) setPlayers([...players,player])
 }

}

function Avatar({player}:{player:Player|null}){

 if(!player){
   return(
     <div className="w-12 h-12 rounded-full bg-slate-500 flex items-center justify-center">
       ?
     </div>
   )
 }

 if(player.avatar){
   return(
     <img
       src={player.avatar}
       className="w-12 h-12 rounded-full object-cover"
     />
   )
 }

 return(
   <div className="w-12 h-12 rounded-full bg-blue-500 flex items-center justify-center font-bold">
     {player.name.charAt(0)}
   </div>
 )

}

const filtered = players.filter(p =>
 p.name.toLowerCase().includes(search.toLowerCase())
)

async function startMatch(){

 const selectedPlayers = [
 teamA[0],
 teamA[1],
 teamB[0],
 teamB[1]
 ].filter(p=>p!==null)

 if(selectedPlayers.length < 2){
 alert("Vælg mindst 2 spillere")
 return
 }

 const playerIds = selectedPlayers.map(p=>p!.id)

 const res = await fetch("https://pushitscore-production.up.railway.app/MatchHeaderInsert/",{
 method:"POST",
 headers:{
 "Content-Type":"application/json"
 },
 body:JSON.stringify({
 match_type_id:1,
 match_gamemode_id: mode==="2v2" ? 2 : 1,
 players:playerIds
 })
 })

 const result = await res.json()

 console.log("Match API:",result)

 const matchId = result.match_id ?? result.id ?? result.matchId

 if(!matchId){
 alert("Match ID mangler fra API")
 return
 }

 setShowPopup(true)

 let counter = 3

 const interval = setInterval(()=>{

 counter--
 setCountdown(counter)

 if(counter===0){

 clearInterval(interval)

 router.push(`/livescore/${matchId}`)

 }

 },1000)

}

return(
<div className="min-h-screen bg-gradient-to-b from-[#0a2342] to-[#081a33] text-white flex flex-col items-center p-10">

<div className="flex items-start justify-center gap-16 mb-10">

<div className="bg-[#132c52] rounded-xl p-6 w-56">

<h2 className="text-center mb-4 font-semibold">
Team A
</h2>

<div className="space-y-4">

{teamA.map((player,i)=>{

const disabled = mode==="1v1" && i===1

return(

<div
key={i}
onDoubleClick={()=>removePlayer("A",i)}
className={`flex items-center gap-3 p-3 rounded-lg ${
 disabled
 ? "bg-slate-700 opacity-40"
 : "bg-[#1b3b6f]"
}`}
>

<Avatar player={player}/>

{disabled
 ? "Ikke aktiv"
 : player
 ? player.name
 : "Tom plads"}

</div>

)

})}

</div>
</div>

<div className="text-3xl font-bold opacity-70 mt-12">
VS
</div>

<div className="bg-[#132c52] rounded-xl p-6 w-56">

<h2 className="text-center mb-4 font-semibold">
Team B
</h2>

<div className="space-y-4">

{teamB.map((player,i)=>{

const disabled = mode==="1v1" && i===1

return(

<div
key={i}
onDoubleClick={()=>removePlayer("B",i)}
className={`flex items-center gap-3 p-3 rounded-lg ${
 disabled
 ? "bg-slate-700 opacity-40"
 : "bg-[#1b3b6f]"
}`}
>

<Avatar player={player}/>

{disabled
 ? "Ikke aktiv"
 : player
 ? player.name
 : "Tom plads"}

</div>

)

})}

</div>
</div>

</div>

<div className="flex gap-6 bg-[#132c52] p-4 rounded-xl justify-center mb-6">

<label className="flex items-center gap-2">
<input
type="radio"
checked={mode==="1v1"}
onChange={()=>setMode("1v1")}
/>
1 vs 1
</label>

<label className="flex items-center gap-2">
<input
type="radio"
checked={mode==="2v2"}
onChange={()=>setMode("2v2")}
/>
2 vs 2
</label>

</div>

<div className="w-full max-w-2xl space-y-6">

<input
placeholder="Søg spiller"
value={search}
onChange={e=>setSearch(e.target.value)}
className="w-full bg-[#132c52] rounded-xl p-3 outline-none"
/>

<div className="bg-[#132c52] rounded-xl p-5 space-y-3 max-h-[350px] overflow-auto">

{filtered.map(player=>(

<button
key={player.id}
onClick={()=>addPlayer(player)}
className="w-full flex items-center gap-3 bg-[#1b3b6f] hover:bg-[#234a85] p-3 rounded-lg"
>

<Avatar player={player}/>
{player.name}

</button>

))}

</div>

</div>

<div className="mt-10">

<button
onClick={startMatch}
className="w-96 bg-blue-600 hover:bg-blue-500 py-4 rounded-xl text-lg font-semibold"
>

Start kamp

</button>

</div>

{showPopup && (

<div className="fixed inset-0 flex items-center justify-center bg-black/70">

<div className="bg-[#132c52] p-10 rounded-xl text-center">

<h2 className="text-2xl mb-4">
Kampen er klar
</h2>

<p className="mb-4">
Du viderestilles til kampen
</p>

<div className="text-5xl font-bold">
{countdown}
</div>

</div>

</div>

)}

</div>
)

}
