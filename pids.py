# coding: utf-8
# Mapa calibrado da ECU Magneti Marelli IAW 4AM (Pajero TR4 2.0 16V Flex) - KWP2000 Modo 21.
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


def _calc_stft(b):
    # 2147: 0x9C40 (40000) e o ponto neutro exato (0.0% em repouso e cut-off)
    v = _u16(b, 0)
    if v is None:
        return 0.0
    return round(((v - 40000.0) / 40000.0) * 100.0, 1)


def _calc_ltft(b):
    # 2179: centro em 156 (0x9C)
    a = _u8(b, 0)
    if a is None:
        return 0.0
    return round(((a - 156.0) / 156.0) * 100.0, 1)


def _calc_etanol(b):
    # 217B -> 00 84 (byte B = 132 = E27)
    val_b = _u8(b, 1)
    if val_b is None:
        return None
    etanol = 27.0 + ((132.0 - float(val_b)) * 1.736)
    return round(max(0.0, min(100.0, etanol)), 1)


def _calc_afr(b):
    # 217B -> 00 84 (byte B = 132 -> 13.2 AFR)
    val_b = _u8(b, 1)
    if val_b is None:
        return None
    return round(float(val_b) / 10.0, 1)


def _calc_temp(b, idx):
    v = _u16(b, idx)
    if v is None:
        return 0.0
    return round(float(v - 40), 0)


def _fmt_marcha(v):
    m = int(round(float(v)))
    if m <= 0:
        return "Neutro"
    return f"{m}ª Marcha"


