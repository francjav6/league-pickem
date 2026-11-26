import {useState} from 'react';
export default function YahooImport({api,week,adminKey,onApplied}) {
  const [file,setFile]=useState(null),[preview,setPreview]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  async function run(confirm=false){
    setBusy(true);setError('');setNotice('');
    try {
      if(!file || file.size>5*1024*1024) throw new Error('Selecciona un HTML de hasta 5 MiB.');
      const headers={'Content-Type':'text/html; charset=utf-8','X-Admin-Key':adminKey};
      if(confirm) headers['X-Import-Digest']=preview.digest;
      const data=await api('/admin/weeks/'+week+'/yahoo/'+(confirm?'confirm':'preview'),{method:'POST',headers,body:await file.text()});
      setPreview(data);
      if(confirm){setNotice(data.already_imported?'Esta fecha ya estaba importada. No se duplicó nada.':'Fecha publicada: dinero y JABA Vault actualizados.');await onApplied();}
    }catch(e){setError(e.message);if(!confirm)setPreview(null)}finally{setBusy(false)}
  }
  return <section className="panel"><span className="eyebrow">WEEK {week} · YAHOO</span><h2>Importar resultados desde HTML</h2><p className="muted">Selecciona el HTML final de Yahoo de esta jornada. La vista previa no cambia la base de datos.</p>
    <input type="file" accept=".html,.htm,text/html" disabled={busy} onChange={e=>{setFile(e.target.files?.[0]||null);setPreview(null);setNotice('');setError('')}}/>
    <button className="primary" disabled={!file||!adminKey||busy} onClick={()=>run(false)}>Previsualizar jornada</button>
    {error&&<div className="error" role="alert">{error}</div>}{notice&&<div className="success" role="status">{notice}</div>}
    {preview&&<><h3>Marcadores finales · {preview.matchups.length} partidos</h3><div className="table-wrap"><table><thead><tr><th>Equipo A</th><th>Marcador</th><th>Equipo B</th><th>Ganador</th></tr></thead><tbody>{preview.matchups.map(m=><tr key={m.id}><td>{m.team_a}</td><td>{m.score_a} – {m.score_b}</td><td>{m.team_b}</td><td>{m.winner_choice==='A'?m.team_a:m.team_b}</td></tr>)}</tbody></table></div>
      <h3>Liquidación prevista</h3><p>Acierto {preview.points_correct} · Error {preview.points_incorrect} · Sin pick {preview.points_missing}</p><div className="table-wrap"><table><thead><tr><th>Jugador</th><th>Aciertos</th><th>Errores</th><th>Sin pick</th><th>Plata fecha</th><th>Acumulado</th></tr></thead><tbody>{preview.players.map(p=><tr key={p.player}><td>{p.player}</td><td>{p.correct}</td><td>{p.wrong}</td><td>{p.missing}</td><td>{p.week_points}</td><td>{p.cumulative_points}</td></tr>)}</tbody></table></div>
      <button className="primary" disabled={busy||preview.saved} onClick={()=>run(true)}>{preview.saved?'Fecha guardada':'Confirmar y publicar fecha'}</button></>}
  </section>
}
