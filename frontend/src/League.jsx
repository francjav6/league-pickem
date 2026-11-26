import { useEffect, useMemo, useState } from "react";

export const TEAMS = [
  ["VENEZUELAN DEMOCRACY","Pacho"],
  ["La Mike Alstott","Javi"],
  ["0 al TE","Raul"],
  ["Glory Warpigs (Col)","Juan Esteban"],
  ["Delfincitos","Tomas Zajdman"],
  ["Green Badgers","Walter"],
  ["Felipe's First-Rate Team","Felipe"],
  ["Hasbu Nation","Fredi"],
  ["FENICIOS S.A","Mono"],
  ["UAI Urquizers","Jorge"],
  ["Ex Ol's Syndicate","Kevin"],
  ["J19","Illai"],
  ["Geriatricos","Hernan"],
  ["Los Yaguaretés","Santiago"],
];
const owners = new Map(TEAMS);
const manager = team => owners.get(team) || "Manager por identificar";
export function TeamLabel({team}) {
  return <span className="team-label"><span className="team-name">{team}</span><span className="manager-name">{manager(team)}</span></span>;
}
export function Brand({login=false}) {
  return <div className={"brand" + (login ? " brand-login" : "")}><img src="/jaba.svg" alt="Logo del jabalí de Jaba Fantasy" /><div><span className="brand-kicker">FANTASY FOOTBALL · EST. 2017</span><h1>JABA <span>FANTASY</span></h1><span className="brand-sub">LEAGUE PICK'EM</span></div></div>;
}
function useArchive(api) {
  const [state,setState] = useState({games:[],failed:[],loading:true});
  const [retry,setRetry] = useState(0);
  useEffect(() => {
    let active=true;
    setState({games:[],failed:[],loading:true});
    async function load() {
      const games=[],failed=[];
      // Sequential reads in small groups to avoid overloading the free backend.
      for(let first=1; first<=14 && active; first+=3) {
        const weeks=Array.from({length:Math.min(3,15-first)},(_,i)=>first+i);
        const results=await Promise.allSettled(weeks.map(w=>api("/weeks/"+w+"/matchups")));
        results.forEach((result,i)=>{
          if(result.status==="fulfilled" && Array.isArray(result.value)) games.push(...result.value);
          else failed.push(weeks[i]);
        });
      }
      if(active) setState({games,failed,loading:false});
    }
    load();
    return ()=>{active=false;};
  },[api,retry]);
  return {...state,reload:()=>setRetry(v=>v+1)};
}
function won(game,team) {
  return (game.winner_choice==="A" && game.team_a===team) || (game.winner_choice==="B" && game.team_b===team);
}
export function LeagueArchive({api,mode}) {
  const {games,failed,loading,reload}=useArchive(api);
  const [a,setA]=useState(TEAMS[0][0]);
  const [b,setB]=useState(TEAMS[6][0]);
  const [season,setSeason]=useState("2026");
  const [week,setWeek]=useState("all");
  const finished=useMemo(()=>games.filter(g=>g.week_complete && ["A","B"].includes(g.winner_choice)).sort((x,y)=>y.week-x.week),[games]);
  const pair=finished.filter(g=>(g.team_a===a && g.team_b===b)||(g.team_a===b && g.team_b===a));
  const winsA=pair.filter(g=>won(g,a)).length;
  const winsB=pair.filter(g=>won(g,b)).length;
  const visible=mode==="rivalries"?pair:finished.filter(g=>week==="all"||g.week===Number(week));
  return <section className="panel archive-panel">
    <span className="eyebrow">JABA STATS · 2017–2026</span>
    <h2>{mode==="rivalries"?"Rivalidades":"Historial de enfrentamientos"}</h2>
    <p className="muted">Por ahora se muestran únicamente ganadores registrados en el Pick'em de 2026, de semanas completas. Los marcadores y las temporadas anteriores están pendientes de importar de Yahoo.</p>
    <label>Temporada<select value={season} onChange={e=>setSeason(e.target.value)}><option value="2026">2026 · Pick'em</option>{Array.from({length:9},(_,i)=>2025-i).map(y=><option key={y} value={y}>{y} · pendiente</option>)}</select></label>
    {mode==="rivalries" ? <div className="rival-select">
      <label>Manager / equipo 1<select value={a} onChange={e=>{setA(e.target.value);if(e.target.value===b)setB(TEAMS.find(t=>t[0]!==e.target.value)[0]);}}>{TEAMS.map(([t,p])=><option key={t} value={t}>{p} — {t}</option>)}</select></label>
      <label>Manager / equipo 2<select value={b} onChange={e=>setB(e.target.value)}>{TEAMS.filter(t=>t[0]!==a).map(([t,p])=><option key={t} value={t}>{p} — {t}</option>)}</select></label>
    </div>:<label>Semana<select value={week} onChange={e=>setWeek(e.target.value)}><option value="all">Todas</option>{Array.from({length:14},(_,i)=>i+1).map(w=><option key={w} value={w}>Week {w}</option>)}</select></label>}
    {season!=="2026"?<div className="empty-state">Temporada {season}: datos pendientes de Yahoo Fantasy.</div>:loading?<div className="empty-state" role="status">Consultando resultados de 2026…</div>:<>
      {failed.length>0&&<div className="error">No se pudieron consultar las semanas {failed.join(", ")}. Los datos visibles son parciales. <button onClick={reload}>Reintentar</button></div>}
      {mode==="rivalries"&&<div className="rival-score"><TeamLabel team={a}/><div><span className="eyebrow">2026 · VICTORIAS</span><strong>{pair.length?winsA+" – "+winsB:"— : —"}</strong><small>{pair.length} duelos registrados</small></div><TeamLabel team={b}/></div>}
      {!visible.length?<div className="empty-state">No hay enfrentamientos completados disponibles para esta selección.</div>:<div className="table-wrap"><table><thead><tr><th>Semana</th><th>Equipo A</th><th>Equipo B</th><th>Ganador</th></tr></thead><tbody>{visible.map(g=><tr key={g.id}><td>{g.week}</td><td><TeamLabel team={g.team_a}/></td><td><TeamLabel team={g.team_b}/></td><td className="positive-score">{manager(g.winner_choice==="A"?g.team_a:g.team_b)}</td></tr>)}</tbody></table></div>}
    </>}
  </section>;
}
export function Standings({api}) {
  const [rows,setRows]=useState(null),[error,setError]=useState("");
  useEffect(()=>{let active=true;api("/standings").then(v=>{if(active)setRows(v)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[api]);
  return <section className="panel archive-panel"><span className="eyebrow">PICK'EM · 2026</span><h2>Clasificación acumulada</h2>
  {error?<p className="error">{error}</p>:!rows?<p className="muted">Cargando clasificación…</p>:<div className="table-wrap compact-table"><table><thead><tr><th>#</th><th>Jugador</th><th>Fechas completas</th><th>Acumulado</th></tr></thead><tbody>{rows.map((p,i)=><tr key={p.player}><td>{i+1}</td><td><strong>{p.player}</strong></td><td>{p.completed_weeks}</td><td className={p.cumulative_points>=0?"positive-score":"negative-score"}>{p.cumulative_points>0?"+":""}{p.cumulative_points}</td></tr>)}</tbody></table></div>}</section>;
}
