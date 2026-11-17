# coding: utf-8
# Mapa de leitura da ECU Magneti Marelli IAW 4AM (Pajero TR4 flex), KWP2000 modo 21.
#
# "b" e a lista de bytes DEPOIS do cabecalho "61 xx".
# Na convencao OBDLink/Torque: A = b[0], B = b[1].
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
    # Calibrado no pedal: 1 = 0% (solto), 436 = 52.1% (meio), 836 = 100% (batente)
    pct = ((v - 1.0) / 835.0) * 100.0
    return round(max(0.0, min(100.0, pct)), 1)


def _calc_trim_156(b):
    a = _u8(b, 0)
    if a is None:
        return None
    return round(((a - 156.0) / 156.0) * 100.0, 1)


def _calc_etanol(b):
    b1 = _u8(b, 1)
    if b1 is None:
        return None
    val = 27.0 + ((132.0 - b1) * 1.736)
    return round(max(0.0, min(100.0, val)), 1)


def _calc_afr(b):
    b1 = _u8(b, 1)
    if b1 is None:
        return None
    return round(b1 / 10.0, 1)


def _calc_temp(b, idx):
    v = _u16(b, idx)
    if v is None:
        return 0.0
    # Bloco 21A2 entrega ECT e IAT em graus Fahrenheit inteiros
    return round((v - 32.0) / 1.8, 1)


def _calc_avanco(b):
    v = _s16(b, 18)
    if v is None:
        return None
    deg = round(v * 0.1, 1)
    if deg < -15.0 or deg > 55.0:
        return None
    return deg


def _calc_knock_sensor_v(b):
    # Sinal do sensor piezo de detonacao (0..5.00 V)
    # < 1.50 V = ruido mecanico normal | 1.50-2.50 V = atencao | > 2.50 V = knock
    if len(b) >= 2:
        raw16 = _u16(b, 0)
        if raw16 is not None and raw16 <= 1023:
            return round((raw16 / 1023.0) * 5.0, 2)
    a = _u8(b, 0)
    if a is None:
        return None
    return round((a / 255.0) * 5.0, 2)


def _calc_knock_mv(b):
    # Sinal bruto de knock em mV (PID 2152: <1500 mV normal | >2500 mV knock)
    v = _u16(b, 0)
    if v is not None and v <= 5000:
        return round(float(v), 0)
    a = _u8(b, 0)
    if a is None:
        return None
    return round((a / 255.0) * 5000.0, 0)


def _calc_corr_ign(b):
    # Atraso/retirada de avanco global aplicada pela ECU ao detectar detonacao (graus)
    v = _s16(b, 0)
    if v is None:
        return None
    deg = round(v * 0.1, 1)
    if deg < -25.0 or deg > 25.0:
        return None
    return deg


def _calc_knock_cil(b, offset):
    # Atraso individual por cilindro no bloco consolidado 21A0 (bytes 8..15, fator 0.1 graus)
    v = _s16(b, offset)
    if v is None:
        return None
    deg = round(v * 0.1, 1)
    if deg < -25.0 or deg > 25.0:
        return None
    return deg


def _calc_knock_max_cil(b):
    vals = [d for off in (8, 10, 12, 14) if (d := _calc_knock_cil(b, off)) is not None]
    if not vals:
        return None
    pior = min(vals)
    return pior if pior < 0.0 else 0.0


def _calc_mapa_comb(b):
    a = _u8(b, 0)
    if a is None:
        return None
    return round(float(a), 0)


