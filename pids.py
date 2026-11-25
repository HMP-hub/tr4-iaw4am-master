# coding: utf-8
import math
from operator import itemgetter


def _u16(b, idx=0):
    if len(b) < idx + 2:
        return None
    b0, b1 = itemgetter(idx, idx + 1)(b)
    return (b0 << 8) | b1


def _s16(b, idx=0):
    v = _u16(b, idx)
    if v is None:
        return None
    return v - 65536 if v >= 32768 else v


def _u8(b, idx=0):
    if len(b) < idx + 1:
        return None
    return itemgetter(idx)(b)


def _calc_tps_a2(b):
    v = _u16(b, 8)
    if v is None:
        return None
    pct = ((v - 1.0) / 835.0) * 100.0
    if pct < 0.35:
        return 0.0
    return round(min(100.0, pct), 1)


def _calc_knock_ret_cil(b, idx):
    v = _s16(b, idx)
    if v is None or v < 0 or v > 80:
        return 0.0
    return round(-v * 0.25, 2)


def _calc_knock_compilado(b):
    if len(b) < 14:
        return None
    vals = [_calc_knock_ret_cil(b, idx) for idx in (6, 8, 10, 12)]
    return min(vals)


def _calc_knock_v_2169(b, idx):
    v = _u8(b, idx)
    if v is None:
        return None
    return round((v / 255.0) * 5.0, 2)


def _calc_stft_21a4(b):
    a = _u8(b, 8)
    if a is None or a == 0:
        return None
    return round(((156.0 - a) / 156.0) * 100.0, 1)


def _calc_ltft_2154(b):
    v = _u16(b, 0)
    if v is None or v == 0:
        return None
    val = round(((1638.0 - v) / 1638.0) * 100.0, 1)
    if val < -35.0 or val > 35.0:
        return None
    return val


def _calc_etanol_pct_217b(b):
    v = _u16(b, 0)
    if v is None:
        return None
    pct = max(0.0, min(100.0, round((v / 488.9) * 100.0, 0)))
    return int(pct)


def _calc_af_217b(b):
    pct = _calc_etanol_pct_217b(b)
    if pct is None:
        return None
    af = 14.7 - (pct / 100.0) * (14.7 - 9.0)
    return round(af, 1)


def _calc_tipo_comb_217b(b):
    pct = _calc_etanol_pct_217b(b)
    if pct is None:
        return None
    if pct <= 3:
        return f"E{pct:02d} (GAS)"
    if pct >= 95:
        return f"E{pct} (ALC)"
    return f"E{pct:02d} (FLEX)"

