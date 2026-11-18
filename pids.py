# coding: utf-8
# Mapa de leitura da ECU Magneti Marelli IAW 4AM (Pajero TR4 2.0 16V Flex), KWP2000 modo 21.
# "b" e a lista de bytes DEPOIS do cabecalho "61 xx".
# Valores de 16 bits sao big-endian.
import math


def _u16(b, idx=0):
    if len(b) < idx + 2:
        return None
    return (b[idx] << 8) | b[idx + 1]


def _s16(b, idx=0):
    v = _u16(b, idx)
    if v is None:
        return None
    return v - 65536 if v >= 32768 else v


def _u8(b, idx=0):
    if len(b) <= idx:
        return None
    return b[idx]


def _num(v, fator=1.0, casas=1):
    return round(v * fator, casas) if v is not None else 0.0


def _calc_tps(b):
    v = _u16(b, 8)
    if v is None:
        return 0.0
    pct = ((v - 1.0) / 835.0) * 100.0
    return round(max(0.0, min(100.0, pct)), 1)


def _calc_trim_156(b):
    a = _u8(b, 0)
    if a is None:
        return None
    return round(((a - 156.0) / 156.0) * 100.0, 1)


def _calc_etanol(b):
    v = _u16(b, 0)
    if v is None:
        return None
    val = 27.0 + ((132.0 - v) * 1.736)
    return round(max(0.0, min(100.0, val)), 1)


def _calc_temp(b, idx):
    v = _u16(b, idx)
    if v is None:
        return 0.0
    return round(float(v - 40), 0)


def _calc_avanco(b):
    v = _s16(b, 10)
    if v is None:
        return None
    deg = round((v * 0.25) + 21.0, 1)
    if deg < -15.0 or deg > 55.0:
        return None
    return deg


def _calc_knock_cilindro(b, idx):
    v = _u16(b, idx)
    if v is None:
        return None
    return round((v / 1023.0) * 5.0, 2)


def _calc_knock_noise_v(b):
    raw16 = _u16(b, 0)
    if raw16 is None:
        return None
    return round((raw16 / 1023.0) * 5.0, 2)


def _calc_corr_ign(b):
    v = _s16(b, 0)
    if v is None:
        return None
    deg = round(v * 0.1, 1)
    if deg < -25.0 or deg > 25.0:
        return None
    return deg


