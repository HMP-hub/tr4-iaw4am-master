# coding: utf-8
# Mapa de leitura da ECU Magneti Marelli IAW 4AM (Pajero TR4 flex), KWP2000 modo 21.
#
# Versao final calibrada a partir das 8 varreduras reais (14/11 e 15/11/2026: motor desligado, pedal 0/50/100%,
# partida a frio, aquecimento em marcha lenta, aceleracao parado e rodagem a 50 e 66 km/h).
# "b" e a lista de bytes DEPOIS do cabecalho "61 xx" (o parse_bytes_kwp ja o tira), e
# todos os valores de 16 bits sao big-endian.
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
    # 1024 (0x0400) e o valor neutro de motor parado; rodando o centro (0%) e 512 (0x0200)
    if v is None or v == 1024:
        return 0.0
    return round(((v - 512.0) / 512.0) * 100.0, 1)


def _calc_temp(b, idx):
    v = _u16(b, idx)
    if v is None:
        return 0.0
    return round(float(v - 40), 0)


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
        "sim": lambda t: round(860 + 25 * math.sin(t * 2.0), 0),
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
        "sim": lambda t: round(33.0 + 1.5 * math.sin(t * 2.0), 1),
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
        "sim": lambda t: round(450 + 360 * math.sin(t * 3.5), 0),
    },
    {
        "id": "STFT",
        "nome": "Integrador Lambda (STFT)",
        "unidade": "%",
        "cmd": "2167",
        "rapido": True,
        "conf": "ok",
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
        "conf": "ok",
        "min": 0,
        "max": 25,
        "calc": lambda b: _num(_u16(b, 16), 0.002, 2),
        "sim": lambda t: round(2.9 + 0.15 * math.sin(t * 2.2), 2),
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
        "calc": lambda b: _num(_s16(b, 18), 0.1, 1),
        "sim": lambda t: round(13.8 + 1.5 * math.sin(t * 1.8), 1),
    },

    # --- Complementares confirmados (selecionaveis em PIDS / LOG CSV) --------------------------------------------
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
        "sim": lambda t: round(38.0 + 1.5 * math.sin(t * 0.15), 0),
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
        "sim": lambda t: 0.8,
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
        "sim": lambda t: 85.0,
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
        "sim": lambda t: 805.0,
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
        "sim": lambda t: 99.7,
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
        "sim": lambda t: 33.0,
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
        "sim": lambda t: 1.85,
    },
    {
        "id": "CORR_IGN",
        "nome": "Correcao Avanco",
        "unidade": "graus",
        "cmd": "216A",
        "rapido": False,
        "conf": "ok",
        "min": -15,
        "max": 15,
        "calc": lambda b: _num(_s16(b, 0), 0.1, 1),
        "sim": lambda t: -0.1,
    },
    {
        "id": "CLOSED_LOOP",
        "nome": "Malha Fechada (2=Ativa 4=Fria)",
        "unidade": "Code",
        "cmd": "21A4",
        "rapido": False,
        "conf": "ok",
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
        "nome": "Indice Relacao Cambio",
        "unidade": "Code",
        "cmd": "2161",
        "rapido": False,
        "conf": "ok",
        "min": 0,
        "max": 10,
        "calc": lambda b: _num(_u16(b, 0), 1, 0),
        "sim": lambda t: 4.0,
    },

    # --- Apenas conferir em uso natural (abastecimento e ventoinha) ----------------------------------------------
    {
        "id": "ETANOL_REAL",
        "nome": "(?) Etanol Aprendido",
        "unidade": "%",
        "cmd": "21A7",
        "rapido": False,
        "conf": "provavel",
        "min": 0,
        "max": 100,
        "calc": lambda b: float(max(0, min(100, (_u8(b, 3) - 128)))) if _u8(b, 3) is not None else 0.0,
        "sim": lambda t: 34.0,
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