PIDS_DB = [
    {
        "id": "STFT",
        "nome": "Ajuste Curto (STFT)",
        "cmd": "21A4",
        "unidade": "%",
        "rapido": True,
        "calc": _calc_stft_21a4,
        "sim": lambda t: round(-4.5 + 3.0 * math.sin(t * 1.1), 1),
    },
    {
        "id": "LTFT",
        "nome": "Ajuste Longo (LTFT)",
        "cmd": "2154",
        "unidade": "%",
        "rapido": True,
        "calc": _calc_ltft_2154,
        "sim": lambda t: -0.7,
    },
    {
        "id": "LAMBDA_1",
        "nome": "Sonda Pre-Cat",
        "cmd": "2145",
        "unidade": "mV",
        "rapido": True,
        "calc": lambda b: _u16(b, 0),
        "sim": lambda t: int(450 + 380 * math.sin(t * 3.2)),
    },
    {
        "id": "TI_EFETIVO",
        "nome": "Tempo Injecao",
        "cmd": "21A0",
        "unidade": "ms",
        "rapido": True,
        "calc": lambda b: round(_u16(b, 16) * 0.002, 2) if _u16(b, 16) is not None else None,
        "sim": lambda t: round(2.52 + 0.35 * math.sin(t * 0.9), 2),
    },
    {
        "id": "RPM",
        "nome": "Rotacao (RPM)",
        "cmd": "21A2",
        "unidade": "rpm",
        "rapido": True,
        "calc": lambda b: _u16(b, 0),
        "sim": lambda t: int(760 + 25 * math.sin(t * 1.7)),
    },
    {
        "id": "AVANCO",
        "nome": "Avanco Ignicao",
        "cmd": "21A0",
        "unidade": "deg",
        "rapido": True,
        "calc": lambda b: round(_s16(b, 14) * 0.125, 1) if _s16(b, 14) is not None else None,
        "sim": lambda t: round(-5.5 + 2.5 * math.sin(t * 1.2), 1),
    },
    {
        "id": "MAP",
        "nome": "Pressao Coletor",
        "cmd": "21A2",
        "unidade": "kPa",
        "rapido": True,
        "calc": lambda b: round(_u16(b, 2) / 10.0, 1) if _u16(b, 2) is not None else None,
        "sim": lambda t: round(31.5 + 1.5 * math.cos(t * 1.3), 1),
    },
    {
        "id": "VBAT",
        "nome": "Tensao Bateria",
        "cmd": "21A2",
        "unidade": "V",
        "rapido": True,
        "calc": lambda b: round(_u16(b, 16) * 0.1, 1) if _u16(b, 16) is not None else None,
        "sim": lambda t: round(14.1 + 0.1 * math.sin(t * 0.5), 1),
    },
    {
        "id": "TPS",
        "nome": "Posicao Borboleta",
        "cmd": "21A2",
        "unidade": "%",
        "rapido": True,
        "calc": _calc_tps_a2,
        "sim": lambda t: 0.0,
    },
    {
        "id": "KNOCK_MAX",
        "nome": "Atraso Detonacao",
        "cmd": "21A3",
        "unidade": "deg",
        "rapido": True,
        "calc": _calc_knock_compilado,
        "sim": lambda t: 0.0,
    },
    {
        "id": "KNOCK_NOISE",
        "nome": "Sinal Sensor Knock",
        "cmd": "2168",
        "unidade": "V",
        "rapido": False,
        "calc": lambda b: round((_u16(b, 0) / 1023.0) * 5.0, 2) if _u16(b, 0) is not None else None,
        "sim": lambda t: round(0.57 + 0.08 * abs(math.sin(t * 2.1)), 2),
    },
    {
        "id": "VEL",
        "nome": "Velocidade",
        "cmd": "21A6",
        "unidade": "km/h",
        "rapido": True,
        "calc": lambda b: _u16(b, 2),
        "sim": lambda t: 0,
    },

    {
        "id": "ECT",
        "nome": "Temp. Agua",
        "cmd": "21A2",
        "unidade": "C",
        "rapido": False,
        "calc": lambda b: round(float(_u16(b, 6) - 40), 1) if _u16(b, 6) is not None else None,
        "sim": lambda t: round(min(92.0, 84.0 + t * 0.04), 1),
    },
    {
        "id": "KNOCK_CIL1",
        "nome": "Retardo Cilindro 1",
        "cmd": "21A3",
        "unidade": "deg",
        "rapido": False,
        "calc": lambda b: _calc_knock_ret_cil(b, 6),
        "sim": lambda t: 0.0,
    },
    {
        "id": "KNOCK_CIL2",
        "nome": "Retardo Cilindro 2",
        "cmd": "21A3",
        "unidade": "deg",
        "rapido": False,
        "calc": lambda b: _calc_knock_ret_cil(b, 8),
        "sim": lambda t: 0.0,
    },
    {
        "id": "KNOCK_CIL3",
        "nome": "Retardo Cilindro 3",
        "cmd": "21A3",
        "unidade": "deg",
        "rapido": False,
        "calc": lambda b: _calc_knock_ret_cil(b, 10),
        "sim": lambda t: 0.0,
    },
    {
        "id": "KNOCK_CIL4",
        "nome": "Retardo Cilindro 4",
        "cmd": "21A3",
        "unidade": "deg",
        "rapido": False,
        "calc": lambda b: _calc_knock_ret_cil(b, 12),
        "sim": lambda t: 0.0,
    },
    {
        "id": "KNOCK_V_CIL1",
        "nome": "Ruido Knock Cil 1",
        "cmd": "2169",
        "unidade": "V",
        "rapido": False,
        "calc": lambda b: _calc_knock_v_2169(b, 0),
        "sim": lambda t: round(0.11 + 0.03 * abs(math.sin(t * 2.0)), 2),
    },
    {
        "id": "KNOCK_V_CIL2",
        "nome": "Ruido Knock Cil 2",
        "cmd": "2169",
        "unidade": "V",
        "rapido": False,
        "calc": lambda b: _calc_knock_v_2169(b, 1),
        "sim": lambda t: round(0.11 + 0.03 * abs(math.cos(t * 2.1)), 2),
    },
    {
        "id": "KNOCK_V_CIL3",
        "nome": "Ruido Knock Cil 3",
        "cmd": "2169",
        "unidade": "V",
        "rapido": False,
        "calc": lambda b: _calc_knock_v_2169(b, 2),
        "sim": lambda t: round(0.11 + 0.03 * abs(math.sin(t * 1.9)), 2),
    },
    {
        "id": "KNOCK_V_CIL4",
        "nome": "Ruido Knock Cil 4",
        "cmd": "2169",
        "unidade": "V",
        "rapido": False,
        "calc": lambda b: _calc_knock_v_2169(b, 3),
        "sim": lambda t: round(0.11 + 0.03 * abs(math.cos(t * 2.2)), 2),
    },
    {
        "id": "CORR_IGN",
        "nome": "Correcao Ignicao",
        "cmd": "2165",
        "unidade": "deg",
        "rapido": False,
        "calc": lambda b: round((_u16(b, 0) - 256.0) * 0.5, 1) if _u16(b, 0) is not None else None,
        "sim": lambda t: -1.0,
    },
    {
        "id": "MAPA_AF",
        "nome": "Mapa Combustivel",
        "cmd": "217B",
        "unidade": ":1 A/F",
        "rapido": False,
        "calc": _calc_af_217b,
        "sim": lambda t: 13.2,
    },
    {
        "id": "TIPO_COMB",
        "nome": "Combustivel SFS",
        "cmd": "217B",
        "unidade": "",
        "rapido": False,
        "calc": _calc_tipo_comb_217b,
        "sim": lambda t: "E27 (FLEX)",
    },

    {
        "id": "CLOSED_LOOP",
        "nome": "Status Malha",
        "cmd": "2161",
        "unidade": "st",
        "rapido": False,
        "calc": lambda b: round(_u16(b, 0) / 100.0, 1) if _u16(b, 0) is not None else None,
        "sim": lambda t: 4.0,
    },
    {
        "id": "IAT",
        "nome": "Temp. Ar Admissao",
        "cmd": "21A2",
        "unidade": "C",
        "rapido": False,
        "calc": lambda b: round(float(_u16(b, 4) - 40), 1) if _u16(b, 4) is not None else None,
        "sim": lambda t: 44.0,
    },
    {
        "id": "IAC",
        "nome": "Atuador Lenta (IAC)",
        "cmd": "213A",
        "unidade": "passos",
        "rapido": False,
        "calc": _u16,
        "sim": lambda t: 69,
    },
    {
        "id": "RPM_ALVO",
        "nome": "RPM Alvo Lenta",
        "cmd": "213B",
        "unidade": "rpm",
        "rapido": False,
        "calc": _u16,
        "sim": lambda t: 750,
    },
    {
        "id": "BARO",
        "nome": "Pressao Barometrica",
        "cmd": "2147",
        "unidade": "kPa",
        "rapido": False,
        "calc": lambda b: round(_u16(b, 10) / 10.0, 1) if _u16(b, 10) is not None else None,
        "sim": lambda t: 97.9,
    },
    {
        "id": "CARGA",
        "nome": "Carga Motor",
        "cmd": "2164",
        "unidade": "raw",
        "rapido": False,
        "calc": _u16,
        "sim": lambda t: int(90 + 15 * abs(math.sin(t))),
    },
    {
        "id": "TI_BASE",
        "nome": "Tempo Injecao Base",
        "cmd": "216A",
        "unidade": "ms",
        "rapido": False,
        "calc": lambda b: round(_u16(b, 0) * 0.004, 2) if _u16(b, 0) is not None else None,
        "sim": lambda t: 1.80,
    },
    {
        "id": "REGIME_MOTOR",
        "nome": "Regime Operacao",
        "cmd": "2160",
        "unidade": "st",
        "rapido": False,
        "calc": lambda b: round(_u16(b, 0) / 100.0, 1) if _u16(b, 0) is not None else None,
        "sim": lambda t: 2.0,
    },
    {
        "id": "ESTADO_MOTOR",
        "nome": "Estado Funcionamento",
        "cmd": "21A0",
        "unidade": "st",
        "rapido": False,
        "calc": lambda b: round(_u16(b, 0) / 100.0, 1) if _u16(b, 0) is not None else None,
        "sim": lambda t: 4.0,
    },
    {
        "id": "MOVIMENTO",
        "nome": "Status Movimento",
        "cmd": "21A1",
        "unidade": "st",
        "rapido": False,
        "calc": lambda b: round(_u16(b, 0) / 100.0, 1) if _u16(b, 0) is not None else None,
        "sim": lambda t: 0.0,
    },
    {
        "id": "MARCHA_IND",
        "nome": "Marcha Engatada",
        "cmd": "21A7",
        "unidade": "marcha",
        "rapido": False,
        "calc": _u16,
        "sim": lambda t: 0,
    },
    {
        "id": "FAN_STATUS",
        "nome": "Ventoinha Radiador",
        "cmd": "21A3",
        "unidade": "st",
        "rapido": False,
        "calc": lambda b: round(_u16(b, 0) / 100.0, 1) if _u16(b, 0) is not None else None,
        "sim": lambda t: 0.0,
    },
]

