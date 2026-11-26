"""Importación transaccional de resultados Yahoo, JABA 2026 (temporada regular)."""
import hashlib
import json
import re
import unicodedata
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from bs4 import BeautifulSoup
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.exc import IntegrityError

SEASON, LEAGUE, MAX_WEEK, MAX_BYTES = 2026, 960962, 14, 5*1024*1024
BASELINE = json.loads(Path(__file__).with_name('vault_baseline.json').read_text(encoding='utf-8'))
TEAMS = {x['id']: x for x in BASELINE['standings'] if x['y']==SEASON and x['l']==LEAGUE}
LAST_BASE = max(x['w'] for x in BASELINE['matches'] if x['y']==SEASON)

class ImportProblem(ValueError): pass

def norm(s):
    return ' '.join(unicodedata.normalize('NFKC',s).replace('’',"'").casefold().split())

def key(a,b): return tuple(sorted((norm(a),norm(b))))

def parse_html(raw, week):
    if not 1 <= week <= MAX_WEEK: raise ImportProblem('Solo se admiten semanas 1–14 de 2026.')
    if len(raw)>MAX_BYTES: raise ImportProblem('Archivo demasiado grande (máx. 5 MiB).')
    try: html=raw.decode('utf-8-sig')
    except UnicodeDecodeError: raise ImportProblem('Guarda el HTML en UTF-8.')
    head=BeautifulSoup(html.split('</head>',1)[0], 'html.parser')
    c=head.select_one('link[rel=canonical]')
    if not c: raise ImportProblem('No se encuentra la URL canónica de Yahoo.')
    u=urlsplit(c.get('href','')); q=parse_qs(u.query)
    if u.scheme!='https' or u.hostname!='football.fantasysports.yahoo.com' or u.path.rstrip('/') not in {f'/f1/{LEAGUE}',f'/{SEASON}/f1/{LEAGUE}'} or q.get('matchup_week')!=[str(week)] or q.get('module')!=['matchups']:
        raise ImportProblem('El archivo no corresponde a la liga, temporada y semana seleccionadas.')
    if not re.search(r'<title>\s*JABA LEAGUE\s*\|',html,re.I): raise ImportProblem('No es la página de JABA LEAGUE.')
    marker=f'Week {week} Matchups'
    start=html.find(marker); end=html.find('</section>',start)
    if start<0 or end<0: raise ImportProblem('No se encuentra el cuadro de enfrentamientos.')
    block=BeautifulSoup(html[start:end],'html.parser')
    first=block.select_one('li.Listitem')
    if not first or not any(str(t).strip()=='Final results' for t in block.strings):
        raise ImportProblem('Yahoo no indica Final results. No se puede liquidar una jornada en curso.')
    if any('bracket' in p.get_text(' ',strip=True).lower() for p in block.find_all('p')):
        raise ImportProblem('La importación automática actual solo cubre temporada regular.')
    games=[]; seen=set()
    for li in block.select('li.Listitem'):
        sides=li.select('div.Grid-u-6-13')
        if len(sides)!=2: raise ImportProblem('Enfrentamiento incompleto o bye inesperado.')
        target=urlsplit(li.get('data-target','')); tq=parse_qs(target.query)
        if target.path not in {f'/f1/{LEAGUE}/matchup',f'/{SEASON}/f1/{LEAGUE}/matchup'} or tq.get('week')!=[str(week)]: raise ImportProblem('Identificador de partido incompatible.')
        pair=[]
        for side in sides:
            a=side.select_one('a.F-link'); score=side.select_one('div.Fz-lg')
            if not a or not score: raise ImportProblem('Equipo o marcador ausente.')
            link=urlsplit(a.get('href','')); mt=re.fullmatch(r'(?:/2026)?/f1/960962/(\d+)',link.path)
            if not mt or (link.netloc and link.hostname!='football.fantasysports.yahoo.com'): raise ImportProblem('URL de equipo incompatible.')
            tid=int(mt.group(1)); team=TEAMS.get(tid)
            if not team or norm(a.get_text(' ',strip=True))!=norm(team['team']): raise ImportProblem('Nombre o ID de equipo no reconocido. Requiere revisión.')
            if tid in seen: raise ImportProblem('Equipo repetido en la jornada.')
            seen.add(tid)
            v=score.get_text(strip=True)
            if not re.fullmatch(r'-?\d{1,4}\.\d{2}',v): raise ImportProblem('Marcador inválido o no definitivo.')
            pair.append((tid,int(Decimal(v)*100)))
        if {str(x[0]) for x in pair}!={*tq.get('mid1',[]),*tq.get('mid2',[])}: raise ImportProblem('IDs del partido no coinciden.')
        (ia,sa),(ib,sb)=sorted(pair)
        if sa==sb: raise ImportProblem('Empate: el Pick’em actual solo admite A/B. Revisión manual necesaria.')
        a,b=TEAMS[ia],TEAMS[ib]
        games.append(dict(y=SEASON,l=LEAGUE,w=week,ia=ia,ib=ib,ta=a['team'],tb=b['team'],a=a['n'],b=b['n'],sa=sa,sb=sb,win=1 if sa>sb else 2,p='regular'))
    if len(games)!=7 or seen!=set(TEAMS): raise ImportProblem('La jornada debe tener exactamente siete partidos y los catorce equipos.')
    return sorted(games,key=lambda x:(x['ia'],x['ib']))

