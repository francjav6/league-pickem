"""Private, versioned JABA analytics snapshot. No writes to picks or users."""
import hashlib
import json
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import Column, Integer, Text, String
from sqlalchemy.exc import IntegrityError

MAX_BYTES = 5 * 1024 * 1024

def validate_snapshot(d):
    if not isinstance(d, dict) or d.get("version") != 1:
        raise ValueError("Formato de archivo no reconocido")
    years = {str(y) for y in range(2017, 2027)}
    if set(d.get("seasons", {})) != years or set(d.get("scoring", {})) != years:
        raise ValueError("Se requieren las diez temporadas 2017–2026")
    p, picks, tx = d["players"], d["drafts"], d["transactions"]
    if not (isinstance(p,list) and 1 <= len(p) <= 10000 and isinstance(picks,list) and len(picks)<=10000 and isinstance(tx,list) and len(tx)<=20000):
        raise ValueError("Tamaño de inventario inválido")
    ids=set()
    for x in p:
        if not isinstance(x,dict) or not isinstance(x.get("id"),str) or not x["id"].isdigit() or x["id"] in ids or not isinstance(x.get("name"),str):
            raise ValueError("Identificador de jugador inválido o duplicado")
        ids.add(x["id"])
    seen=set()
    for x in picks:
        if len(x)!=5 or str(x[0]) not in years or not isinstance(x[1],int) or not isinstance(x[2],int) or x[1]<1 or x[2]<1 or not isinstance(x[3],str) or x[4] not in ids or (x[0],x[2]) in seen:
            raise ValueError("Pick inválido o duplicado")
        seen.add((x[0],x[2]))
    seen=set()
    for x in tx:
        if len(x)!=7 or str(x[0]) not in years or not isinstance(x[1],int) or not isinstance(x[2],str) or x[2] in seen or not isinstance(x[4],int) or not isinstance(x[6],list):
            raise ValueError("Transacción inválida o duplicada")
        seen.add(x[2])
        for m in x[6]:
            if len(m)!=3 or not isinstance(m[0],str) or m[1] not in ("adds","drops") or m[2] not in ids:
                raise ValueError("Movimiento inválido")
    for y, ss in d["seasons"].items():
        through=d["scoring"][y]["through"]
        if not isinstance(through,int) or not 1<=through<=18 or (y=="2026" and through>11):
            raise ValueError("Semana de corte inválida")
        for pid,x in ss.items():
            if pid not in ids or not isinstance(x.get("pos"),str) or len(x["weeks"])!=through or any(v is not None and (type(v) is not int or abs(v)>100000) for v in x["weeks"]):
                raise ValueError("Serie semanal inválida")
            if x["total"]!=sum(v for v in x["weeks"] if v is not None) or x["games"]!=sum(v is not None for v in x["weeks"]) or not 1<=x["rank"]<=x["pool"]:
                raise ValueError("Totales de jugador inconsistentes")
    if not isinstance(d.get("validation"),dict) or not isinstance(d.get("notes"),list):
        raise ValueError("Faltan metadatos")
    return d

def install(app, Base, engine, get_db, require_admin, get_current_user):
    class AnalyticsSnapshot(Base):
        __tablename__="jaba_analytics_snapshots"
        id=Column(Integer,primary_key=True)
        sha256=Column(String(64),nullable=False)
        payload=Column(Text,nullable=False)

    AnalyticsSnapshot.__table__.create(bind=engine,checkfirst=True)

    @app.get("/history/analytics")
    def get_analytics(user=Depends(get_current_user),db=Depends(get_db)):
        row=db.get(AnalyticsSnapshot,1)
        if not row:
            raise HTTPException(404,"Todavía no se ha publicado la base de jugadores")
        return Response(row.payload,media_type="application/json",headers={"Cache-Control":"no-store"})

    @app.post("/admin/history/analytics",dependencies=[Depends(require_admin)])
    async def publish_analytics(request:Request,user=Depends(get_current_user),db=Depends(get_db)):
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>MAX_BYTES:
                raise HTTPException(413,"Archivo demasiado grande")
        try:
            data=validate_snapshot(json.loads(raw))
            payload=json.dumps(data,ensure_ascii=False,separators=(",",":"),allow_nan=False)
        except (ValueError,TypeError,KeyError,AttributeError,IndexError):
            raise HTTPException(422,"Archivo de estadísticas inválido")
        digest=hashlib.sha256(payload.encode("utf-8")).hexdigest()
        row=db.get(AnalyticsSnapshot,1)
        if row:
            if row.sha256==digest:
                return {"saved":True,"unchanged":True,"sha256":digest}
            raise HTTPException(409,"Ya existe una base publicada. No se sobrescribe automáticamente.")
        db.add(AnalyticsSnapshot(id=1,sha256=digest,payload=payload))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409,"Ya existe una publicación simultánea")
        return {"saved":True,"sha256":digest}