PIDS_DB = [
    # --- Principais (rapido=True: marcados por padrao no Painel e Log) ---
    {
        "id": "RPM",
        "nome": "Rotacao Motor (RPM)",
        "unidade": "rpm",
        "cmd": "21A2",
        "rapido": True,
        "min": 0,
        "max": 7000,
        "calc": lambda b: _num(_u16(b, 0), 1, 0),
        "sim": lambda t: round(800 + 25 * math.sin(t * 2.0), 0),
    },
    {
        "id": "VEL",
        "nome": "Velocidade",
        "unidade": "km/h",
        "cmd": "21A6",
        "rapido": True,
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
        "min": -10,
        "max": 125,
        "calc": lambda b: _calc_temp(b, 6),
        "sim": lambda t: round(86.0 + 1.5 * math.sin(t * 0.1), 0),
    },
    {
        "id": "TPS",
        "nome": "Posicao Borboleta",
        "unidade": "%",
        "cmd": "21A2",
        "rapido": True,
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
        "min": -35,
        "max": 35,
        "calc": _calc_stft,
        "sim": lambda t: round(4.5 * math.sin(t * 1.4), 1),
    },
    {
        "id": "TI_EFETIVO",
        "nome": "Tempo de Injecao",
        "unidade": "ms",
        "cmd": "21A0",
        "rapido": True,
        "min": 0,
        "max": 25,
        "calc": lambda b: _num(_u16(b, 16), 0.002, 2),
        "sim": lambda t: round(2.55 + 0.15 * math.sin(t * 2.2), 2),
    },
    {
        "id": "AVANCO",
        "nome": "Avanco de Ignicao",
        "unidade": "graus",
        "cmd": "21A0",
        "rapido": True,
        "min": -15,
        "max": 55,
        "calc": lambda b: _num(_s16(b, 18), 0.1, 1),
        "sim": lambda t: round(10.5 + 1.5 * math.sin(t * 1.8), 1),
    },
    {
        "id": "KNOCK_SENSOR",
        "nome": "Sensor Knock (<1.5V OK | >2.5V Knock)",
        "unidade": "V",
        "cmd": "21A4",
        "rapido": True,
        "min": 0.0,
        "max": 5.0,
        "calc": lambda b: _num(_u16(b, 8), 0.0000488, 2),
        "sim": lambda t: round(1.15 + 0.25 * abs(math.sin(t * 1.7)), 2),
    },
    {
        "id": "CORR_IGN",
        "nome": "Atraso Ponto por Knock",
        "unidade": "graus",
        "cmd": "216A",
        "rapido": True,
        "min": -15,
        "max": 15,
        "calc": lambda b: _num(_s16(b, 0), 0.1, 1),
        "sim": lambda t: 0.0,
    },
    {
        "id": "LTFT",
        "nome": "Adaptativo Mistura (LTFT)",
        "unidade": "%",
        "cmd": "2179",
        "rapido": True,
        "min": -30,
        "max": 30,
        "calc": _calc_ltft,
        "sim": lambda t: 3.8,
    },

    # --- Complementares confirmados (selecionaveis em PIDS / LOG CSV) ---
    {
        "id": "BATERIA",
        "nome": "Tensao Bateria",
        "unidade": "V",
        "cmd": "21A2",
        "rapido": False,
        "min": 9.0,
        "max": 16.0,
        "calc": lambda b: _num(_u16(b, 16), 0.1, 1),
        "sim": lambda t: 14.1,
    },
    {
        "id": "ETANOL_REAL",
        "nome": "Etanol Aprendido (Flex)",
        "unidade": "%",
        "cmd": "217B",
        "rapido": False,
        "min": 0,
        "max": 100,
        "calc": _calc_etanol,
        "sim": lambda t: 27.0,
    },
    {
        "id": "AFR_LAMBDA",
        "nome": "Relacao Ar/Combustivel (AFR)",
        "unidade": "AFR",
        "cmd": "217B",
        "rapido": False,
        "min": 7.0,
        "max": 18.0,
        "calc": _calc_afr,
        "sim": lambda t: 13.2,
    },
    {
        "id": "MARCHA_IND",
        "nome": "Marcha Sugerida",
        "unidade": "",
        "cmd": "2161",
        "rapido": False,
        "min": 0,
        "max": 5,
        "calc": lambda b: _num(_u16(b, 0), 1, 0),
        "fmt": _fmt_marcha,
        "sim": lambda t: 4.0,
    },
    {
        "id": "IAT",
        "nome": "Temperatura Ar Admissao",
        "unidade": "C",
        "cmd": "21A2",
        "rapido": False,
        "min": -10,
        "max": 100,
        "calc": lambda b: _calc_temp(b, 4),
        "sim": lambda t: round(44.0 + 1.5 * math.sin(t * 0.15), 0),
    },
    {
        "id": "IAC",
        "nome": "Atuador Marcha Lenta (IAC)",
        "unidade": "passos",
        "cmd": "21A2",
        "rapido": False,
        "min": 0,
        "max": 200,
        "calc": lambda b: _num(_u16(b, 14), 1, 0),
        "sim": lambda t: 72.0,
    },
    {
        "id": "RPM_ALVO",
        "nome": "Rotacao Alvo Lenta",
        "unidade": "rpm",
        "cmd": "213A",
        "rapido": False,
        "min": 0,
        "max": 2000,
        "calc": lambda b: _num(_u16(b, 0), 1, 0),
        "sim": lambda t: 750.0,
    },
    {
        "id": "BARO",
        "nome": "Pressao Barometrica",
        "unidade": "kPa",
        "cmd": "2160",
        "rapido": False,
        "min": 70,
        "max": 105,
        "calc": lambda b: _num(_u16(b, 0), 0.1, 1),
        "sim": lambda t: 97.5,
    },
    {
        "id": "CARGA",
        "nome": "Carga Motor (MAP / 100 kPa)",
        "unidade": "%",
        "cmd": "21A2",
        "rapido": False,
        "min": 0,
        "max": 100,
        "calc": lambda b: _num(min(100.0, (_u16(b, 2) or 0) * 0.1), 1, 0),
        "sim": lambda t: 31.0,
    },
    {
        "id": "TI_BASE",
        "nome": "Tempo Injecao Base",
        "unidade": "ms",
        "cmd": "216B",
        "rapido": False,
        "min": 0,
        "max": 25,
        "calc": lambda b: _num(_u16(b, 0), 0.01, 2),
        "sim": lambda t: 1.80,
    },
    {
        "id": "CLOSED_LOOP",
        "nome": "Malha Fechada (2=Ativa 4=Fria)",
        "unidade": "Code",
        "cmd": "21A4",
        "rapido": False,
        "min": 0,
        "max": 5,
        "calc": lambda b: float(_u8(b, 6) or 0),
        "sim": lambda t: 2.0,
    },
    {
        "id": "REGIME_MOTOR",
        "nome": "Regime (1=Par 2=Norm 4=Frio)",
        "unidade": "Code",
        "cmd": "21A1",
        "rapido": False,
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
        "min": 0,
        "max": 1,
        "calc": lambda b: float(_u8(b, 0) or 0),
        "sim": lambda t: 1.0,
    },
    {
        "id": "FAN_STATUS",
        "nome": "Eletroventilador (1=Desl 8=Lig)",
        "unidade": "Code",
        "cmd": "21A6",
        "rapido": False,
        "min": 0,
        "max": 10,
        "calc": lambda b: float(_u8(b, 8) or 0),
        "sim": lambda t: 1.0,
    },
]