def signature(games):
    return sorted((min(g['ia'],g['ib']),max(g['ia'],g['ib']),g['sa'] if g['ia']<g['ib'] else g['sb'],g['sb'] if g['ia']<g['ib'] else g['sa']) for g in games)

def digest(games): return hashlib.sha256(json.dumps(signature(games),separators=(',',':')).encode()).hexdigest()

def merge_vault(imports):
    d=json.loads(json.dumps(BASELINE)); byweek={r.week:json.loads(r.payload) for r in imports}
    new=[w for w in byweek if w>LAST_BASE]
    if not new: return d
    d['matches'].extend(g for w in sorted(new) for g in byweek[w]); d['matches'].sort(key=lambda x:(x['y'],x['w'],x['ia'],x['ib']))
    for w in sorted(new): d['coverage'].append(dict(y=SEASON,w=w,g=7,expected=7,status='complete_week_in_progress_season'))
    s=[x for x in d['standings'] if x['y']==SEASON]; teams={x['id']:x for x in s}
    for x in s:
        for k in ('g','w','d','t','pf','pa'): x[k]=0
    for g in d['matches']:
        if g['y']!=SEASON or g['p']!='regular': continue
        for i,j,side in [('ia','ib',1),('ib','ia',2)]:
            x=teams[g[i]]; x['g']+=1; x['w']+=int(g['win']==side); x['d']+=int(g['win']==3-side); x['t']+=int(g['win']==0); x['pf']+=g['sa' if side==1 else 'sb']; x['pa']+=g['sb' if side==1 else 'sa']
    for rank,x in enumerate(sorted(s,key=lambda x:(-(2*x['w']+x['t']),-x['pf'],x['id'])),1): x['rank']=rank
    d['standings'].sort(key=lambda x:(-x['y'],x['rank']))
    return d