PIDS_DB = [
    {
        "id": "RPM",
        "nome": "Rotacao Motor (RPM)",
        "unidade": "rpm",
        "cmd": "21A2",
        "rapido": True,
        "conf": "ok",
        "min": 0,
        "max": 7000,
        "calc": lambda b: _num(_u16(b, 0), 1, 0),
        "sim": lambda t: round(755 + 20 * math.sin(t * 2.0), 0),
    },
    {
        "id": "VEL",
        "nome": "Velocidade",
        "unidade": "km/h",
        "cmd": "21A6",
        "rapido": True,
        "conf": "ok",
        "min": 0,
        "max": 200,
        "calc": lambda b: _num(_u16(b, 2), 1, 0),
        "sim": lambda t: round(max(0.0, 55.0 + 15.0 * math.sin(t * 0.3)), 0),
    },
    {
        "id": "MAP",
        "nome": "Pressao Coletor (MAP)",
        "unidade": "kPa",
        "cmd": "21A2",
        "rapido": True,
        "conf": "ok",
        "min": 10,
        "max": 105,
        "calc": lambda b: _num(_u16(b, 2), 0.1, 1),
        "sim": lambda t: round(31.5 + 1.5 * math.sin(t * 2.0), 1),
    },
    {
        "id": "ECT",
        "nome": "Temperatura Agua",
        "unidade": "C",
        "cmd": "21A2",
        "rapido": True,
        "conf": "ok",
        "min": -10,
        "max": 125,
        "calc": lambda b: _calc_temp(b, 6),
        "sim": lambda t: round(86.0 + 1.5 * math.sin(t * 0.1), 0),
    },
    {
        "id": "TPS",
        "nome": "Posicao Borboleta (TPS)",
        "unidade": "%",
        "cmd": "21A2",
        "rapido": True,
        "conf": "ok",
        "min": 0,
        "max": 100,
        "calc": _calc_tps,
        "sim": lambda t: round(12.0 + 8.0 * abs(math.sin(t * 0.8)), 1),
    },
    {
        "id": "LAMBDA_1",
        "nome": "Sonda Lambda Pre-Cat",
        "unidade": "mV",
        "cmd": "2145",
        "rapido": True,
        "conf": "ok",
        "min": 0,
        "max": 1000,
        "calc": lambda b: _num(_u16(b, 0), 1, 0),
        "sim": lambda t: round(450 + 360 * math.sin(t * 3.5), 0),
    },
    {
        "id": "STFT",
        "nome": "Integrador Lambda (STFT)",
        "unidade": "%",
        "cmd": "2147",
        "rapido": True,
        "conf": "ok",
        "min": -35,
        "max": 35,
        "calc": _calc_trim_156,
        "sim": lambda t: round(3.8 * math.sin(t * 1.4), 1),
    },
    {
        "id": "TI_EFETIVO",
        "nome": "Tempo de Injecao",
        "unidade": "ms",
        "cmd": "21A0",
        "rapido": True,
        "conf": "ok",
        "min": 0,
        "max": 25,
        "calc": lambda b: _num(_u16(b, 16), 0.002, 2),
        "sim": lambda t: round(2.48 + 0.15 * math.sin(t * 2.2), 2),
    },
    {
        "id": "AVANCO",
        "nome": "Avanco de Ignicao",
        "unidade": "graus",
        "cmd": "21A0",
        "rapido": True,
        "conf": "provavel",
        "min": -15,
        "max": 55,
        "calc": _calc_avanco,
        "sim": lambda t: round(10.5 + 1.5 * math.sin(t * 1.8), 1),
    },
    {
        "id": "VBAT",
        "nome": "Tensao da Bateria",
        "unidade": "V",
        "cmd": "21A2",
        "rapido": True,
        "conf": "ok",
        "min": 9.0,
        "max": 16.0,
        "calc": lambda b: _num(_u16(b, 16), 0.1, 1),
        "sim": lambda t: 13.9,
    },
    {
        "id": "KNOCK_NOISE",
        "nome": "Ruido Base Knock (Janela)",
        "unidade": "V",
        "cmd": "2168",
        "rapido": False,
        "conf": "provavel",
        "min": 0.0,
        "max": 5.0,
        "calc": _calc_knock_noise_v,
        "sim": lambda t: round(1.15 + 0.10 * abs(math.sin(t * 2.5)), 2),
    },
    {
        "id": "KNOCK_CIL1",
        "nome": "Sinal Knock Cilindro 1",
        "unidade": "V",
        "cmd": "21A3",
        "rapido": False,
        "conf": "provavel",
        "min": 0.0,
        "max": 5.0,
        "calc": lambda b: _calc_knock_cilindro(b, 14),
        "sim": lambda t: round(0.25 + 0.05 * math.sin(t * 1.1), 2),
    },
    {
        "id": "KNOCK_CIL2",
        "nome": "Sinal Knock Cilindro 2",
        "unidade": "V",
        "cmd": "21A3",
        "rapido": False,
        "conf": "provavel",
        "min": 0.0,
        "max": 5.0,
        "calc": lambda b: _calc_knock_cilindro(b, 16),
        "sim": lambda t: round(0.26 + 0.05 * math.cos(t * 1.1), 2),
    },
    {
        "id": "KNOCK_CIL3",
        "nome": "Sinal Knock Cilindro 3",
        "unidade": "V",
        "cmd": "21A3",
        "rapido": False,
        "conf": "provavel",
        "min": 0.0,
        "max": 5.0,
        "calc": lambda b: _calc_knock_cilindro(b, 18),
        "sim": lambda t: round(0.24 + 0.05 * math.sin(t * 1.3), 2),
    },
    {
        "id": "KNOCK_CIL4",
        "nome": "Sinal Knock Cilindro 4",
        "unidade": "V",
        "cmd": "21A3",
        "rapido": False,
        "conf": "provavel",
        "min": 0.0,
        "max": 5.0,
        "calc": lambda b: _calc_knock_cilindro(b, 20),
        "sim": lambda t: round(0.25 + 0.05 * math.cos(t * 1.3), 2),
    },
    {
        "id": "CORR_IGN",
        "nome": "Ajuste/Atraso Ponto Ignicao",
        "unidade": "graus",
        "cmd": "216A",
        "rapido": False,
        "conf": "provavel",
        "min": -20,
        "max": 15,
        "calc": _calc_corr_ign,
        "sim": lambda t: -0.4,
    },
    {
        "id": "LTFT",
        "nome": "Adaptativo Mistura (LTFT)",
        "unidade": "%",
        "cmd": "2179",
        "rapido": False,
        "conf": "ok",
        "min": -35,
        "max": 35,
        "calc": _calc_trim_156,
        "sim": lambda t: 3.8,
    },
    {
        "id": "ETANOL_REAL",
        "nome": "Etanol Aprendido (Flex)",
        "unidade": "%",
        "cmd": "217B",
        "rapido": False,
        "conf": "provavel",
        "min": 0,
        "max": 100,
        "calc": _calc_etanol,
        "sim": lambda t: 27.0,
    },
    {
        "id": "CLOSED_LOOP",
        "nome": "Status da Malha (Loop)",
        "unidade": "Code",
        "cmd": "2157",
        "rapido": False,
        "conf": "ok",
        "min": 0,
        "max": 16,
        "calc": lambda b: float(_u8(b, 0)) if _u8(b, 0) is not None else None,
        "sim": lambda t: 4.0,
    },
    {
        "id": "IAT",
        "nome": "Temperatura Ar Admissao",
        "unidade": "C",
        "cmd": "21A2",
        "rapido": False,
        "conf": "ok",
        "min": -10,
        "max": 100,
        "calc": lambda b: _calc_temp(b, 4),
        "sim": lambda t: round(46.0 + 1.5 * math.sin(t * 0.15), 0),
    },
    {
        "id": "IAC",
        "nome": "Atuador Marcha Lenta (IAC)",
        "unidade": "passos",
        "cmd": "21A2",
        "rapido": False,
        "conf": "ok",
        "min": 0,
        "max": 200,
        "calc": lambda b: _num(_u16(b, 14), 1, 0),
        "sim": lambda t: 72.0,
    },
    {
        "id": "RPM_ALVO",
        "nome": "Rotacao Alvo Lenta",
        "unidade": "rpm",
        "cmd": "21A2",
        "rapido": False,
        "conf": "ok",
        "min": 0,
        "max": 2000,
        "calc": lambda b: _num(_u16(b, 12), 1, 0),
        "sim": lambda t: 750.0,
    },
    {
        "id": "BARO",
        "nome": "Pressao Barometrica",
        "unidade": "kPa",
        "cmd": "2160",
        "rapido": False,
        "conf": "ok",
        "min": 70,
        "max": 105,
        "calc": lambda b: _num(_u16(b, 0), 0.1, 1),
        "sim": lambda t: 96.7,
    },
    {
        "id": "CARGA",
        "nome": "Fluxo / Carga Calculada",
        "unidade": "idx",
        "cmd": "21A0",
        "rapido": False,
        "conf": "provavel",
        "min": 0,
        "max": 500,
        "calc": lambda b: _num(_u16(b, 18), 1, 0),
        "sim": lambda t: 85.0,
    },
    {
        "id": "TI_BASE",
        "nome": "Tempo Injecao Base",
        "unidade": "ms",
        "cmd": "216B",
        "rapido": False,
        "conf": "ok",
        "min": 0,
        "max": 25,
        "calc": lambda b: _num(_u16(b, 0), 0.01, 2),
        "sim": lambda t: 1.80,
    },
    {
        "id": "REGIME_MOTOR",
        "nome": "Regime (1=Par 2=Norm 4=Frio)",
        "unidade": "Code",
        "cmd": "21A1",
        "rapido": False,
        "conf": "ok",
        "min": 0,
        "max": 5,
        "calc": lambda b: float(_u8(b, 14) or 0),
        "sim": lambda t: 2.0,
    },
    {
        "id": "ESTADO_MOTOR",
        "nome": "Estado Motor (2=Par 4=Rod)",
        "unidade": "Code",
        "cmd": "21A6",
        "rapido": False,
        "conf": "ok",
        "min": 0,
        "max": 5,
        "calc": lambda b: float(_u8(b, 4) or 0),
        "sim": lambda t: 4.0,
    },
    {
        "id": "MOVIMENTO",
        "nome": "Veiculo em Movimento (0/1)",
        "unidade": "Ativo",
        "cmd": "2159",
        "rapido": False,
        "conf": "ok",
        "min": 0,
        "max": 1,
        "calc": lambda b: float(_u8(b, 0) or 0),
        "sim": lambda t: 1.0,
    },
    {
        "id": "MARCHA_IND",
        "nome": "Relacao Marcha Estimada",
        "unidade": "Code",
        "cmd": "2161",
        "rapido": False,
        "conf": "ok",
        "min": 0,
        "max": 10,
        "calc": lambda b: _num(_u16(b, 0), 1, 0),
        "sim": lambda t: 3.0,
    },
    {
        "id": "FAN_STATUS",
        "nome": "Eletroventilador (Status)",
        "unidade": "Code",
        "cmd": "21A6",
        "rapido": False,
        "conf": "provavel",
        "min": 0,
        "max": 10,
        "calc": lambda b: float(_u8(b, 8) or 0),
        "sim": lambda t: 1.0,
    },
]
