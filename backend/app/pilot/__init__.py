from functools import lru_cache

from app.config import settings
from app.pilot.base import PilotProfile
from app.pilot.cle import CLE_PROFILE

_REGISTRY: dict[str, PilotProfile] = {"cle": CLE_PROFILE}


def load_profile(profile_id: str) -> PilotProfile:
    try:
        return _REGISTRY[profile_id]
    except KeyError as exc:
        raise RuntimeError(
            f"Unknown PILOT_PROFILE '{profile_id}'. Known: {sorted(_REGISTRY)}"
        ) from exc


@lru_cache(maxsize=1)
def get_pilot_profile() -> PilotProfile:
    return load_profile(settings.pilot_profile)