def install(app,Base,engine,get_db,require_admin,get_current_user,Matchup,User,Pick,matchup_locked,cumulative_points_through,points):
    class YahooWeekImport(Base):
        __tablename__='yahoo_week_imports'
        id=Column(Integer,primary_key=True)
        season=Column(Integer,nullable=False)
        league_id=Column(Integer,nullable=False)
        week=Column(Integer,nullable=False)
        sha256=Column(String(64),nullable=False)
        payload=Column(Text,nullable=False)
        imported_at=Column(DateTime(timezone=True),nullable=False,default=lambda:datetime.now(timezone.utc))
        __table_args__=(UniqueConstraint('season','league_id','week',name='uq_yahoo_import_week'),)
    YahooWeekImport.__table__.create(engine,checkfirst=True)
    def existing(db,week):
        return db.query(YahooWeekImport).filter_by(season=SEASON,league_id=LEAGUE,week=week).first()
    async def read(request):
        buf=bytearray()
        async for part in request.stream():
            if len(buf)+len(part)>MAX_BYTES: raise HTTPException(413,'Archivo demasiado grande (máx. 5 MiB).')
            buf.extend(part)
        return bytes(buf)
    def prepare(db,week,games,lock=False):
        q=db.query(Matchup).filter(Matchup.week==week).order_by(Matchup.id)
        rows=q.with_for_update().all() if lock else q.all()
        if len(rows)!=7 or len({key(m.team_a,m.team_b) for m in rows})!=7: raise ImportProblem('El calendario Pick’em debe contener siete partidos únicos.')
        if not all(matchup_locked(m) for m in rows): raise ImportProblem('Los picks aún no están cerrados.')
        pairs={key(g['ta'],g['tb']):g for g in games}
        if set(pairs)!={key(m.team_a,m.team_b) for m in rows}: raise ImportProblem('Los enfrentamientos Yahoo no coinciden con el calendario Pick’em.')
        base=[g for g in BASELINE['matches'] if g['y']==SEASON and g['w']==week]
        if base and signature(base)!=signature(games): raise ImportProblem('El marcador difiere del histórico consolidado; no se sobrescribe automáticamente.')
        old=existing(db,week)
        if old and old.sha256!=digest(games): raise ImportProblem('La semana ya está importada con otros marcadores; requiere revisión.')
        if week>LAST_BASE+1 and not all(existing(db,w) for w in range(LAST_BASE+1,week)): raise ImportProblem('Importa primero las jornadas anteriores que faltan en el histórico.')
        winners={}; out=[]
        for m in rows:
            g=pairs[key(m.team_a,m.team_b)]; forward=norm(m.team_a)==norm(g['ta']); sa,sb=(g['sa'],g['sb']) if forward else (g['sb'],g['sa']); win='A' if sa>sb else 'B'
            if m.winner_choice not in (None,win): raise ImportProblem(f'Resultado manual contradictorio: {m.team_a} vs {m.team_b}. No se modifica.')
            if old and m.winner_choice!=win: raise ImportProblem("La fecha importada no coincide con los ganadores guardados; requiere revisión.")
            winners[m.id]=win;out.append(dict(id=m.id,team_a=m.team_a,team_b=m.team_b,score_a=f'{Decimal(sa)/100:.2f}',score_b=f'{Decimal(sb)/100:.2f}',winner_choice=win))
        picks={(p.user_id,p.matchup_id):p.choice for p in db.query(Pick).filter(Pick.matchup_id.in_(list(winners))).all()}
        players=[]
        for u in db.query(User).all():
            c=e=missing=0
            for mid,win in winners.items():
                choice=picks.get((u.id,mid)); c+=choice==win; e+=choice is not None and choice!=win; missing+=choice is None
            value=c*points[0]+e*points[1]+missing*points[2]; previous,_=cumulative_points_through(db,u,week-1)
            players.append(dict(player=u.name,correct=c,wrong=e,missing=missing,week_points=value,cumulative_points=previous+value))
        players.sort(key=lambda p:(-p['week_points'],-p['correct'],p['player'].casefold()))
        return rows,winners,old,dict(week=week,season=SEASON,digest=digest(games),already_imported=bool(old),matchups=out,players=players,points_correct=points[0],points_incorrect=points[1],points_missing=points[2])
    @app.post('/admin/weeks/{week}/yahoo/preview',dependencies=[Depends(require_admin)])
    async def preview(week:int,request:Request,db=Depends(get_db)):
        try: return prepare(db,week,parse_html(await read(request),week))[3]
        except ImportProblem as e: raise HTTPException(409,str(e))
    @app.post('/admin/weeks/{week}/yahoo/confirm',dependencies=[Depends(require_admin)])
    async def confirm(week:int,request:Request,x_import_digest:str=Header(...),db=Depends(get_db)):
        try:
            games=parse_html(await read(request),week)
            if digest(games)!=x_import_digest: raise ImportProblem('El archivo cambió; vuelve a previsualizar.')
            rows,winners,old,result=prepare(db,week,games,lock=True)
            if not old:
                for m in rows: m.winner_choice=winners[m.id];m.manually_locked=True
                db.add(YahooWeekImport(season=SEASON,league_id=LEAGUE,week=week,sha256=digest(games),payload=json.dumps(games,ensure_ascii=False)))
                db.commit()
            result['saved']=True
            return result
        except ImportProblem as e: db.rollback();raise HTTPException(409,str(e))
        except IntegrityError: db.rollback();raise HTTPException(409,'Importación concurrente; vuelve a previsualizar.')
    @app.get('/history/vault',dependencies=[Depends(get_current_user)])
    def vault(db=Depends(get_db)):
        return merge_vault(db.query(YahooWeekImport).filter_by(season=SEASON,league_id=LEAGUE).all())
    return existing
