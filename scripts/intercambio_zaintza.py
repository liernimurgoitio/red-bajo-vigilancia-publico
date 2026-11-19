"""Validación estricta del intercambio ficticio v1 de Zaintza SOC."""
from datetime import datetime
import re


def campos(valor, nombres):
    return isinstance(valor, dict) and set(valor) == set(nombres.split())


def validar_intercambio(valor):
    error = 'Archivo de intercambio no válido. Utiliza una exportación ficticia v1 de Zaintza SOC.'
    if (not campos(valor, 'format version environment sourceInstanceId detection')
        or valor['format'] != 'zaintza-laguntza' or type(valor['version']) is not int or valor['version'] != 1
        or valor['environment'] != 'demo' or valor['sourceInstanceId'] != 'zaintza-demo-v1'):
        raise ValueError(error)
    d = valor['detection']
    if (not campos(d, 'id ruleId firstSeen lastSeen eventCount evidenceRefs')
        or d['ruleId'] not in ('ZAINTZA-AUTH-001', 'ZAINTZA-AUTH-002')
        or type(d['eventCount']) is not int or not 5 <= d['eventCount'] <= 100
        or not isinstance(d['evidenceRefs'], list) or len(d['evidenceRefs']) != d['eventCount']
        or any(not isinstance(ref, str) or not re.fullmatch(r'DEMO-4625-[0-9]{1,12}', ref) for ref in d['evidenceRefs'])):
        raise ValueError(error)
    refs = sorted(d['evidenceRefs'])
    if len(set(refs)) != len(refs) or not isinstance(d['id'], str) or d['id'] not in [d['ruleId'] + ':' + ref for ref in refs]:
        raise ValueError(error)
    fechas = []
    for nombre in ('firstSeen', 'lastSeen'):
        v = d[nombre]
        if not isinstance(v, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z', v):
            raise ValueError(error)
        try:
            fechas.append(datetime.fromisoformat(v.replace('Z', '+00:00')))
        except ValueError as problema:
            raise ValueError(error) from problema
    if not 0 <= (fechas[1] - fechas[0]).total_seconds() <= 300:
        raise ValueError(error)
    return {**valor, 'detection': {**d, 'evidenceRefs': refs}}
