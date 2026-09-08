from datetime import datetime

from main import Matchup, SessionLocal

WEEKS = {1: [('VENEZUELAN DEMOCRACY', 'La Mike Alstott'), ('0 al TE', 'Glory Warpigs (Col)'), ('Delfincitos', 'Green Badgers'), ("Felipe's First-Rate Team", 'Hasbu Nation'), ('FENICIOS S.A', 'UAI Urquizers'), ("Ex Ol's Syndicate", 'J19'), ('Geriatricos', 'Los Yaguaretés')], 2: [('VENEZUELAN DEMOCRACY', 'Glory Warpigs (Col)'), ('La Mike Alstott', 'UAI Urquizers'), ('0 al TE', "Felipe's First-Rate Team"), ('Delfincitos', 'Geriatricos'), ('FENICIOS S.A', "Ex Ol's Syndicate"), ('Green Badgers', 'Hasbu Nation'), ('J19', 'Los Yaguaretés')], 3: [('VENEZUELAN DEMOCRACY', '0 al TE'), ('La Mike Alstott', 'FENICIOS S.A'), ('Delfincitos', "Felipe's First-Rate Team"), ('Glory Warpigs (Col)', 'Hasbu Nation'), ('Green Badgers', 'Los Yaguaretés'), ("Ex Ol's Syndicate", 'Geriatricos'), ('UAI Urquizers', 'J19')], 4: [('VENEZUELAN DEMOCRACY', 'UAI Urquizers'), ('La Mike Alstott', 'Delfincitos'), ('0 al TE', "Ex Ol's Syndicate"), ("Felipe's First-Rate Team", 'J19'), ('FENICIOS S.A', 'Glory Warpigs (Col)'), ('Green Badgers', 'Geriatricos'), ('Hasbu Nation', 'Los Yaguaretés')], 5: [('VENEZUELAN DEMOCRACY', 'FENICIOS S.A'), ('La Mike Alstott', 'Green Badgers'), ('0 al TE', 'UAI Urquizers'), ('Delfincitos', 'Los Yaguaretés'), ("Felipe's First-Rate Team", 'Geriatricos'), ('Glory Warpigs (Col)', 'J19'), ('Hasbu Nation', "Ex Ol's Syndicate")], 6: [('VENEZUELAN DEMOCRACY', 'Los Yaguaretés'), ('La Mike Alstott', 'Hasbu Nation'), ('0 al TE', 'Delfincitos'), ("Felipe's First-Rate Team", 'UAI Urquizers'), ('FENICIOS S.A', 'Green Badgers'), ('Glory Warpigs (Col)', "Ex Ol's Syndicate"), ('Geriatricos', 'J19')], 7: [('VENEZUELAN DEMOCRACY', 'J19'), ('La Mike Alstott', 'Los Yaguaretés'), ('0 al TE', 'FENICIOS S.A'), ('Delfincitos', "Ex Ol's Syndicate"), ("Felipe's First-Rate Team", 'Green Badgers'), ('Glory Warpigs (Col)', 'Geriatricos'), ('Hasbu Nation', 'UAI Urquizers')], 8: [('VENEZUELAN DEMOCRACY', 'Delfincitos'), ('La Mike Alstott', 'J19'), ('0 al TE', 'Hasbu Nation'), ("Felipe's First-Rate Team", "Ex Ol's Syndicate"), ('FENICIOS S.A', 'Geriatricos'), ('Glory Warpigs (Col)', 'Los Yaguaretés'), ('Green Badgers', 'UAI Urquizers')], 9: [('VENEZUELAN DEMOCRACY', 'Green Badgers'), ('La Mike Alstott', "Ex Ol's Syndicate"), ('0 al TE', 'Geriatricos'), ('Delfincitos', 'FENICIOS S.A'), ("Felipe's First-Rate Team", 'Glory Warpigs (Col)'), ('Hasbu Nation', 'J19'), ('UAI Urquizers', 'Los Yaguaretés')], 10: [('VENEZUELAN DEMOCRACY', "Felipe's First-Rate Team"), ('La Mike Alstott', 'Glory Warpigs (Col)'), ('0 al TE', 'Green Badgers'), ('Delfincitos', 'J19'), ('FENICIOS S.A', 'Los Yaguaretés'), ('Hasbu Nation', 'Geriatricos'), ("Ex Ol's Syndicate", 'UAI Urquizers')], 11: [('VENEZUELAN DEMOCRACY', 'Hasbu Nation'), ('La Mike Alstott', '0 al TE'), ('Delfincitos', 'Glory Warpigs (Col)'), ("Felipe's First-Rate Team", 'Los Yaguaretés'), ('FENICIOS S.A', 'J19'), ('Green Badgers', "Ex Ol's Syndicate"), ('Geriatricos', 'UAI Urquizers')], 12: [('VENEZUELAN DEMOCRACY', 'Geriatricos'), ('La Mike Alstott', "Felipe's First-Rate Team"), ('0 al TE', 'J19'), ('Delfincitos', 'UAI Urquizers'), ('FENICIOS S.A', 'Hasbu Nation'), ('Glory Warpigs (Col)', 'Green Badgers'), ("Ex Ol's Syndicate", 'Los Yaguaretés')], 13: [('VENEZUELAN DEMOCRACY', "Ex Ol's Syndicate"), ('La Mike Alstott', 'Geriatricos'), ('0 al TE', 'Los Yaguaretés'), ('Delfincitos', 'Hasbu Nation'), ("Felipe's First-Rate Team", 'FENICIOS S.A'), ('Glory Warpigs (Col)', 'UAI Urquizers'), ('Green Badgers', 'J19')], 14: [('VENEZUELAN DEMOCRACY', 'La Mike Alstott'), ('0 al TE', 'Glory Warpigs (Col)'), ('Delfincitos', 'Green Badgers'), ("Felipe's First-Rate Team", 'Hasbu Nation'), ('FENICIOS S.A', 'UAI Urquizers'), ("Ex Ol's Syndicate", 'J19'), ('Geriatricos', 'Los Yaguaretés')]}

