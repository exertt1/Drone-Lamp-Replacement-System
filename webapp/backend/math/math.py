import math
from webapp.backend.models.models import EnergyModel, DroneModel


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def energy_required_pct(dist_m_to_lamp: float, dist_m_back: float) -> float:
    dist_km = (dist_m_to_lamp + dist_m_back) / 1000.0
    return dist_km * EnergyModel.ENERGY_PER_KM_PCT + EnergyModel.TAKEOFF_LAND_PCT + EnergyModel.WORK_COST_PCT + EnergyModel.SAFETY_MARGIN_PCT

def speed_mps() -> float:
    return DroneModel.AVG_SPEED_KMH * 1000.0 / 3600.0