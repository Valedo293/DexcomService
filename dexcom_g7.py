"""Accesso alle letture Dexcom G7 tramite Dexcom Share.

Il G7 pubblica le letture sullo stesso servizio Share usato dalle generazioni
precedenti. Questa classe centralizza la configurazione, in particolare la
regione dell'account, così che tutti gli endpoint dell'app usino il server
corretto.
"""

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from pydexcom import Dexcom


@dataclass(frozen=True)
class G7Reading:
    value: float
    trend_description: str
    trend_arrow: str
    time: datetime


class DexcomG7Client:
    """Piccolo adapter per le letture G7 disponibili in Dexcom Share."""

    def __init__(self, username: str, password: str, region: str = "OUS"):
        if not username or not password:
            raise ValueError("DEXCOM_USERNAME e DEXCOM_PASSWORD sono obbligatori")

        normalized_region = region.strip().upper()
        if normalized_region not in {"US", "OUS"}:
            raise ValueError("DEXCOM_REGION deve essere US oppure OUS")

        self._dexcom = Dexcom(username, password, ous=normalized_region == "OUS")

    @classmethod
    def from_environment(cls):
        return cls(
            os.getenv("DEXCOM_USERNAME", ""),
            os.getenv("DEXCOM_PASSWORD", ""),
            os.getenv("DEXCOM_REGION", "OUS"),
        )

    def get_current_reading(self) -> Optional[G7Reading]:
        reading = self._dexcom.get_current_glucose_reading()
        if reading is None:
            return None

        return G7Reading(
            value=float(reading.value),
            trend_description=reading.trend_description,
            trend_arrow=reading.trend_arrow or "-",
            time=reading.time,
        )


def get_g7_reading() -> Optional[G7Reading]:
    """Crea una sessione Share G7 e restituisce la lettura corrente."""

    return DexcomG7Client.from_environment().get_current_reading()
