# coding: utf-8
import math
import random
from operator import itemgetter

b0 = itemgetter(0)
b1 = itemgetter(1)
b3 = itemgetter(3)
b5 = itemgetter(5)


def decode_malha_completa(bytes_a5):
    if len(bytes_a5) < 6:
        return "SEM DADOS"
    d = b3(bytes_a5)
    g = b5(bytes_a5)
    if d == 0:
        return "EMERGENCIA"
    if d == 1 and g == 1:
        return "CL - LENTA"
    if d == 1 and g == 0:
        return "CL - CRUZEIRO"
    if d == 2 and g == 2:
        return "OL - WOT"
    if d == 2 and g == 1:
        return "OL - CUTOFF/FRIO"
    return f"OL - TRANS ({d}/{g})"


PIDS_DB = [
    {"id": "STATUS_MALHA", "nome": "Status Malha Completo", "categoria": "Mistura & Flex", "cmd": "21A5", "unidade": "State", "rapido": True, "calc": lambda b: decode_malha_completa(list(b)), "sim": lambda t: random.choice(["CL - LENTA", "CL - CRUZEIRO", "OL - WOT", "OL - CUTOFF/FRIO"])},
    {"id": "STFT", "nome": "STFT (Integrador Lambda)", "categoria": "Mistura & Flex", "cmd": "2147", "unidade": "%", "rapido": True, "calc": lambda b: round(((b0(b) - 156) / 156.0) * 100.0, 1) if len(b) >= 1 else 0.0, "sim": lambda t: round(math.sin(t * 2.5) * 6.5 + 2.0, 1)},
    {"id": "LTFT", "nome": "LTFT (Auto-Adaptativo)", "categoria": "Mistura & Flex", "cmd": "2179", "unidade": "%", "rapido": True, "calc": lambda b: round(((b0(b) - 156) / 156.0) * 100.0, 1) if len(b) >= 1 else 0.0, "sim": lambda t: 3.8},
    {"id": "AFR_ALVO", "nome": "AFR Alvo (Mapa SFS)", "categoria": "Mistura & Flex", "cmd": "217B", "unidade": "AFR", "rapido": True, "calc": lambda b: round((b1(b) if len(b) >= 2 else b0(b)) / 10.0, 1) if len(b) >= 1 else 13.2, "sim": lambda t: 13.2},
    {"id": "ETANOL_REAL", "nome": "Etanol SFS (Base E27)", "categoria": "Mistura & Flex", "cmd": "217B", "unidade": "%", "rapido": True, "calc": lambda b: round(max(0.0, min(100.0, 27.0 + ((132 - (b1(b) if len(b) >= 2 else b0(b))) * 1.738))), 0) if len(b) >= 1 else 27.0, "sim": lambda t: 27.0},
    {"id": "ETANOL_INST", "nome": "Etanol Real (SFS+Trims)", "categoria": "Mistura & Flex", "cmd": "CALC_HIBRIDO", "unidade": "%", "rapido": True, "calc": lambda b: 27.0, "sim": lambda t: 31.0},
    {"id": "SONDA_PRE", "nome": "Sonda Lambda Pre-Cat", "categoria": "Mistura & Flex", "cmd": "2141", "unidade": "mV", "rapido": True, "calc": lambda b: round(((b1(b) if len(b) >= 2 else b0(b)) * 4.88), 0) if len(b) >= 1 else 0.0, "sim": lambda t: round(450 + math.sin(t * 4.0) * 380, 0)},
    {"id": "SONDA_POS", "nome": "Sonda Lambda Pos-Cat", "categoria": "Mistura & Flex", "cmd": "2142", "unidade": "mV", "rapido": False, "calc": lambda b: round(((b1(b) if len(b) >= 2 else b0(b)) * 4.88), 0) if len(b) >= 1 else 0.0, "sim": lambda t: 680.0},
    {"id": "REGIME_CARGA", "nome": "Regime Pedal (0/1/2)", "categoria": "Mistura & Flex", "cmd": "215C", "unidade": "Code", "rapido": False, "calc": lambda b: float(b0(b)) if len(b) >= 1 else 0.0, "sim": lambda t: 1.0},
    {"id": "RPM", "nome": "Rotacao Motor (RPM)", "categoria": "Motor & Injecao", "cmd": "2131", "unidade": "rpm", "rapido": True, "calc": lambda b: float((b0(b) * 256) + b1(b)) if len(b) >= 2 else 0.0, "sim": lambda t: round(780 + math.sin(t) * 35, 0)},
    {"id": "TI_PRINCIPAL", "nome": "Tempo Injecao Efetivo", "categoria": "Motor & Injecao", "cmd": "2145", "unidade": "ms", "rapido": True, "calc": lambda b: round(((b0(b) * 256) + b1(b)) * 0.004, 2) if len(b) >= 2 else 0.0, "sim": lambda t: round(3.25 + math.sin(t * 2) * 0.25, 2)},
    {"id": "MAP_KPA", "nome": "Pressao Coletor (MAP)", "categoria": "Motor & Injecao", "cmd": "2135", "unidade": "kPa", "rapido": True, "calc": lambda b: round(((b0(b) * 256) + b1(b)) * 0.1, 1) if len(b) >= 2 else (float(b0(b)) if len(b) == 1 else 0.0), "sim": lambda t: round(34.0 + math.sin(t * 1.5) * 2.0, 1)},
    {"id": "PRESSAO_BARO", "nome": "Pressao Barometrica", "categoria": "Motor & Injecao", "cmd": "2136", "unidade": "kPa", "rapido": False, "calc": lambda b: round(((b0(b) * 256) + b1(b)) * 0.1, 1) if len(b) >= 2 else (float(b0(b)) if len(b) == 1 else 0.0), "sim": lambda t: 99.5},
    {"id": "CARGA_MOTOR", "nome": "Carga Calculada Motor", "categoria": "Motor & Injecao", "cmd": "2138", "unidade": "%", "rapido": False, "calc": lambda b: round((b0(b) / 255.0) * 100.0, 1) if len(b) >= 1 else 0.0, "sim": lambda t: 22.4},
    {"id": "TI_CIL1", "nome": "Tempo Injecao Cil. 1", "categoria": "Motor & Injecao", "cmd": "2161", "unidade": "ms", "rapido": False, "calc": lambda b: round(((b0(b) * 256) + b1(b)) * 0.004, 2) if len(b) >= 2 else 0.0, "sim": lambda t: 3.24},
    {"id": "TI_CIL2", "nome": "Tempo Injecao Cil. 2", "categoria": "Motor & Injecao", "cmd": "2162", "unidade": "ms", "rapido": False, "calc": lambda b: round(((b0(b) * 256) + b1(b)) * 0.004, 2) if len(b) >= 2 else 0.0, "sim": lambda t: 3.26},
    {"id": "TI_CIL3", "nome": "Tempo Injecao Cil. 3", "categoria": "Motor & Injecao", "cmd": "2163", "unidade": "ms", "rapido": False, "calc": lambda b: round(((b0(b) * 256) + b1(b)) * 0.004, 2) if len(b) >= 2 else 0.0, "sim": lambda t: 3.25},
    {"id": "TI_CIL4", "nome": "Tempo Injecao Cil. 4", "categoria": "Motor & Injecao", "cmd": "2164", "unidade": "ms", "rapido": False, "calc": lambda b: round(((b0(b) * 256) + b1(b)) * 0.004, 2) if len(b) >= 2 else 0.0, "sim": lambda t: 3.23},
    {"id": "AVANCO_IGN", "nome": "Avanco Ignicao Final", "categoria": "Ignicao & Knock", "cmd": "2149", "unidade": "deg", "rapido": True, "calc": lambda b: round((b0(b) - 128) * 0.5, 1) if len(b) >= 1 else 0.0, "sim": lambda t: round(10.5 + math.sin(t) * 2.0, 1)},
    {"id": "KNOCK_CIL1", "nome": "Atraso Knock Cil. 1", "categoria": "Ignicao & Knock", "cmd": "2181", "unidade": "deg", "rapido": False, "calc": lambda b: round(b0(b) * 0.375, 2) if len(b) >= 1 else 0.0, "sim": lambda t: 0.0},
    {"id": "KNOCK_CIL2", "nome": "Atraso Knock Cil. 2", "categoria": "Ignicao & Knock", "cmd": "2182", "unidade": "deg", "rapido": False, "calc": lambda b: round(b0(b) * 0.375, 2) if len(b) >= 1 else 0.0, "sim": lambda t: 0.0},
    {"id": "KNOCK_CIL3", "nome": "Atraso Knock Cil. 3", "categoria": "Ignicao & Knock", "cmd": "2183", "unidade": "deg", "rapido": False, "calc": lambda b: round(b0(b) * 0.375, 2) if len(b) >= 1 else 0.0, "sim": lambda t: 0.0},
    {"id": "KNOCK_CIL4", "nome": "Atraso Knock Cil. 4", "categoria": "Ignicao & Knock", "cmd": "2184", "unidade": "deg", "rapido": False, "calc": lambda b: round(b0(b) * 0.375, 2) if len(b) >= 1 else 0.0, "sim": lambda t: 0.0},
    {"id": "TEMP_AGUA", "nome": "Temperatura Agua (ECT)", "categoria": "Temp & Eletrica", "cmd": "213B", "unidade": "C", "rapido": True, "calc": lambda b: float((b1(b) if len(b) >= 2 else b0(b)) - 40) if len(b) >= 1 else 0.0, "sim": lambda t: 88.0},
    {"id": "TEMP_AR", "nome": "Temperatura Ar (IAT)", "categoria": "Temp & Eletrica", "cmd": "213C", "unidade": "C", "rapido": False, "calc": lambda b: float((b1(b) if len(b) >= 2 else b0(b)) - 40) if len(b) >= 1 else 0.0, "sim": lambda t: 42.0},
    {"id": "BATERIA_V", "nome": "Tensao Bateria", "categoria": "Temp & Eletrica", "cmd": "213E", "unidade": "V", "rapido": True, "calc": lambda b: round((b1(b) if len(b) >= 2 else b0(b)) * 0.0704, 2) if len(b) >= 1 else 0.0, "sim": lambda t: 13.85},
    {"id": "TPS_PCT", "nome": "Posicao Borboleta (TPS)", "categoria": "Cambio & Atuadores", "cmd": "2133", "unidade": "%", "rapido": False, "calc": lambda b: round(((b1(b) if len(b) >= 2 else b0(b)) / 255.0) * 100.0, 1) if len(b) >= 1 else 0.0, "sim": lambda t: 12.5},
    {"id": "VELOCIDADE", "nome": "Velocidade Veiculo", "categoria": "Cambio & Atuadores", "cmd": "2132", "unidade": "km/h", "rapido": False, "calc": lambda b: float(b1(b) if len(b) >= 2 else b0(b)) if len(b) >= 1 else 0.0, "sim": lambda t: 0.0},
    {"id": "CAMBIO_NEUTRO", "nome": "Status Cambio (N/Eng)", "categoria": "Cambio & Atuadores", "cmd": "215A", "unidade": "State", "rapido": False, "calc": lambda b: "NEUTRO / P" if (len(b) >= 1 and (b0(b) & 0x01)) else "ENGATADO", "sim": lambda t: "NEUTRO / P"},
    {"id": "VENTOINHA_STATUS", "nome": "Eletroventilador", "categoria": "Cambio & Atuadores", "cmd": "215E", "unidade": "State", "rapido": False, "calc": lambda b: "DESLIGADA" if (len(b) == 0 or b0(b) == 0) else ("ALTA VEL." if b0(b) >= 2 else "BAIXA VEL."), "sim": lambda t: "DESLIGADA"},
    {"id": "AC_STATUS", "nome": "Compressor A/C", "categoria": "Cambio & Atuadores", "cmd": "215F", "unidade": "State", "rapido": False, "calc": lambda b: "LIGADO" if (len(b) >= 1 and b0(b) > 0) else "DESLIGADO", "sim": lambda t: "DESLIGADO"},
    {"id": "CANISTER_EVAP", "nome": "Valvula Canister (EVAP)", "categoria": "Cambio & Atuadores", "cmd": "214E", "unidade": "%", "rapido": False, "calc": lambda b: round((b0(b) / 255.0) * 100.0, 1) if len(b) >= 1 else 0.0, "sim": lambda t: 18.0},
]
