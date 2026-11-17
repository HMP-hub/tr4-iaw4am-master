# coding: utf-8
# Mapa de leitura da ECU Magneti Marelli IAW 4AM (Pajero TR4 flex), KWP2000 modo 21.
# Calibrado com varreduras reais (14/11 a 16/11/2026: motor parado, pedal 0/50/100%,
# marcha lenta aquecida, ventoinha ligada, cut-off e rodagem em carga).
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


def _calc_stft(b):
    v = _u16(b, 0)
    # Centro neutro = 128 (0.0%); cada unidade = 100/156 (~0.641%).
    # Em motor parado (1024) ou cut-off (128), retorna 0.0%.
    if v is None or v == 1024 or v == 128:
        return 0.0
    return round((v - 128.0) / 1.56, 1)


def _calc_temp(b, idx):
    v = _u16(b, idx)
    if v is None:
        return 0.0
    return round(float(v - 40), 0)


PIDS_DB = [
    # --- Principais (rapido=True: marcados por padrao no Painel e Log) ---
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
        "sim": lambda t: round(31.5 + 1.2 * math.sin(t * 2.0), 1),
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
        "nome": "Posicao Borboleta",
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
        "sim": lambda t: round(450 + 380 * math.sin(t * 3.5), 0),
    },
    {
        "id": "STFT",
        "nome": "Integrador Lambda (STFT)",
        "unidade": "%",
        "cmd": "21A0",
        "rapido": True,
        "conf": "ok",
        "min": -35,
        "max": 35,
        "calc": lambda b: _calc_stft(b[6:8]),
        "sim": lambda t: round(4.5 * math.sin(t * 1.4), 1),
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
        "sim": lambda t: round(2.5 + 0.15 * math.sin(t * 2.2), 2),
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
        # Bytes 10:12 de 21A0 (= PID 2135): marca -4.4 a -4.8 graus em lenta (-5 no OBDLink)
        "calc": lambda b: _num(_s16(b, 10), 0.1, 1),
        "sim": lambda t: round(-4.5 + 1.2 * math.sin(t * 1.8), 1),
    },
    {
        "id": "CORR_IGN",
        "nome": "Atraso Ignicao (Knock)",
        "unidade": "graus",
        "cmd": "216A",
        "rapido": True,
        "conf": "ok",
        "min": -15,
        "max": 15,
        "calc": lambda b: _num(_s16(b, 0), 0.1, 1),
        "sim": lambda t: 0.0,
    },

    # --- Complementares confirmados (selecionaveis em PIDS / LOG CSV) ---
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
        "sim": lambda t: round(44.0 + 1.5 * math.sin(t * 0.15), 0),
    },
    {
        "id": "LTFT",
        "nome": "Adaptativo Mistura (LTFT)",
        "unidade": "%",
        "cmd": "2169",
        "rapido": False,
        "conf": "ok",
        "min": -30,
        "max": 30,
        "calc": lambda b: _num(_s16(b, 0), 0.1, 1),
        "sim": lambda t: 3.8,
    },
    {
        "id": "FATOR_SFS",
        "nome": "Integrador Adapt. Combustivel",
        "unidade": "raw",
        "cmd": "2147",
        "rapido": False,
        "conf": "ok",
        "min": 30000,
        "max": 55000,
        # 40000 (0x9C40) em repouso; varia dinamicamente em malha fechada (SFS/Lambda)
        "calc": lambda b: _num(_u16(b, 0), 1, 0),
        "sim": lambda t: round(45000 + 800 * math.sin(t * 0.5), 0),
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
        "cmd": "213A",
        "rapido": False,
        "conf": "ok",
        "min": 600,
        "max": 1200,
        "calc": lambda b: _num(_u16(b, 0), 1, 0),
        "sim": lambda t: 750.0,
    },
    {
        "id": "TENSAO_KNOCK",
        "nome": "Sensor Detonacao (Knock)",
        "unidade": "V",
        "cmd": "2142",
        "rapido": False,
        "conf": "est",
        "min": 0.0,
        "max": 5.0,
        "calc": lambda b: _num(_u16(b, 0), 5.0 / 1023.0, 2),
        "sim": lambda t: round(0.35 + 0.12 * abs(math.sin(t * 2.1)), 2),
    },
    {
        "id": "REL_AF",
        "nome": "Relacao Ar/Combustivel",
        "unidade": "A/F",
        "cmd": "2148",
        "rapido": False,
        "conf": "est",
        "min": 8.5,
        "max": 16.0,
        "calc": lambda b: _num(_u16(b, 0), 0.01, 2),
        "sim": lambda t: 13.2,
    },
    {
        "id": "PURGA_CANISTER",
        "nome": "Valvula Canister (EVAP)",
        "unidade": "%",
        "cmd": "213E",
        "rapido": False,
        "conf": "est",
        "min": 0,
        "max": 100,
        "calc": lambda b: _num(_u8(b, 0), 100.0 / 255.0, 1),
        "sim": lambda t: round(max(0.0, 25.0 * math.sin(t * 0.4)), 1),
    },
    {
        "id": "ESTADO_MOTOR",
        "nome": "Estado do Motor",
        "unidade": "",
        "cmd": "21A6",
        "rapido": False,
        "conf": "ok",
        "min": 0,
        "max": 1,
        "calc": lambda b: (
            "PARADO" if _u8(b, 4) == 2
            else ("RODANDO" if _u8(b, 4) == 4
                  else (f"ST:{_u8(b, 4)}" if _u8(b, 4) is not None else "--"))
        ),
        "sim": lambda t: "RODANDO",
    },
    {
        "id": "STATUS_FAN",
        "nome": "Eletroventilador (Ventoinha)",
        "unidade": "",
        "cmd": "21A6",
        "rapido": False,
        "conf": "ok",
        "min": 0,
        "max": 1,
        "calc": lambda b: (
            "LIGADA" if (_u8(b, 8) or 0) & 0x08
            else ("DESLIGADA" if _u8(b, 8) is not None else "--")
        ),
        "sim": lambda t: "LIGADA" if math.sin(t * 0.25) > 0.6 else "DESLIGADA",
    },
    {
        "id": "STATUS_AC",
        "nome": "Ar-Condicionado (A/C)",
        "unidade": "",
        "cmd": "21A6",
        "rapido": False,
        "conf": "ok",
        "min": 0,
        "max": 1,
        "calc": lambda b: (
            "LIGADO" if (_u8(b, 6) or 0) & 0x40
            else ("DESLIGADO" if _u8(b, 6) is not None else "--")
        ),
        "sim": lambda t: "DESLIGADO",
    },
    {
        "id": "RODA_FONICA",
        "nome": "Aprendizado Roda Fonica",
        "unidade": "",
        "cmd": "21A6",
        "rapido": False,
        "conf": "ok",
        "min": 0,
        "max": 1,
        "calc": lambda b: (
            "APRENDIDA" if (_u8(b, 10) or 0) > 0
            else ("PENDENTE" if _u8(b, 10) is not None else "--")
        ),
        "sim": lambda t: "APRENDIDA",
    },
]