PIDS_DB = [
    # --- Principais (rapido=True: marcados por padrao no Painel e Log) ------------------------------------------
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
        "sim": lambda t: round(820 + 25 * math.sin(t * 2.0), 0),
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
        "sim": lambda t: round(32.5 + 1.5 * math.sin(t * 2.0), 1),
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
        "sim": lambda t: round(86.0 + 1.5 * math.sin(t * 0.1), 1),
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
        "sim": lambda t: round(2.75 + 0.15 * math.sin(t * 2.2), 2),
    },
    {
        "id": "AVANCO",
        "nome": "Avanco de Ignicao",
        "unidade": "graus",
        "cmd": "21A0",
        "rapido": True,
        "conf": "ok",
        "min": -15,
        "max": 55,
        "calc": _calc_avanco,
        "sim": lambda t: round(11.5 + 1.5 * math.sin(t * 1.8), 1),
    },

    # --- Complementares (selecionaveis em PIDS / GRAFICO / LOG CSV) ----------------------------------------------
    {
        "id": "KNOCK_SENSOR",
        "nome": "Sensor Knock (<1.5V OK | >2.5V Knock)",
        "unidade": "V",
        "cmd": "2168",
        "rapido": False,
        "conf": "ok",
        "min": 0.0,
        "max": 5.0,
        "calc": _calc_knock_sensor_v,
        "sim": lambda t: round(2.85 if math.sin(t * 0.9) > 0.92 else 0.65 + 0.15 * abs(math.sin(t * 2.5)), 2),
    },
    {
        "id": "KNOCK_MV",
        "nome": "Sinal Bruto Knock (mV)",
        "unidade": "mV",
        "cmd": "2152",
        "rapido": False,
        "conf": "provavel",
        "min": 0,
        "max": 5000,
        "calc": _calc_knock_mv,
        "sim": lambda t: round(2850.0 if math.sin(t * 0.9) > 0.92 else 650.0, 0),
    },
    {
        "id": "CORR_IGN",
        "nome": "Atraso Ponto Global Knock",
        "unidade": "graus",
        "cmd": "216A",
        "rapido": False,
        "conf": "ok",
        "min": -20,
        "max": 15,
        "calc": _calc_corr_ign,
        "sim": lambda t: -2.0 if math.sin(t * 0.9) > 0.92 else 0.0,
    },
    {
        "id": "KNOCK_MAX_CIL",
        "nome": "Pior Atraso Knock (4 Cilindros)",
        "unidade": "graus",
        "cmd": "21A0",
        "rapido": False,
        "conf": "ok",
        "min": -20,
        "max": 5,
        "calc": _calc_knock_max_cil,
        "sim": lambda t: -1.5 if math.sin(t * 0.9) > 0.92 else 0.0,
    },
    {
        "id": "KNOCK_CIL1",
        "nome": "Atraso Knock Cilindro 1",
        "unidade": "graus",
        "cmd": "21A0",
        "rapido": False,
        "conf": "ok",
        "min": -20,
        "max": 5,
        "calc": lambda b: _calc_knock_cil(b, 8),
        "sim": lambda t: 0.0,
    },
    {
        "id": "KNOCK_CIL2",
        "nome": "Atraso Knock Cilindro 2",
        "unidade": "graus",
        "cmd": "21A0",
        "rapido": False,
        "conf": "ok",
        "min": -20,
        "max": 5,
        "calc": lambda b: _calc_knock_cil(b, 10),
        "sim": lambda t: -1.5 if math.sin(t * 0.9) > 0.92 else 0.0,
    },
    {
        "id": "KNOCK_CIL3",
        "nome": "Atraso Knock Cilindro 3",
        "unidade": "graus",
        "cmd": "21A0",
        "rapido": False,
        "conf": "ok",
        "min": -20,
        "max": 5,
        "calc": lambda b: _calc_knock_cil(b, 12),
        "sim": lambda t: 0.0,
    },
    {
        "id": "KNOCK_CIL4",
        "nome": "Atraso Knock Cilindro 4",
        "unidade": "graus",
        "cmd": "21A0",
        "rapido": False,
        "conf": "ok",
        "min": -20,
        "max": 5,
        "calc": lambda b: _calc_knock_cil(b, 14),
        "sim": lambda t: 0.0,
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
        "cmd": "2178",
        "rapido": False,
        "conf": "ok",
        "min": 0,
        "max": 100,
        "calc": _calc_etanol,
        "sim": lambda t: 27.0,
    },
    {
        "id": "MAPA_COMB",
        "nome": "Mapa Aprendizado Combustivel",
        "unidade": "raw",
        "cmd": "217B",
        "rapido": False,
        "conf": "ok",
        "min": 0,
        "max": 255,
        "calc": _calc_mapa_comb,
        "sim": lambda t: 128.0,
    },
    {
        "id": "AFR_LAMBDA",
        "nome": "Relacao Ar/Combustivel (AFR)",
        "unidade": ":1",
        "cmd": "2178",
        "rapido": False,
        "conf": "ok",
        "min": 8,
        "max": 16,
        "calc": _calc_afr,
        "sim": lambda t: 13.2,
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
        "sim": lambda t: 2.0,
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
        "sim": lambda t: round(36.0 + 1.5 * math.sin(t * 0.15), 1),
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
        "sim": lambda t: 74.0,
    },
    {
        "id": "RPM_ALVO",
        "nome": "Rotacao Alvo Lenta",
        "unidade": "rpm",
        "cmd": "213A",
        "rapido": False,
        "conf": "ok",
        "min": 0,
        "max": 2000,
        "calc": lambda b: _num(_u16(b, 0), 1, 0),
        "sim": lambda t: 780.0,
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
        "sim": lambda t: 99.5,
    },
    {
        "id": "CARGA",
        "nome": "Carga Motor (MAP / 100 kPa)",
        "unidade": "%",
        "cmd": "21A2",
        "rapido": False,
        "conf": "ok",
        "min": 0,
        "max": 100,
        "calc": lambda b: _num(min(100.0, (_u16(b, 2) or 0) * 0.1), 1, 0),
        "sim": lambda t: 32.0,
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
        "sim": lambda t: 1.94,
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
        "nome": "(?) Eletroventilador",
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