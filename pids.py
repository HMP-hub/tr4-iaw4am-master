# -*- coding: utf-8 -*-
"""
Mapeamento de PIDs e Fórmulas para ECU Magneti Marelli IAW 4AM (Pajero TR4 2.0 16V Flex)
Protocolo: KWP2000 over K-Line / ELM327
"""

# Comandos de Inicialização de Sessão KWP2000
KWP_START_SESSION = "10 81"  # Iniciar sessão de diagnóstico ECU
KWP_STOP_SESSION = "20"      # Parar sessão

# Dicionário de PIDs e Fórmulas de Conversão
# Cada PID possui o comando hex, nome descritivo, unidade e função lambda de conversão dos bytes (A, B, ...)
PIDS_CONFIG = {
    "RPM": {
        "cmd": "21 0C", # Ou PID padrão 010C / específico 21...
        "name": "Rotação do Motor",
        "unit": "rpm",
        "formula": lambda a, b: ((a * 256) + b) / 4 if b is not None else 0
    },
    "TEMP_AGUA": {
        "cmd": "21 05",
        "name": "Temperatura da Água",
        "unit": "°C",
        "formula": lambda a, b=None: a - 40
    },
    "MAP": {
        "cmd": "21 0B",
        "name": "Pressão do Coletor (MAP)",
        "unit": "kPa",
        "formula": lambda a, b=None: a
    },
    "TPS": {
        "cmd": "21 11",
        "name": "Posição da Borboleta (TPS)",
        "unit": "%",
        "formula": lambda a, b=None: round((a * 100) / 255, 1)
    },
    "BATT": {
        "cmd": "21 42",
        "name": "Tensão da Bateria",
        "unit": "V",
        "formula": lambda a, b: ((a * 256) + b) / 1000 if b is not None else 0
    },
    # PIDs avançados / específicos da IAW 4AM (ex: 21A0, 21A1 ajustados para leitura real)
    "PID_21A0": {
        "cmd": "21 A0",
        "name": "Avanço de Ignição / Parâmetro A0",
        "unit": "°BTDC",
        "formula": lambda a, b=None: round((a - 128) / 2, 2)
    },
    "PID_21A1": {
        "cmd": "21 A1",
        "name": "Tempo de Injeção / Parâmetro A1",
        "unit": "ms",
        "formula": lambda a, b: ((a * 256) + b) / 100 if b is not None else 0
    }
}
