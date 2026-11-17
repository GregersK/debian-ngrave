"""Sørger for at gravér-modulerne i hukommelsen passer sammen.

Ved en opdatering skiftes filerne på disken ud, før tjenesten genstartes. Bliver
genstarten ikke til noget, kører den GAMLE proces videre — og den indlæser
workers.* efterhånden som der er brug for dem. Så kan en ny gcode_worker fra
disken møde en gammel font_manager i hukommelsen, og hvert job fejler.

Dette modul importeres først af gcode_worker, cipher_worker og skilt_worker og
genindlæser de naboer der er ældre end krævet. I en proces der er startet på
den nye version, sker der ingenting.

Ændres en funktion som de andre moduler kalder, så hæv modulets API-tal og
kravet her.
"""
import importlib
import sys

KRAV = {'font_manager': 2}      # modul -> mindste API-tal


def _tjek():
    pakke = __package__ or 'workers'
    for navn, krav in KRAV.items():
        m = sys.modules.get(f'{pakke}.{navn}')
        if m is not None and getattr(m, 'API', 0) < krav:
            bf = sys.modules.get(f'{pakke}.block_font')
            if bf is not None:
                importlib.reload(bf)
            importlib.reload(m)


_tjek()
