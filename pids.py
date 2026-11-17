# coding: utf-8
# Mapeamento de PIDs validado para ECU Magneti Marelli IAW 4AM (Pajero TR4 Flex)
import math

def _u16(b, idx=0):
    if len(b) < idx + 2: return None
    return (b[idx] << 8) | b[idx + 1]

def _s16(b, idx=0):
    v = _u16(b, idx)
    if v is None: return None
    return v - 65536 if v >= 32768 else v

def _u8(b, idx=0):
    if len(b) <= idx: return None
    return b[idx]

def _num(v, fator=1.0, casas=1):
    return round(v * fator, casas) if v is not None else 0.0

def _calc_tps(b):
    v = _u16(b, 8)
    if v is None: return 0.0
    pct = ((v - 1.0) / 835.0) * 100.0
    return round(max(0.0, min(100.0, pct)), 1)

def _calc_trim_156(b):
    a = _u8(b, 0)
    if a is None: return None
    return round(((a - 156.0) / 156.0) * 100.0, 1)

def _calc_etanol_flex(b):
    v = _u8(b, 1) if len(b) > 1 else _u8(b, 0)
    if v is None: return 0.0
    pct = (v / 255.0) * 100.0
    return round(max(0.0, min(100.0, pct)), 1)

def _calc_temp_agua(b):
    v = _u8(b, 7) if len(b) > 7 else _u8(b, 6)
    if v is None: v = 70
    temp = float(v) - 20.0 if v > 40 else float(v)
    return round(max(-10.0, min(140.0, temp)), 1)

def _calc_temp_ar(b):
    v = _u8(b, 5) if len(b) > 5 else _u8(b, 4)
    if v is None: return 25.0
    return round(float(v) - 20.0, 1)

def _calc_avanco(b):
    v = _s16(b, 18)
    if v is None: return 0.0
    deg = round(v * 0.1, 1)
    return deg if -15.0 <= deg <= 55.0 else 0.0

def _calc_knock_sensor_v(b):
    v = _u16(b, 0)
    if v is not None and v <= 5000:
        return round(v / 1000.0, 2)
    a = _u8(b, 0)
    if a is None: return 0.0
    return round((a / 255.0) * 5.0, 2)

def _calc_corr_ign(b):
    v = _s16(b, 0)
    if v is None: return 0.0
    deg = round(v * 0.1, 1)
    return deg if -25.0 <= deg <= 25.0 else 0.0

def _calc_knock_cil(b, offset):
    v = _s16(b, offset)
    if v is None: return 0.0
    deg = round(v * 0.1, 1)
    return deg if -25.0 <= deg <= 25.0 else 0.0

def _calc_knock_max_cil(b):
    vals = [d for off in (8, 10, 12, 14) if (d := _calc_knock_cil(b, off)) is not None]
    if not vals: return 0.0
    pior = min(vals)
    return pior if pior < 0.0 else 0.0

PIDS_DB = [
    {"id": "RPM", "nome": "Rotacao Motor (RPM)", "unidade": "rpm", "cmd": "21A2", "rapido": True, "calc": lambda b: _num(_u16(b, 0), 1, 0), "sim": lambda t: 820},
    {"id": "VEL", "nome": "Velocidade", "unidade": "km/h", "cmd": "21A6", "rapido": True, "calc": lambda b: _num(_u16(b, 2), 1, 0), "sim": lambda t: 0},
    {"id": "MAP", "nome": "Pressao Coletor (MAP)", "unidade": "kPa", "cmd": "21A2", "rapido": True, "calc": lambda b: _num(_u16(b, 2), 0.1, 1), "sim": lambda t: 32.5},
    {"id": "ECT", "nome": "Temperatura Agua", "unidade": "C", "cmd": "21A2", "rapido": True, "calc": _calc_temp_agua, "sim": lambda t: 88.0},
    {"id": "TPS", "nome": "Posicao Borboleta (TPS)", "unidade": "%", "cmd": "21A2", "rapido": True, "calc": _calc_tps, "sim": lambda t: 12.0},
    {"id": "LAMBDA_1", "nome": "Sonda Lambda Pre-Cat", "unidade": "mV", "cmd": "2145", "rapido": True, "calc": lambda b: _num(_u16(b, 0), 1, 0), "sim": lambda t: 450},
    {"id": "STFT", "nome": "Integrador Lambda (STFT)", "unidade": "%", "cmd": "2147", "rapido": True, "calc": _calc_trim_156, "sim": lambda t: 1.5},
    {"id": "TI_EFETIVO", "nome": "Tempo de Injecao", "unidade": "ms", "cmd": "21A0", "rapido": True, "calc": lambda b: _num(_u16(b, 16), 0.002, 2), "sim": lambda t: 2.75},
    {"id": "AVANCO", "nome": "Avanco de Ignicao", "unidade": "graus", "cmd": "21A0", "rapido": True, "calc": _calc_avanco, "sim": lambda t: 12.0},
    {"id": "KNOCK_SENSOR", "nome": "Sensor Knock", "unidade": "V", "cmd": "2168", "rapido": False, "calc": _calc_knock_sensor_v, "sim": lambda t: 0.45},
    {"id": "CORR_IGN", "nome": "Atraso Ponto Global Knock", "unidade": "graus", "cmd": "216A", "rapido": False, "calc": _calc_corr_ign, "sim": lambda t: 0.0},
    {"id": "KNOCK_MAX_CIL", "nome": "Pior Atraso Knock (Cilindros)", "unidade": "graus", "cmd": "21A0", "rapido": False, "calc": _calc_knock_max_cil, "sim": lambda t: 0.0},
    {"id": "LTFT", "nome": "Adaptativo Mistura (LTFT)", "unidade": "%", "cmd": "2179", "rapido": False, "calc": _calc_trim_156, "sim": lambda t: 2.0},
    {"id": "ETANOL_REAL", "nome": "Etanol Aprendido (Flex)", "unidade": "%", "cmd": "217B", "rapido": False, "calc": _calc_etanol_flex, "sim": lambda t: 25.0},
    {"id": "IAT", "nome": "Temperatura Ar Admissao", "unidade": "C", "cmd": "21A2", "rapido": False, "calc": _calc_temp_ar, "sim": lambda t: 32.0},
    {"id": "IAC", "nome": "Atuador Marcha Lenta (IAC)", "unidade": "passos", "cmd": "21A2", "rapido": False, "calc": lambda b: _num(_u16(b, 14), 1, 0), "sim": lambda t: 72.0},
    {"id": "CLOSED_LOOP", "nome": "Status da Malha (Loop)", "unidade": "Code", "cmd": "2157", "rapido": False, "calc": lambda b: float(_u8(b, 0) or 0), "sim": lambda t: 2.0}
]

PIDS_VIGILANCIA_BG = {
    "RPM", "VEL", "MAP", "ECT", "TPS", "LAMBDA_1",
    "STFT", "LTFT", "KNOCK_SENSOR", "CORR_IGN", "KNOCK_MAX_CIL", "IAC", "CLOSED_LOOP",
}
