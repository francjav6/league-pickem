"""Pruebas de importación aisladas; no utilizan la DB de producción."""
import unittest, tempfile
from html import escape
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from yahoo_import import BASELINE, TEAMS, install

class ImportTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.engine=create_engine('sqlite:///'+self.temp.name+'/test.db',connect_args={'check_same_thread':False})
        Base=declarative_base()
        class Matchup(Base):
            __tablename__='matchups';id=Column(Integer,primary_key=True);week=Column(Integer);team_a=Column(String);team_b=Column(String);winner_choice=Column(String);manually_locked=Column(Boolean,default=True)
        class User(Base):
            __tablename__='users';id=Column(Integer,primary_key=True);name=Column(String)
        class Pick(Base):
            __tablename__='picks';id=Column(Integer,primary_key=True);user_id=Column(Integer);matchup_id=Column(Integer);choice=Column(String)
        self.Matchup=Matchup;self.Pick=Pick;Base.metadata.create_all(self.engine);self.Session=sessionmaker(bind=self.engine,autoflush=False)
        def db():
            with self.Session() as session:yield session
        def admin(x_admin_key:str=Header(default='')):
            if x_admin_key!='test-admin':raise HTTPException(403,'admin')
        def user(authorization:str=Header(default='')):
            if authorization!='Bearer test':raise HTTPException(401,'login')
        self.app=FastAPI();install(self.app,Base,self.engine,db,admin,user,Matchup,User,Pick,lambda m:m.manually_locked,lambda s,u,w:(30,1),(10,-5,0))
        self.client=TestClient(self.app)
        self.admin={'X-Admin-Key':'test-admin','Content-Type':'text/html'}
        self.pairs=[(9,12),(1,4),(2,14),(3,13),(5,8),(6,7),(10,16)]
        with self.Session() as s:
            for i,(a,b) in enumerate(self.pairs,1):s.add(Matchup(id=i,week=12,team_a=TEAMS[b]['team'],team_b=TEAMS[a]['team'],manually_locked=True))
            s.add(User(id=1,name='Prueba'));s.add_all([Pick(user_id=1,matchup_id=1,choice='B'),Pick(user_id=1,matchup_id=2,choice='A')]);s.commit()
    def tearDown(self):self.engine.dispose();self.temp.cleanup()
    def html(self,week=12,final=True,tie=False,delta=0,missing=False):
        parts=[f'<html><head><title>JABA LEAGUE | Fantasy Football</title><link rel="canonical" href="https://football.fantasysports.yahoo.com/f1/960962?matchup_week={week}&amp;module=matchups"></head><body><section><h2>Week {week} Matchups</h2><p>{"Final results" if final else "Live results"}</p><ul>']
        for a,b in self.pairs[:-1] if missing else self.pairs:
            parts.append(f'<li class="Listitem" data-target="/f1/960962/matchup?week={week}&amp;mid1={a}&amp;mid2={b}">')
            for i,score in [(a,60+delta),(b,60+delta if tie else 40)]:parts.append(f'<div class="Grid-u-6-13"><a class="F-link" href="/f1/960962/{i}">{escape(TEAMS[i]["team"])}</a><div class="Fz-lg">{score:.2f}</div></div>')
            parts.append('</li>')
        return ''.join(parts)+'</ul></section></body></html>'
    def preview(self,html=None):return self.client.post('/admin/weeks/12/yahoo/preview',content=html or self.html(),headers=self.admin)
    def test_transaction_and_idempotence(self):
        p=self.preview();self.assertEqual(p.status_code,200,p.text);d=p.json();self.assertEqual(d['players'][0]['week_points'],5);self.assertEqual(d['players'][0]['cumulative_points'],35)
        with self.Session() as s:self.assertTrue(all(m.winner_choice is None for m in s.query(self.Matchup).all()))
        h={**self.admin,'X-Import-Digest':d['digest']};res=self.client.post('/admin/weeks/12/yahoo/confirm',content=self.html(),headers=h);self.assertEqual(res.status_code,200,res.text)
        with self.Session() as s:self.assertTrue(all(m.winner_choice=='B' for m in s.query(self.Matchup).all()));self.assertEqual(s.query(self.Pick).count(),2)
        res=self.client.post('/admin/weeks/12/yahoo/confirm',content=self.html(),headers=h);self.assertTrue(res.json()['already_imported'])
        hist=self.client.get('/history/vault',headers={'Authorization':'Bearer test'}).json();self.assertEqual(len(hist['matches']),len(BASELINE['matches'])+7);self.assertEqual(len([m for m in hist['matches'] if m['y']==2026 and m['w']==12]),7);self.assertTrue(all(x['g']==12 for x in hist['standings'] if x['y']==2026))
        self.assertEqual(self.preview(self.html(delta=1)).status_code,409)
    def test_invalid_uploads(self):
        for h in [self.html(week=11),self.html(final=False),self.html(tie=True),self.html(missing=True)]:self.assertEqual(self.preview(h).status_code,409)
        self.assertEqual(self.client.post('/admin/weeks/12/yahoo/preview',content=self.html()).status_code,403)
        self.assertEqual(self.client.get('/history/vault').status_code,401)
        p=self.preview().json();self.assertEqual(self.client.post('/admin/weeks/12/yahoo/confirm',content=self.html(delta=1),headers={**self.admin,'X-Import-Digest':p['digest']}).status_code,409)
        with self.Session() as s:
            m=s.get(self.Matchup,1);m.winner_choice='A';s.commit()
        self.assertEqual(self.preview().status_code,409)
    def test_locked(self):
        with self.Session() as s:m=s.get(self.Matchup,1);m.manually_locked=False;s.commit()
        self.assertEqual(self.preview().status_code,409)

if __name__=='__main__':unittest.main()
