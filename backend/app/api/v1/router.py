from fastapi import APIRouter
from app.api.v1.endpoints import auth, competitions, fixtures, groups, players, results, standings, stats, teams

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["Auth"])
router.include_router(competitions.router, prefix="/competitions", tags=["Competitions"])
router.include_router(teams.router, prefix="/competitions/{competition_id}/teams", tags=["Teams"])
router.include_router(fixtures.router, prefix="/competitions/{competition_id}/fixtures", tags=["Fixtures"])
router.include_router(results.router, prefix="/competitions/{competition_id}/fixtures", tags=["Results"])
router.include_router(standings.router, prefix="/competitions/{competition_id}/standings", tags=["Standings"])
router.include_router(groups.router, prefix="/competitions/{competition_id}/groups", tags=["Groups"])
router.include_router(players.router, prefix="/competitions/{competition_id}/teams/{team_id}/players", tags=["Players"])
router.include_router(stats.router, prefix="/competitions/{competition_id}/stats", tags=["Stats"])
