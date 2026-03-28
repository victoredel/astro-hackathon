from fastapi import APIRouter, Query
from pipeline.orbital_collision import calculate_orbital_risk

router = APIRouter(prefix="/orbital", tags=["Orbital Mechanics"])

@router.get("/collision-risk")
async def get_collision_risk(storm_prob: float = Query(default=25.0, ge=0.0, le=100.0)):
    """
    Calcula el riesgo de colisión orbital modificando el arrastre termosférico (BSTAR)
    basado en la probabilidad de tormenta solar.
    """
    result = calculate_orbital_risk(storm_prob=storm_prob)
    return result
