from fastapi import APIRouter, Depends

from eman.db import get_db

router = APIRouter()


@router.get("/tags")
def list_tags(db=Depends(get_db)):
    rows = db.execute("SELECT name FROM tag ORDER BY name").fetchall()
    return {"tags": [r["name"] for r in rows]}
