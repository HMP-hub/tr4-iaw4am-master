# coding: utf-8
# Mapa calibrado da ECU Magneti Marelli IAW 4AM (Pajero TR4 2.0 Flex)
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


def _f_para_c(b, idx):
    v = _u16(b, idx)
    if v is None:
        return 0.0
    return round((v - 32.0) * 5.0 / 9.0, 1)


def _mapa_comb_str(b):
    raw = _u8(b, 0)
    if raw is None:
        return "--"
    alc = max(0, min(100, raw - 128))
    if alc >= 75:
        return f"Etanol ({alc}%)"
    if alc >= 36:
        return f"Mix Flex ({alc}%)"
    return f"Gasolina ({alc}%)"


PIDS_DB = [
    # --- PAINEL PRINCIPAL (ATIVOS POR PADRAO) ---
    {
        "id": "RPM",
        "nome": "Rotacao Motor (RPM)",
        "unidade": "rpm",
        "cmd": "21A2",
        "rapido": True,
        "min": 0,
        "max": 7000,
        "calc": lambda b: _num(_u16(b, 0), 1.0, 0),
        "sim": lambda t: round(860 + 25 * math.sin(t * 2.0), 0),
    },
    {
        "id": "MAP",
        "nome": "Pressao Coletor (MAP)",
        "unidade": "kPa",
        "cmd": "21A2",
        "rapido": True,
        "min": 10,
        "max": 110,
        "calc": lambda b: _num(_u16(b, 2), 0.1, 1),
        "sim": lambda t: round(33.5 + 1.5 * math.sin(t * 2.0), 1),
    },
    {
        "id": "ECT",
        "nome": "Temperatura Agua (ECT)",
        "unidade": "C",
        "cmd": "21A2",
        "rapido": True,
        "min": 0,
        "max": 125,
        "calc": lambda b: _f_para_c(b, 4),
        "sim": lambda t: round(89.0 + 1.5 * math.sin(t * 0.1), 1),
    },
    {
        "id": "IAT",
        "nome": "Temperatura Ar Coletor (IAT)",
        "unidade": "C",
        "cmd": "21A2",
        "rapido": True,
        "min": 0,
        "max": 100,
        "calc": lambda b: _f_para_c(b, 6),
        "sim": lambda t: round(42.0 + 2.0 * math.sin(t * 0.15), 1),
    },
    {
        "id": "TPS",
        "nome": "Posicao Borboleta (TPS)",
        "unidade": "%",
        "cmd": "213D",
        "rapido": True,
        "min": 0,
        "max": 100,
        "calc": lambda b: _num(_u16(b, 0), 0.1, 1),
        "sim": lambda t: round(max(0.0, 12.0 * math.sin(t * 1.1)), 1),
    },
    {
        "id": "IAC_PASSOS",
        "nome": "Motor Passo Marcha Lenta (ISC)",
        "unidade": "passos",
        "cmd": "21A2",
        "rapido": True,
        "min": 0,
        "max": 250,
        "calc": lambda b: _num(_u16(b, 14), 1.0, 0),
        "sim": lambda t: 68.0,
    },
    {
        "id": "TI_EFETIVO",
        "nome": "Tempo Injecao Consolidado",
        "unidade": "ms",
        "cmd": "21A1",
        "rapido": True,
        "min": 0,
        "max": 25,
        "calc": lambda b: _num(_u16(b, 12), 0.002, 2),
        "sim": lambda t: round(3.10 + 0.15 * math.sin(t * 2.2), 2),
    },
    {
        "id": "AVANCO",
        "nome": "Avanco Ignicao Final",
        "unidade": "deg",
        "cmd": "2138",
        "rapido": True,
        "min": -10,
        "max": 50,
        "calc": lambda b: _num(_s16(b, 0), 0.1, 1),
        "sim": lambda t: round(14.3 + 1.5 * math.sin(t * 1.8), 1),
    },
    {
        "id": "BATERIA",
        "nome": "Tensao Bateria",
        "unidade": "V",
        "cmd": "21A2",
        "rapido": True,
        "min": 10,
        "max": 16,
        "calc": lambda b: _num(_u16(b, 16), 0.1, 1),
        "sim": lambda t: round(14.2 + 0.1 * math.sin(t * 0.5), 1),
    },
    {
        "id": "LAMBDA_1",
        "nome": "Sonda Lambda Pre-Cat",
        "unidade": "mV",
        "cmd": "21A3",
        "rapido": True,
        "min": 0,
        "max": 1000,
        "calc": lambda b: _num(_u16(b, 14), 1.0, 0),
        "sim": lambda t: round(450 + 360 * math.sin(t * 3.5), 0),
    },
    {
        "id": "STFT",
        "nome": "Integrador Lambda (STFT)",
        "unidade": "%",
        "cmd": "2167",
        "rapido": True,
        "min": -35,
        "max": 35,
        "calc": lambda b: round(((_u16(b, 0) or 1024) - 1024) / 10.24, 1),
        "sim": lambda t: round(1.8 * math.sin(t * 1.4), 1),
    },
    {
        "id": "ETANOL_REAL",
        "nome": "Etanol Aprendido SFS (ECU)",
        "unidade": "%",
        "cmd": "21A7",
        "rapido": True,
        "min": 0,
        "max": 100,
        "calc": lambda b: float(max(0, min(100, (_u8(b, 3) or 128) - 128))),
        "sim": lambda t: 34.0,
    },

    # --- DIAGNOSTICO AVANCADO / DETONACAO / MAPA COMBUSTIVEL ---
    {
        "id": "MAPA_COMB",
        "nome": "Identificacao Mapa Combustivel",
        "unidade": "",
        "cmd": "2179",
        "rapido": False,
        "min": 0,
        "max": 100,
        "calc": _mapa_comb_str,
        "sim": lambda t: "Gasolina (34%)",
    },
    {
        "id": "KNOCK_SENSOR",
        "nome": "Sinal Sensor Detonacao (Knock)",
        "unidade": "mV",
        "cmd": "2152",
        "rapido": False,
        "min": 0,
        "max": 5000,"calc": lambda b: _num(_u16(b, 0), 1.0, 0),
        "sim": lambda t: 120.0,
    },
    {
        "id": "CORR_IGN",
        "nome": "Correcao Avanco Ignicao / Knock",
        "unidade": "deg",
        "cmd": "216A",
        "rapido": False,
        "min": -15,
        "max": 15,
        "calc": lambda b: _num(_s16(b, 0), 0.1, 1),
        "sim": lambda t: -0.1,
    },
    {
        "id": "KNOCK_CIL1",
        "nome": "Ajuste Ignicao / Knock Cil. 1",
        "unidade": "deg",
        "cmd": "21A0",
        "rapido": False,
        "min": -15,
        "max": 15,
        "calc": lambda b: _num(_s16(b, 8), 0.1, 1),
        "sim": lambda t: 0.0,
    },
    {
        "id": "KNOCK_CIL2",
        "nome": "Ajuste Ignicao / Knock Cil. 2",
        "unidade": "deg",
        "cmd": "21A0",
        "rapido": False,
        "min": -15,
        "max": 15,
        "calc": lambda b: _num(_s16(b, 10), 0.1, 1),
        "sim": lambda t: 0.0,
    },
    {
        "id": "KNOCK_CIL3",
        "nome": "Ajuste Ignicao / Knock Cil. 3",
        "unidade": "deg",
        "cmd": "21A0",
        "rapido": False,
        "min": -15,
        "max": 15,
        "calc": lambda b: _num(_s16(b, 12), 0.1, 1),
        "sim": lambda t: 0.0,
    },
    {
        "id": "KNOCK_CIL4",
        "nome": "Ajuste Ignicao / Knock Cil. 4",
        "unidade": "deg",
        "cmd": "21A0",
        "rapido": False,
        "min": -15,
        "max": 15,
        "calc": lambda b: _num(_s16(b, 14), 0.1, 1),
        "sim": lambda t: 0.0,
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
        "sim": lambda t: 99.7,
    },
    {
        "id": "CARGA",
        "nome": "Carga Motor (MAP / Baro)",
        "unidade": "%",
        "cmd": "21A2",
        "rapido": False,
        "min": 0,
        "max": 100,
        "calc": lambda b: _num(min(100.0, (_u16(b, 2) or 0) * 0.1), 1.0, 0),
        "sim": lambda t: 33.0,
    },
    {
        "id": "VEL",
        "nome": "Velocidade Veiculo",
        "unidade": "km/h",
        "cmd": "2134",
        "rapido": False,
        "min": 0,
        "max": 200,
        "calc": lambda b: _num(_u16(b, 0), 1.0, 0),
        "sim": lambda t: 0.0,
    },
    {
        "id": "RPM_ALVO",
        "nome": "Rotacao Alvo Marcha Lenta",
        "unidade": "rpm",
        "cmd": "21A4",
        "rapido": False,
        "min": 0,
        "max": 2000,
        "calc": lambda b: _num((_u16(b, 8) or 0) / 40.0, 1.0, 0),
        "sim": lambda t: 850.0,
    },
    {
        "id": "TI_BANCO1",
        "nome": "Tempo Injecao Grupo 1/4",
        "unidade": "ms",
        "cmd": "2154",
        "rapido": False,
        "min": 0,
        "max": 25,
        "calc": lambda b: _num(_u16(b, 0), 0.002, 2),
        "sim": lambda t: 3.27,
    },
    {
        "id": "TI_BANCO2",
        "nome": "Tempo Injecao Grupo 2/3",
        "unidade": "ms",
        "cmd": "2155",
        "rapido": False,
        "min": 0,
        "max": 25,
        "calc": lambda b: _num(_u16(b, 0), 0.002, 2),
        "sim": lambda t: 3.23,
    },
    {
        "id": "TI_BASE",
        "nome": "Tempo Injecao Base Teorico",
        "unidade": "ms",
        "cmd": "216B",
        "rapido": False,
        "min": 0,
        "max": 25,
        "calc": lambda b: _num(_u16(b, 0), 0.01, 2),
        "sim": lambda t: 3.24,
    },
    {
        "id": "TPS_2",
        "nome": "Posicao Borboleta Canal 2",
        "unidade": "%",
        "cmd": "213E",
        "rapido": False,
        "min": 0,
        "max": 100,
        "calc": lambda b: _num(_u16(b, 0), 0.1, 1),
        "sim": lambda t: 0.0,
    },
    {
        "id": "LAMBDA_2",
        "nome": "Sonda Lambda Pos-Cat",
        "unidade": "mV",
        "cmd": "21A3",
        "rapido": False,
        "min": 0,
        "max": 1000,
        "calc": lambda b: _num(_u16(b, 16), 1.0, 0),
        "sim": lambda t: round(650 + 18 * math.sin(t * 0.4), 0),
    },
    {
        "id": "STFT_RAW",
        "nome": "Integrador Lambda Bruto (Raw)",
        "unidade": "raw",
        "cmd": "2167",
        "rapido": False,
        "min": 0,
        "max": 2048,
        "calc": lambda b: _num(_u16(b, 0), 1.0, 0),
        "sim": lambda t: 1024.0,
    },
    {
        "id": "LTFT",
        "nome": "Adaptativo Mistura (LTFT)",
        "unidade": "%",
        "cmd": "2169",
        "rapido": False,
        "min": -30,
        "max": 30,
        "calc": lambda b: _num(_s16(b, 0), 0.1, 1),
        "sim": lambda t: -0.4,
    },
    {
        "id": "ESTADO_MOTOR",
        "nome": "Estado Motor (2=Parado 4=Rodando)",
        "unidade": "Code",
        "cmd": "21A6",
        "rapido": False,
        "min": 0,
        "max": 5,
        "calc": lambda b: float(_u8(b, 4) or 0),
        "sim": lambda t: 4.0,
    },
    {
        "id": "AC_STATUS",
        "nome": "Status Compressor A/C / Carga",
        "unidade": "Ativo",
        "cmd": "21A6",
        "rapido": False,
        "min": 0,
        "max": 1,
        "calc": lambda b: 1.0 if (_u8(b, 6) or 0) & 0x40 else 0.0,"sim": lambda t: 0.0,
    },
    {
        "id": "FAN_STATUS",
        "nome": "Eletroventilador Radiador",
        "unidade": "Ativo",
        "cmd": "21A6",
        "rapido": False,
        "min": 0,
        "max": 1,
        "calc": lambda b: float(_u8(b, 8) or 0),
        "sim": lambda t: 0.0,
    },
    {
        "id": "RODA_FONICA",
        "nome": "Aprendizagem Roda Fonica",
        "unidade": "OK",
        "cmd": "21A6",
        "rapido": False,
        "min": 0,
        "max": 1,
        "calc": lambda b: float(_u8(b, 10) or 0),
        "sim": lambda t: 1.0,
    },
]