WEEK_LOCKS_UTC = {1: '2026-09-10T00:20:00+00:00', 2: '2026-09-18T00:15:00+00:00', 3: '2026-09-25T00:15:00+00:00', 4: '2026-10-02T00:15:00+00:00', 5: '2026-10-09T00:15:00+00:00', 6: '2026-10-16T00:15:00+00:00', 7: '2026-10-23T00:15:00+00:00', 8: '2026-10-30T00:15:00+00:00', 9: '2026-11-06T01:15:00+00:00', 10: '2026-11-13T01:15:00+00:00', 11: '2026-11-20T01:15:00+00:00', 12: '2026-11-26T01:00:00+00:00', 13: '2026-12-04T01:15:00+00:00', 14: '2026-12-11T01:15:00+00:00'}

db = SessionLocal()

try:
    total_added = 0

    for week, games in WEEKS.items():
        lock_at = datetime.fromisoformat(WEEK_LOCKS_UTC[week])

        existing_rows = (
            db.query(Matchup)
            .filter(Matchup.week == week)
            .order_by(Matchup.id)
            .all()
        )

        existing_pairs = {(m.team_a, m.team_b) for m in existing_rows}

        for team_a, team_b in games:
            if (team_a, team_b) not in existing_pairs:
                db.add(
                    Matchup(
                        week=week,
                        team_a=team_a,
                        team_b=team_b,
                        starts_at=lock_at,
                        manually_locked=False,
                    )
                )
                total_added += 1

        # Flush para incluir los recién creados.
        db.flush()

        # Sin borrar picks ni resultados existentes, sincronizamos el cierre
        # de TODOS los matchups de la semana con el primer kickoff NFL.
        for matchup in db.query(Matchup).filter(Matchup.week == week).all():
            matchup.starts_at = lock_at

        db.commit()
        print(
            f"Week {week}: lock = {WEEK_LOCKS_UTC[week]} UTC; "
            f"{len(games)} matchups expected."
        )

    print(f"Done. New matchups added: {total_added}. Existing picks were preserved.")
finally:
    db.close()
