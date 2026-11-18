# coding: utf-8
import os
import csv
import json
import time
import threading
from datetime import datetime
from operator import itemgetter
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from pids import PIDS_DB

# Apenas comandos compostos rapidos para vigilancia em segundo plano (mantem taxa alta de leitura)
PIDS_VIGILANCIA_BG = {
    "RPM", "VEL", "MAP", "ECT", "TPS", "LAMBDA_1",
    "STFT", "VBAT", "TI_EFETIVO", "AVANCO",
    "KNOCK_CIL1", "KNOCK_CIL2", "KNOCK_CIL3", "KNOCK_CIL4",
    "IAC", "RPM_ALVO", "FAN_STATUS",
}

CMDS_MODO_01_PROBE = [
    ("0103", "Status Loop OBD2"),
    ("0104", "Carga Calculada"),
    ("0105", "Temp Agua OBD2"),
    ("0106", "STFT Banco 1 OBD2"),
    ("0107", "LTFT Banco 1 OBD2"),
    ("010B", "MAP OBD2"),
    ("010C", "RPM OBD2"),
    ("010D", "Velocidade OBD2"),
    ("010E", "Avanco Ignicao OBD2"),
    ("010F", "Temp Ar OBD2"),
    ("0111", "TPS OBD2"),
    ("0114", "Sonda Pre-Cat OBD2"),
    ("0142", "Tensao Bateria OBD2"),
    ("0152", "Percentual Etanol OBD2"),
]

CMDS_MODO_21_VIVOS = [
    "213A", "213B", "2145", "2147", "2157", "2159",
    "2160", "2161", "2162", "2163", "2164", "2165",
    "2166", "2167", "2168", "2169", "216A", "216B",
    "2178", "2179", "217B",
    "21A0", "21A1", "21A2", "21A3", "21A4", "21A5", "21A6", "21A7",
]


class TR4EngineMixin:
    def _init_telemetria_viagem(self):
        self.tel = {
            "inicio_ts": time.time(),
            "amostras": 0,
            "amostras_mov": 0,
            "vel_max": 0.0,
            "rpm_max": 0.0,
            "ect_ini": None,
            "ect_min": None,
            "ect_max": None,
            "tempo_para_80c": None,
            "tempo_acima_98c": 0.0,
            "ultimo_ts": None,
            "knock_eventos": 0,
            "knock_pior_graus": 0.0,
            "knock_pior_cil": 0,
            "knock_pior_rpm": 0,
            "knock_pior_map": 0.0,
            "knock_ativo_frame": False,
            "lambda_ultimo_lado": None,
            "lambda_trocas": 0,
            "tempo_cl_quente": 0.0,
            "stft_soma": 0.0,
            "stft_n": 0,
            "stft_min": None,
            "stft_max": None,
            "ltft_ultimo": None,
            "pobre_carga_eventos": 0,
            "map_lenta_soma": 0.0,
            "map_lenta_n": 0,
            "iac_lenta_soma": 0.0,
            "iac_lenta_n": 0,
            "vbat_min_partida": None,
            "vbat_soma": 0.0,
            "vbat_n": 0,
            "vbat_max": None,
            "ti_lenta_soma": 0.0,
            "ti_lenta_n": 0,
            "cutoff_eventos": 0,
            "cutoff_ativo_frame": False,
            "avanco_lenta_soma": 0.0,
            "avanco_lenta_n": 0,
            "avanco_max": None,
            "alerta_critico_atual": "",
        }

    def reiniciar_telemetria_viagem(self, *args):
        self._init_telemetria_viagem()
        if hasattr(self, "lbl_boletim"):
            self.lbl_boletim.text = (
                "Nova viagem iniciada! Telemetria zerada.\n\n"
                "Monitorando 7 sistemas em segundo plano: detonacao por cilindro, arrefecimento, "
                "sonda lambda/mistura, vacuo/IAC, bateria/alternador, injecao/cut-off e ignicao."
            )
    def _processar_amostra_telemetria(self):
        if not hasattr(self, "tel"):
            self._init_telemetria_viagem()
        t = self.tel
        agora = time.time()
        dt = 0.0 if t["ultimo_ts"] is None else min(2.0, max(0.0, agora - t["ultimo_ts"]))
        t["ultimo_ts"] = agora
        t["amostras"] += 1

        rpm = self.valores_atuais.get("RPM")
        vel = self.valores_atuais.get("VEL")
        ect = self.valores_atuais.get("ECT")
        mp = self.valores_atuais.get("MAP")
        tps = self.valores_atuais.get("TPS")
        lam = self.valores_atuais.get("LAMBDA_1")
        stft = self.valores_atuais.get("STFT")
        ltft = self.valores_atuais.get("LTFT")
        ti = self.valores_atuais.get("TI_EFETIVO")
        av = self.valores_atuais.get("AVANCO")
        vbat = self.valores_atuais.get("VBAT")
        iac = self.valores_atuais.get("IAC")

        if isinstance(vel, (int, float)):
            if vel > t["vel_max"]:
                t["vel_max"] = vel
            if vel >= 3:
                t["amostras_mov"] += 1

        if isinstance(rpm, (int, float)) and rpm > t["rpm_max"]:
            t["rpm_max"] = rpm

        # 1. Sistema de Arrefecimento
        if isinstance(ect, (int, float)) and ect > -5:
            if t["ect_ini"] is None:
                t["ect_ini"] = ect
            if t["ect_min"] is None or ect < t["ect_min"]:
                t["ect_min"] = ect
            if t["ect_max"] is None or ect > t["ect_max"]:
                t["ect_max"] = ect
            if ect >= 80.0 and t["tempo_para_80c"] is None and t["ect_ini"] < 72.0:
                t["tempo_para_80c"] = round(agora - t["inicio_ts"], 0)
            if ect >= 98.0:
                t["tempo_acima_98c"] += dt

        # 2. Detonacao / Knock individual por cilindro (21A3[6:14])
        motor_rodando = isinstance(rpm, (int, float)) and rpm >= 650
        sob_carga = (isinstance(tps, (int, float)) and tps >= 12.0) or (isinstance(mp, (int, float)) and mp >= 52.0)
        k_cils = [
            self.valores_atuais.get("KNOCK_CIL1"),
            self.valores_atuais.get("KNOCK_CIL2"),
            self.valores_atuais.get("KNOCK_CIL3"),
            self.valores_atuais.get("KNOCK_CIL4"),
        ]
        pior_cil_idx = 0
        pior_cil_deg = 0.0
        for idx_c, val_c in enumerate(k_cils, start=1):
            if isinstance(val_c, (int, float)) and val_c < pior_cil_deg:
                pior_cil_deg = val_c
                pior_cil_idx = idx_c

        if motor_rodando and sob_carga and pior_cil_deg <= -0.5:
            if not t["knock_ativo_frame"]:
                t["knock_eventos"] += 1
                t["knock_ativo_frame"] = True
            if pior_cil_deg < t["knock_pior_graus"]:
                t["knock_pior_graus"] = pior_cil_deg
                t["knock_pior_cil"] = pior_cil_idx
                t["knock_pior_rpm"] = int(rpm)
                t["knock_pior_map"] = float(mp) if isinstance(mp, (int, float)) else 0.0
        else:
            t["knock_ativo_frame"] = False

        # 3. Sonda Lambda Pre-Cat & Mistura
        quente = isinstance(ect, (int, float)) and ect >= 75.0
        if quente and motor_rodando:
            t["tempo_cl_quente"] += dt
            if isinstance(lam, (int, float)):
                lado = "R" if lam >= 550 else ("P" if lam <= 350 else t["lambda_ultimo_lado"])
                if lado and t["lambda_ultimo_lado"] and lado != t["lambda_ultimo_lado"]:
                    t["lambda_trocas"] += 1
                if lado:
                    t["lambda_ultimo_lado"] = lado

            if isinstance(stft, (int, float)):
                t["stft_soma"] += stft
                t["stft_n"] += 1
                if t["stft_min"] is None or stft < t["stft_min"]:
                    t["stft_min"] = stft
                if t["stft_max"] is None or stft > t["stft_max"]:
                    t["stft_max"] = stft

        if isinstance(ltft, (int, float)):
            t["ltft_ultimo"] = ltft

        if (
            isinstance(mp, (int, float)) and mp >= 78.0
            and isinstance(tps, (int, float)) and tps >= 45.0
            and isinstance(lam, (int, float)) and lam < 480.0
            and isinstance(rpm, (int, float)) and rpm >= 2200
        ):
            t["pobre_carga_eventos"] += 1

        # 4. Marcha lenta aquecida (Vacuo MAP, Passos IAC, TI Lenta e Avanco Base)
        em_lenta_quente = (
            isinstance(ect, (int, float)) and ect >= 80.0
            and isinstance(vel, (int, float)) and vel == 0
            and isinstance(tps, (int, float)) and tps <= 1.0
            and isinstance(rpm, (int, float)) and 650 <= rpm <= 1050
        )
        if em_lenta_quente:
            if isinstance(mp, (int, float)) and 15.0 <= mp <= 65.0:
                t["map_lenta_soma"] += mp
                t["map_lenta_n"] += 1
            if isinstance(iac, (int, float)) and 5 <= iac <= 180:
                t["iac_lenta_soma"] += iac
                t["iac_lenta_n"] += 1
            if isinstance(ti, (int, float)) and 1.0 <= ti <= 6.0:
                t["ti_lenta_soma"] += ti
                t["ti_lenta_n"] += 1
            if isinstance(av, (int, float)) and -5.0 <= av <= 25.0:
                t["avanco_lenta_soma"] += av
                t["avanco_lenta_n"] += 1

        # 5. Sistema de Carga (Bateria & Alternador)
        if isinstance(vbat, (int, float)) and 7.0 <= vbat <= 16.5:
            if not motor_rodando:
                if t["vbat_min_partida"] is None or vbat < t["vbat_min_partida"]:
                    t["vbat_min_partida"] = vbat
            else:
                t["vbat_soma"] += vbat
                t["vbat_n"] += 1
                if t["vbat_max"] is None or vbat > t["vbat_max"]:
                    t["vbat_max"] = vbat

        # 6. Injecao & Cut-off
        em_cutoff = (
            isinstance(rpm, (int, float)) and rpm >= 1500
            and isinstance(tps, (int, float)) and tps <= 0.5
            and isinstance(ti, (int, float)) and ti == 0.0
        )
        if em_cutoff:
            if not t["cutoff_ativo_frame"]:
                t["cutoff_eventos"] += 1
                t["cutoff_ativo_frame"] = True
        else:
            t["cutoff_ativo_frame"] = False

        # 7. Avanco maximo em carga
        if motor_rodando and isinstance(av, (int, float)) and -10.0 <= av <= 50.0:
            if t["avanco_max"] is None or av > t["avanco_max"]:
                t["avanco_max"] = av

        alerta = ""
        if isinstance(ect, (int, float)) and ect >= 103.0:
            alerta = f"ALERTA CRITICO: TEMPERATURA AGUA {ect:.0f} C!"
        elif pior_cil_deg <= -3.0 and sob_carga and motor_rodando:
            alerta = f"ALERTA KNOCK CIL {pior_cil_idx}: ATRASO {pior_cil_deg:.1f} GRAUS!"
        elif motor_rodando and isinstance(vbat, (int, float)) and vbat < 12.6:
            alerta = f"ALERTA ALTERNADOR: TENSAO BAIXA ({vbat:.1f} V)!"
        t["alerta_critico_atual"] = alerta
    def gerar_texto_boletim(self):
        if not hasattr(self, "tel"):
            self._init_telemetria_viagem()
        t = self.tel
        dur_s = max(1, int(time.time() - t["inicio_ts"]))
        mins, segs = divmod(dur_s, 60)

        # 1. Detonacao / Knock por Cilindro
        ev_k = t["knock_eventos"]
        pior_k = t["knock_pior_graus"]
        pior_c = t["knock_pior_cil"]
        if ev_k == 0 and pior_k > -0.5:
            sev_k = "NORMAL (Sem atraso por detonacao registrado)"
        elif pior_k >= -2.0 and ev_k <= 8:
            sev_k = "LEVE (Pontual em retomada - aceitavel)"
        elif pior_k >= -4.5:
            sev_k = "MODERADA (Atencao: octanagem combustivel / carbonizacao)"
        else:
            sev_k = "SEVERA (Risco mecanico - revisar combustivel/velas)"

        det_k = (
            f"  - Gravidade: {sev_k}\n"
            f"  - Atraso max ECU: {pior_k:.2f} graus"
            + (f" (Cilindro {pior_c} a {t['knock_pior_rpm']} rpm / {t['knock_pior_map']:.1f} kPa)\n" if ev_k > 0 else "\n")
            + f"  - Eventos sob carga: {ev_k} ocorrencia(s)"
        )

        # 2. Sistema de Arrefecimento
        ect_ini = f"{t['ect_ini']:.0f} C" if t["ect_ini"] is not None else "--"
        ect_max = f"{t['ect_max']:.0f} C" if t["ect_max"] is not None else "--"
        if t["ect_max"] is None:
            diag_ect = "Aguardando amostras de temperatura"
        elif t["ect_max"] >= 103.0:
            diag_ect = "CRITICO: Superaquecimento detectado (>= 103 C)"
        elif t["ect_max"] >= 98.0:
            diag_ect = "ATENCAO: Temperatura elevada (98-102 C)"
        elif dur_s >= 600 and t["amostras_mov"] > 30 and t["ect_max"] < 78.0:
            diag_ect = "ATENCAO: Motor nao atingiu 78 C (valvula termostatica aberta?)"
        else:
            diag_ect = "NORMAL (Controle termico estavel)"

        t80_txt = f"{int(t['tempo_para_80c'])}s" if t["tempo_para_80c"] is not None else "N/A"
        det_ect = (
            f"  - Estado: {diag_ect}\n"
            f"  - Inicio: {ect_ini}  |  Pico Maximo: {ect_max}\n"
            f"  - Tempo ate 80 C: {t80_txt}  |  Tempo >= 98 C: {t['tempo_acima_98c']:.0f}s"
        )

        # 3. Sonda Lambda Pre-Cat & Mistura
        taxa_sonda = (t["lambda_trocas"] / (t["tempo_cl_quente"] / 60.0)) if t["tempo_cl_quente"] >= 20.0 else None
        if taxa_sonda is None:
            diag_sonda = "Aguardando 20s+ em malha fechada quente (>= 75 C)"
            taxa_txt = "--"
        elif taxa_sonda >= 22.0:
            diag_sonda = "NORMAL (Sonda pre-cat rapida e responsiva)"
            taxa_txt = f"{taxa_sonda:.0f} trocas/min"
        else:
            diag_sonda = "ATENCAO: Sonda pre-cat lenta/envelhecida (< 22 trocas/min)"
            taxa_txt = f"{taxa_sonda:.0f} trocas/min"

        stft_med = f"{(t['stft_soma'] / t['stft_n']):+.1f}%" if t["stft_n"] > 0 else "--"
        stft_faixa = f"{t['stft_min']:+.1f}% a {t['stft_max']:+.1f}%" if t["stft_n"] > 0 else "--"
        ltft_txt = f"{t['ltft_ultimo']:+.1f}%" if t["ltft_ultimo"] is not None else "--"

        det_mist = (
            f"  - Sonda Pre-Cat: {diag_sonda} ({taxa_txt})\n"
            f"  - STFT Medio: {stft_med} (Faixa: {stft_faixa})\n"
            f"  - LTFT Atual: {ltft_txt}\n"
            f"  - Alertas mistura pobre em carga alta: {t['pobre_carga_eventos']}"
        )

        # 4. Vacuo Coletor & Marcha Lenta
        if t["map_lenta_n"] >= 5:
            map_med = t["map_lenta_soma"] / t["map_lenta_n"]
            iac_med = (t["iac_lenta_soma"] / t["iac_lenta_n"]) if t["iac_lenta_n"] > 0 else 0
            if map_med > 40.0:
                diag_lenta = "ATENCAO: Vacuo fraco em lenta (> 40 kPa - possivel entrada falsa de ar)"
            elif iac_med > 110:
                diag_lenta = "ATENCAO: IAC muito aberto (> 110 passos - limpar TBI)"
            else:
                diag_lenta = "NORMAL (Vedacao admissao e marcha lenta saudaveis)"
            det_lenta = (
                f"  - Estado: {diag_lenta}\n"
                f"  - Vacuo MAP medio em lenta quente: {map_med:.1f} kPa\n"
                f"  - Abertura media atuador IAC: {iac_med:.0f} passos"
            )
        else:
            det_lenta = "  - Aguardando marcha lenta estabilizada com motor >= 80 C."

        # 5. Sistema de Carga (Bateria & Alternador)
        if t["vbat_n"] > 0:
            vbat_med = t["vbat_soma"] / t["vbat_n"]
            vbat_max = t["vbat_max"] or vbat_med
            v_part = f"{t['vbat_min_partida']:.1f} V" if t["vbat_min_partida"] is not None else "N/A"
            if vbat_med < 13.2:
                diag_bat = "ATENCAO: Tensao de carga baixa (< 13.2 V - revisar alternador/correia)"
            elif vbat_max > 14.9:
                diag_bat = "ATENCAO: Sobretensao (> 14.9 V - regulador de voltagem)"
            else:
                diag_bat = "NORMAL (Alternador e regulador operando na faixa ideal)"
            det_bat = (
                f"  - Estado: {diag_bat}\n"
                f"  - Tensao media rodando: {vbat_med:.1f} V (Pico: {vbat_max:.1f} V)\n"
                f"  - Minima pre-partida: {v_part}"
            )
        else:
            det_bat = "  - Aguardando amostras com motor em funcionamento."

        # 6. Sistema de Injecao & Cut-Off
        if t["ti_lenta_n"] >= 3:
            ti_med = t["ti_lenta_soma"] / t["ti_lenta_n"]
            if ti_med < 1.9:
                diag_inj = "ATENCAO: Tempo de injecao muito curto em lenta (< 1.9 ms - pressao alta/mistura rica)"
            elif ti_med > 3.2:
                diag_inj = "ATENCAO: Tempo de injecao elevado em lenta (> 3.2 ms - bico sujo/pressao baixa)"
            else:
                diag_inj = "NORMAL (Vazao e estanqueidade de bicos equilibradas)"
            det_inj = (
                f"  - Estado: {diag_inj}\n"
                f"  - Tempo injecao medio lenta quente: {ti_med:.2f} ms\n"
                f"  - Cortes de combustivel (Cut-Off) detectados: {t['cutoff_eventos']}"
            )
        else:
            det_inj = f"  - Cortes de combustivel (Cut-Off) detectados: {t['cutoff_eventos']}"

        # 7. Ignicao & Eficiencia
        av_lenta_txt = f"{(t['avanco_lenta_soma'] / t['avanco_lenta_n']):.1f} graus" if t["avanco_lenta_n"] > 0 else "--"
        av_max_txt = f"{t['avanco_max']:.1f} graus" if t["avanco_max"] is not None else "--"
        det_ign = (
            f"  - Avanco medio em lenta quente: {av_lenta_txt}\n"
            f"  - Avanco maximo atingido: {av_max_txt}"
        )

        return (
            f"=== BOLETIM TECNICO DE TELEMETRIA - TR4 2.0 ===\n"
            f"Duracao monitorada: {mins}m {segs}s  |  Amostras: {t['amostras']}\n"
            f"RPM Max: {t['rpm_max']:.0f} rpm  |  Vel Max: {t['vel_max']:.0f} km/h\n\n"
            f"1. DETONACAO / SENSOR KNOCK\n{det_k}\n\n"
            f"2. SISTEMA DE ARREFECIMENTO\n{det_ect}\n\n"
            f"3. SONDA LAMBDA PRE-CAT & MISTURA\n{det_mist}\n\n"
            f"4. VACUO COLETOR & MARCHA LENTA (IAC)\n{det_lenta}\n\n"
            f"5. BATERIA & ALTERNADOR\n{det_bat}\n\n"
            f"6. SISTEMA DE INJECAO & CUT-OFF\n{det_inj}\n\n"
            f"7. IGNICAO & AVANCO\n{det_ign}"
        )
    def atualizar_tela_boletim(self):
        if hasattr(self, "lbl_boletim"):
            self.lbl_boletim.text = self.gerar_texto_boletim()

    def salvar_boletim_txt(self, *args):
        try:
            pasta = self._obter_pasta_gravacao()
            nome_arq = os.path.join(pasta, f"BOLETIM_TR4_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            texto = self.gerar_texto_boletim()
            with open(nome_arq, "w", encoding="utf-8") as f:
                f.write(f"Gerado em: {datetime.now()}\n\n" + texto)
            if hasattr(self, "lbl_boletim"):
                self.lbl_boletim.text = f"BOLETIM SALVO EM:\n{nome_arq}\n\n" + texto
            if hasattr(self, "lbl_eng"):
                self.lbl_eng.text = f"Boletim salvo com sucesso em:\n{nome_arq}"
        except Exception as e:
            if hasattr(self, "lbl_boletim"):
                self.lbl_boletim.text = f"Erro ao salvar boletim: {e}"

    def _caminho_config_bt(self):
        base = "."
        try:
            cand = getattr(self, "user_data_dir", ".")
            if cand:
                os.makedirs(cand, exist_ok=True)
                base = cand
        except Exception:
            base = "."
        return os.path.join(base, "bt_config.json")

    def _carregar_bt_salvo(self):
        try:
            arq = self._caminho_config_bt()
            if os.path.exists(arq):
                with open(arq, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                self.bt_salvo_addr = str(dados.get("addr", "")).strip()
                self.bt_salvo_nome = str(dados.get("nome", "")).strip()
        except Exception:
            self.bt_salvo_addr = ""
            self.bt_salvo_nome = ""

    def _salvar_bt_salvo(self, addr, nome):
        self.bt_salvo_addr = str(addr or "").strip()
        self.bt_salvo_nome = str(nome or "").strip()
        try:
            with open(self._caminho_config_bt(), "w", encoding="utf-8") as f:
                json.dump({"addr": self.bt_salvo_addr, "nome": self.bt_salvo_nome}, f)
        except Exception:
            pass

    def _atualizar_estado_conexao(self, novo_estado):
        self.estado_conexao = novo_estado
        if hasattr(self, "btn_bt_lista"):
            self.btn_bt_lista.text = "TROCAR\nBLUETOOTH" if self.bt_salvo_addr else "ESCOLHER\nBLUETOOTH"

        if not hasattr(self, "btn_acao_con"):
            return

        if novo_estado == "CONECTANDO":
            self.btn_acao_con.text = "CANCELAR\nCONEXAO"
            self.btn_acao_con.background_color = (0.85, 0.52, 0.12, 1)
        elif novo_estado in ("CONECTADO", "SIMULACAO"):
            self.btn_acao_con.text = "DESCONECTAR"
            self.btn_acao_con.background_color = (0.78, 0.22, 0.22, 1)
        else:
            nome_curto = self.bt_salvo_nome[:14] if self.bt_salvo_nome else ""
            self.btn_acao_con.text = f"CONECTAR\n({nome_curto})" if nome_curto else "CONECTAR"
            self.btn_acao_con.background_color = (0.14, 0.62, 0.35, 1)

    def acao_botao_conexao(self, *args):
        estado = getattr(self, "estado_conexao", "DESCONECTADO")
        if estado == "CONECTANDO":
            self.cancelar_tentativa_conexao()
        elif estado in ("CONECTADO", "SIMULACAO"):
            self.desconectar_ecu()
        else:
            if self.bt_salvo_addr:
                self._iniciar_conexao_completa(self.bt_salvo_addr, self.bt_salvo_nome or self.bt_salvo_addr)
            else:
                self.conectar_bluetooth()

    def cancelar_tentativa_conexao(self):
        self.cancelar_conexao = True
        self._con_seq = getattr(self, "_con_seq", 0) + 1
        self._fechar_socket_bt()
        self._atualizar_estado_conexao("DESCONECTADO")
        self._atualizar_status("CONEXAO CANCELADA PELO USUARIO", (1.0, 0.78, 0.2, 1))

    def _fechar_socket_bt(self):
        sock = getattr(self, "bt_socket", None)
        self.bt_socket = None
        self.bt_in = None
        self.bt_out = None
        if sock:
            try:
                sock.close()
            except Exception:
                pass

    def iniciar_simulacao(self, *args):
        self._init_telemetria_viagem()
        self.desconectar_ecu()
        self._init_telemetria_viagem()
        self.modo_simulacao = True
        self.rodando = True
        self._atualizar_estado_conexao("SIMULACAO")
        self._atualizar_status("SIMULACAO ATIVA | ECU: IAW 4AM.AR", (0.3, 0.9, 0.5, 1))
        threading.Thread(target=self.loop_leitura, daemon=True).start()

    def _pedir_permissoes_android(self):
        try:
            from android.permissions import request_permissions, Permission
            perms = [
                Permission.BLUETOOTH,
                Permission.BLUETOOTH_ADMIN,
                Permission.WRITE_EXTERNAL_STORAGE,
                Permission.READ_EXTERNAL_STORAGE,
                "android.permission.BLUETOOTH_CONNECT",
                "android.permission.BLUETOOTH_SCAN",
            ]
            request_permissions(perms)
        except Exception:
            pass

    def conectar_bluetooth(self, *args):
        if getattr(self, "estado_conexao", "") == "CONECTANDO":
            self.cancelar_tentativa_conexao()
            return
        try:
            from jnius import autoclass
            BluetoothAdapter = autoclass("android.bluetooth.BluetoothAdapter")
            adapter = BluetoothAdapter.getDefaultAdapter()
            if not adapter or not adapter.isEnabled():
                self._atualizar_status("ERRO: LIGUE O BLUETOOTH DO CELULAR", (1.0, 0.35, 0.35, 1))
                return
            pareados = list(adapter.getBondedDevices().toArray())
            if not pareados:
                self._atualizar_status("NENHUM DISPOSITIVO PAREADO NO ANDROID", (1.0, 0.35, 0.35, 1))
                return
            self._abrir_seletor_bt(pareados)
        except Exception as e:
            err = str(e)
            if "BLUETOOTH_CONNECT" in err or "SecurityException" in err:
                self._pedir_permissoes_android()
                self._atualizar_status("PERMISSAO SOLICITADA - ABRINDO LISTA...", (1.0, 0.78, 0.2, 1))
                Clock.schedule_once(lambda dt: self.conectar_bluetooth(), 1.2)
            else:
                self._atualizar_status(f"ERRO BT: {err[:42]}", (1.0, 0.35, 0.35, 1))

    def _abrir_seletor_bt(self, pareados):
        if getattr(self, "_popup_bt", None):
            try:
                self._popup_bt.dismiss()
            except Exception:
                pass
        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        box.add_widget(
            Label(
                text="Toque no scanner para conectar agora:",
                size_hint_y=0.10,
                bold=True,
                font_size="14sp",
            )
        )
        scroll = ScrollView(size_hint_y=0.78, bar_width=dp(6))
        lista = GridLayout(cols=1, spacing=dp(12), size_hint_y=None, padding=(dp(4), dp(6)))
        lista.bind(minimum_height=lista.setter("height"))
        popup = Popup(title="Selecionar Scanner Bluetooth", content=box, size_hint=(0.95, 0.85))
        self._popup_bt = popup

        for dev in pareados:
            addr = str(dev.getAddress() or "").strip()
            nome = str(dev.getName() or "").strip() or addr or "Dispositivo Sem Nome"
            eh_salvo = (addr and addr == self.bt_salvo_addr)
            rotulo = f"{nome}  [SALVO]" if eh_salvo else nome
            cor_btn = (0.14, 0.58, 0.38, 1) if eh_salvo else (0.14, 0.42, 0.68, 1)
            btn = Button(
                text=rotulo,
                size_hint_y=None,
                height=dp(64),
                font_size="16sp",
                bold=True,
                background_normal="",
                background_color=cor_btn,
            )
            btn.bind(on_release=lambda inst, a=addr, n=nome, p=popup: self._ao_escolher_dispositivo_bt(a, n, p))
            lista.add_widget(btn)

        scroll.add_widget(lista)
        box.add_widget(scroll)
        btn_fechar = Button(
            text="CANCELAR",
            size_hint_y=0.12,
            font_size="14sp",
            background_normal="",
            background_color=(0.75, 0.22, 0.22, 1),
            bold=True,
        )
        btn_fechar.bind(on_release=popup.dismiss)
        box.add_widget(btn_fechar)
        popup.open()

    def _ao_escolher_dispositivo_bt(self, addr, nome, popup):
        self._popup_bt = None
        try:
            popup.dismiss()
        except Exception:
            pass
        self._salvar_bt_salvo(addr, nome)
        self._iniciar_conexao_completa(addr, nome)
    def _iniciar_conexao_completa(self, addr, nome_dev):
        if self.rodando or self.modo_simulacao:
            self.desconectar_ecu()
        self.cancelar_conexao = False
        self._bt_io_erro = False
        self._con_seq = getattr(self, "_con_seq", 0) + 1
        seq = self._con_seq
        self._atualizar_estado_conexao("CONECTANDO")
        self._atualizar_status(f"CONECTANDO BT ({nome_dev})...", (1.0, 0.78, 0.2, 1))
        threading.Thread(
            target=self._conectar_tudo_thread,
            args=(seq, addr, nome_dev),
            daemon=True,
        ).start()

    def _abortado(self, seq):
        return getattr(self, "cancelar_conexao", False) or seq != getattr(self, "_con_seq", 0)

    def _conectar_tudo_thread(self, seq, addr, nome_dev):
        log_hs = []
        try:
            from jnius import autoclass
            BluetoothAdapter = autoclass("android.bluetooth.BluetoothAdapter")
            UUID = autoclass("java.util.UUID")

            adapter = BluetoothAdapter.getDefaultAdapter()
            if not adapter or not adapter.isEnabled():
                if not self._abortado(seq):
                    Clock.schedule_once(lambda dt: self._falha_conexao("ERRO: LIGUE O BLUETOOTH DO CELULAR", []))
                return

            self._fechar_socket_bt()
            if self._abortado(seq):
                return

            dispositivo_alvo = adapter.getRemoteDevice(addr)
            spp_uuid = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
            sock = dispositivo_alvo.createRfcommSocketToServiceRecord(spp_uuid)
            self.bt_socket = sock
            adapter.cancelDiscovery()
            sock.connect()

            if self._abortado(seq):
                self._fechar_socket_bt()
                return

            self.bt_in = sock.getInputStream()
            self.bt_out = sock.getOutputStream()
            self._bt_io_erro = False

            Clock.schedule_once(
                lambda dt: self._atualizar_status(f"BT OK ({nome_dev}) | INICIANDO K-LINE ECU...", (1.0, 0.78, 0.2, 1))
            )

            self._limpar_buffer_bt()
            r_atz = self.enviar_comando_raw("ATZ", timeout=2.5)
            log_hs.append(f"Reset Scanner: {r_atz or 'SEM RESPOSTA'}")
            if self._abortado(seq):
                return
            if not r_atz:
                Clock.schedule_once(lambda dt: self._falha_conexao("SCANNER NAO RESPONDEU", log_hs))
                return

            setup_cmds = ["ATE0", "ATL0", "ATS0", "ATH0", "ATAT1", "ATST32", "ATSP5", "ATSH8110F1", "ATWM8110F13E"]
            for cmd in setup_cmds:
                if self._abortado(seq):
                    return
                self.enviar_comando_raw(cmd, timeout=0.9)

            Clock.schedule_once(
                lambda dt: self._atualizar_status("SINCRONIZANDO BARRAMENTO K-LINE...", (1.0, 0.78, 0.2, 1))
            )
            r_init = self.enviar_comando_raw("ATFI", timeout=3.5)
            log_hs.append(f"Fast Init: {r_init or 'TIMEOUT'}")
            if self._abortado(seq):
                return

            if "OK" not in r_init.upper():
                self.enviar_comando_raw("ATSP4", timeout=1.0)
                self.enviar_comando_raw("ATSH8110F1", timeout=1.0)
                r_init = self.enviar_comando_raw("ATSI", timeout=4.5)
                log_hs.append(f"Slow Init: {r_init or 'TIMEOUT'}")
                if self._abortado(seq):
                    return

            r_sess = self.enviar_comando_raw("1081", timeout=2.0)
            log_hs.append(f"Sessao KWP: {r_sess or 'TIMEOUT'}")
            r_map = self.enviar_comando_raw("2131", timeout=1.8)
            log_hs.append(f"Teste MAP: {r_map or 'TIMEOUT'}")
            if self._abortado(seq):
                return

            limpo_map = "".join(c for c in r_map.upper() if c in "0123456789ABCDEF")
            limpo_sess = "".join(c for c in r_sess.upper() if c in "0123456789ABCDEF")
            conectou_real = ("5081" in limpo_sess) or ("6131" in limpo_map)

            if not conectou_real:
                Clock.schedule_once(
                    lambda dt: self._falha_conexao("ECU NAO RESPONDEU (CHAVE LIGADA?)", log_hs)
                )
                return

            self._init_telemetria_viagem()
            self._calib_arquivo_atual = ""
            self._calib_etapas_feitas = []
            self.modo_simulacao = False
            self.rodando = True
            Clock.schedule_once(lambda dt: self._sucesso_conexao(nome_dev))
            self.loop_leitura()
        except Exception as e:
            if self._abortado(seq):
                return
            self.rodando = False
            self._fechar_socket_bt()
            log_hs.append(f"Erro: {e}")
            Clock.schedule_once(
                lambda dt, err=str(e): self._falha_conexao(f"FALHA CONEXAO: {err[:34]}", log_hs)
            )
    def _sucesso_conexao(self, nome_dev):
        self._atualizar_estado_conexao("CONECTADO")
        self._atualizar_status(f"ECU CONECTADA ({nome_dev}) | K-LINE ATIVO", (0.2, 0.95, 0.45, 1))
        if hasattr(self, "lbl_eng"):
            self.lbl_eng.text = (
                "ECU conectada com sucesso!\n\n"
                "Para calibrar 100% dos PIDs, toque em CAPTURAR CALIBRACAO nos 4 estados:\n"
                "1) Chave ligada, motor frio desligado\n"
                "2) Marcha lenta quente (80-94 C)\n"
                "3) Ventoinha armada (~97 C)\n"
                "4) Cut-off (>2200 RPM, pe fora do pedal)"
            )

    def _falha_conexao(self, titulo, log_hs):
        self.rodando = False
        self._fechar_socket_bt()
        self._atualizar_estado_conexao("DESCONECTADO")
        self._atualizar_status(titulo, (1.0, 0.30, 0.30, 1))
        if hasattr(self, "lbl_eng") and log_hs:
            detalhes = "\n".join(log_hs[-6:])
            self.lbl_eng.text = f"{titulo}\n\n{detalhes}"

    def _tratar_perda_conexao(self, motivo):
        if getattr(self, "estado_conexao", "") == "DESCONECTADO":
            return
        self.rodando = False
        self.varrendo = False
        self.modo_simulacao = False
        if getattr(self, "gravando_log", False):
            self.parar_gravacao_log()
        self._fechar_socket_bt()
        self.valores_atuais = {p["id"]: "--" for p in PIDS_DB}
        self.atualizar_interface(0)
        self._atualizar_estado_conexao("DESCONECTADO")
        self._atualizar_status(motivo, (1.0, 0.28, 0.28, 1))
        if hasattr(self, "lbl_eng"):
            self.lbl_eng.text = f"{motivo}\n\nLigue a chave do veiculo e toque em CONECTAR para reconectar."
        self.atualizar_tela_boletim()

    def _atualizar_status(self, texto, cor):
        if hasattr(self, "lbl_status"):
            self.lbl_status.text = texto
            self.lbl_status.color = cor

    def _limpar_buffer_bt(self):
        try:
            while self.bt_in and self.bt_in.available() > 0:
                self.bt_in.read()
        except Exception:
            pass

    def enviar_comando_raw(self, cmd, timeout=0.8):
        if not self.bt_out or not self.bt_in:
            self._bt_io_erro = True
            return ""
        lock = getattr(self, "bt_lock", None)
        if lock:
            lock.acquire()
        try:
            self._limpar_buffer_bt()
            self.bt_out.write((cmd + "\r").encode("ascii"))
            self.bt_out.flush()
            resposta = bytearray()
            t_limite = time.time() + timeout
            while time.time() < t_limite:
                if self.bt_in.available() > 0:
                    b = self.bt_in.read()
                    if b < 0:
                        self._bt_io_erro = True
                        break
                    if b == 62:
                        break
                    resposta.append(b)
                else:
                    time.sleep(0.004)
            return resposta.decode("ascii", errors="ignore").replace("\r", " ").replace("\n", " ").strip()
        except Exception:
            self._bt_io_erro = True
            return ""
        finally:
            if lock:
                lock.release()

    def parse_bytes_kwp(self, resp_str, cmd_enviado):
        limpo = "".join(c for c in resp_str.upper() if c in "0123456789ABCDEF")
        try:
            srv_req = int(cmd_enviado[:2], 16)
            srv_ok = f"{(srv_req + 0x40):02X}"
        except Exception:
            srv_ok = "61"
        prefixo_ok = srv_ok + cmd_enviado[2:4].upper()
        idx = limpo.find(prefixo_ok)
        if idx == -1:
            return []
        dados_hex = limpo[idx + 4:]
        return [int(dados_hex[i:i + 2], 16) for i in range(0, len(dados_hex) - 1, 2)]

    def _registrar_valor(self, pid_id, valor):
        if valor is None:
            return
        self.valores_atuais[pid_id] = valor
        if isinstance(valor, (int, float)):
            if pid_id not in self.valores_min or valor < self.valores_min[pid_id]:
                self.valores_min[pid_id] = valor
            if pid_id not in self.valores_max or valor > self.valores_max[pid_id]:
                self.valores_max[pid_id] = valor

    def zerar_min_max(self, *args):
        self.valores_min = {}
        self.valores_max = {}
        for pid_id, val in self.valores_atuais.items():
            if isinstance(val, (int, float)):
                self.valores_min[pid_id] = val
                self.valores_max[pid_id] = val
        self.atualizar_interface(0)

    def loop_leitura(self):
        t0 = time.time()
        ciclo = 0
        ciclos_sem_resposta = 0
        while self.rodando:
            ciclo += 1
            t_atual = time.time() - t0
            cache_comandos = {}
            gravando_ativo = self.gravando_log and not getattr(self, "log_pausado", False)
            log_ativos = getattr(self, "selecionados_log", {}) if gravando_ativo else {}
            ler_bg_agora = (ciclo % 3 == 1)
            comandos_tentados = 0
            comandos_validos = 0

            for pid in PIDS_DB:
                if not self.rodando:
                    break
                pid_id = pid["id"]
                ativo_ui = self.selecionados.get(pid_id, False) or log_ativos.get(pid_id, False)
                ativo_bg = (pid_id in ("LAMBDA_1", "RPM", "TPS", "MAP")) or (ler_bg_agora and (pid_id in PIDS_VIGILANCIA_BG))
                if not (ativo_ui or ativo_bg):
                    continue
                if self.modo_simulacao:
                    valor = pid["sim"](t_atual)
                    comandos_validos += 1
                else:
                    cmd = pid["cmd"]
                    if cmd not in cache_comandos:
                        comandos_tentados += 1
                        raw = self.enviar_comando_raw(cmd, timeout=0.75)
                        parsed = self.parse_bytes_kwp(raw, cmd)
                        cache_comandos[cmd] = parsed
                        if parsed:
                            comandos_validos += 1
                    bytes_resp = cache_comandos[cmd]
                    if not bytes_resp:
                        continue
                    valor = pid["calc"](bytes_resp)
                self._registrar_valor(pid_id, valor)

            if not self.rodando:
                break

            if not self.modo_simulacao:
                if getattr(self, "_bt_io_erro", False):
                    self.rodando = False
                    Clock.schedule_once(lambda dt: self._tratar_perda_conexao("CONEXAO BLUETOOTH PERDIDA"))
                    break

                if comandos_tentados == 0:
                    comandos_tentados = 1
                    raw_hb = self.enviar_comando_raw("21A2", timeout=0.75)
                    if self.parse_bytes_kwp(raw_hb, "21A2"):
                        comandos_validos = 1

                if comandos_validos == 0:
                    ciclos_sem_resposta += 1
                    if ciclos_sem_resposta >= 4:
                        self.rodando = False
                        Clock.schedule_once(
                            lambda dt: self._tratar_perda_conexao("ECU DESCONECTADA (CHAVE DESLIGADA / SEM RESPOSTA)")
                        )
                        break
                    time.sleep(0.15)
                    continue
                else:
                    ciclos_sem_resposta = 0

            self._processar_amostra_telemetria()

            if gravando_ativo and self.writer_log and hasattr(self, "pids_gravando_lista"):
                try:
                    linha = [round(time.time() - self.inicio_log_ts, 2)] + [
                        self.valores_atuais.get(pid_id, "") for pid_id in self.pids_gravando_lista
                    ]
                    self.writer_log.writerow(linha)
                    self.arquivo_log.flush()
                    self.linhas_gravadas_log = getattr(self, "linhas_gravadas_log", 0) + 1
                except Exception:
                    pass
            Clock.schedule_once(self.atualizar_interface)
            time.sleep(0.08 if self.modo_simulacao else 0.01)

    def atualizar_interface(self, dt):
        if not hasattr(self, "tel"):
            self._init_telemetria_viagem()
        for pid_id, widgets in self.cards_ui.items():
            lbl_val, lbl_min, lbl_max, unidade = widgets
            val = self.valores_atuais.get(pid_id, "--")
            lbl_val.text = f"{val} {unidade}" if val != "--" else "--"
            vmin = self.valores_min.get(pid_id, "--")
            vmax = self.valores_max.get(pid_id, "--")
            lbl_min.text = f"MIN: {vmin}"
            lbl_max.text = f"MAX: {vmax}"

        if hasattr(self, "graficos_lista") and hasattr(self, "pids_graf"):
            for idx, graf in enumerate(self.graficos_lista):
                val = self.valores_atuais.get(itemgetter(idx)(self.pids_graf))
                if isinstance(val, (int, float)):
                    graf.adicionar_ponto(val)

        # Atualizacao ao vivo do indicador de Log CSV
        rec_tag = ""
        if getattr(self, "gravando_log", False):
            qtd = getattr(self, "linhas_gravadas_log", 0)
            dur_log = max(0, int(time.time() - getattr(self, "inicio_log_ts", time.time())))
            mm, ss = divmod(dur_log, 60)
            if getattr(self, "log_pausado", False):
                rec_tag = f" | LOG PAUSADO ({mm:02d}:{ss:02d})"
                if hasattr(self, "lbl_log_status_bar"):
                    self.lbl_log_status_bar.text = f"STATUS LOG: PAUSADO ({mm:02d}:{ss:02d}  |  {qtd} linhas)"
                    self.lbl_log_status_bar.color = (1.0, 0.78, 0.2, 1)
            else:
                rec_tag = f" | [REC {mm:02d}:{ss:02d} | {qtd}L]"
                if hasattr(self, "lbl_log_status_bar"):
                    self.lbl_log_status_bar.text = f"STATUS LOG: GRAVANDO ({mm:02d}:{ss:02d}  |  {qtd} linhas)"
                    self.lbl_log_status_bar.color = (0.25, 0.95, 0.45, 1)

        alerta = self.tel.get("alerta_critico_atual", "")
        if alerta and self.estado_conexao in ("CONECTADO", "SIMULACAO"):
            self._atualizar_status(alerta + rec_tag, (1.0, 0.25, 0.25, 1))
        elif self.estado_conexao == "CONECTADO":
            self._atualizar_status(f"ECU CONECTADA | K-LINE ATIVO{rec_tag}", (0.2, 0.95, 0.45, 1))
        elif self.estado_conexao == "SIMULACAO":
            self._atualizar_status(f"SIMULACAO ATIVA | IAW 4AM{rec_tag}", (0.3, 0.9, 0.5, 1))

    def _obter_pasta_gravacao(self):
        pasta_dl = "/sdcard/Download"
        try:
            if os.path.exists(pasta_dl) and os.access(pasta_dl, os.W_OK):
                return pasta_dl
        except Exception:
            pass
        return getattr(self, "user_data_dir", ".")

    def iniciar_gravacao_log(self, *args):
        if not self.rodando:
            if hasattr(self, "lbl_log_info"):
                self.lbl_log_info.text = "Conecte a ECU ou Simulacao antes de iniciar o Log!"
            return
        if self.gravando_log:
            if getattr(self, "log_pausado", False):
                self.log_pausado = False
                if hasattr(self, "lbl_log_info"):
                    self.lbl_log_info.text = f"RETOMANDO GRAVACAO ({self.linhas_gravadas_log} linhas):\n{self.caminho_log_atual}"
            return
        try:
            sel_log = getattr(self, "selecionados_log", {})
            self.pids_gravando_lista = [p["id"] for p in PIDS_DB if sel_log.get(p["id"], False)]
            if not self.pids_gravando_lista:
                self.pids_gravando_lista = [p["id"] for p in PIDS_DB if p["rapido"]]
            pasta = self._obter_pasta_gravacao()
            nome_arq = os.path.join(pasta, f"TR4_IAW4AM_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            self.caminho_log_atual = nome_arq
            self.arquivo_log = open(nome_arq, "w", newline="", encoding="utf-8")
            self.writer_log = csv.writer(self.arquivo_log, delimiter=";")
            self.writer_log.writerow(["Tempo_s"] + self.pids_gravando_lista)
            self.arquivo_log.flush()
            self.inicio_log_ts = time.time()
            self.linhas_gravadas_log = 0
            self.log_pausado = False
            self.gravando_log = True
            if hasattr(self, "lbl_log_status_bar"):
                self.lbl_log_status_bar.text = "STATUS LOG: GRAVANDO (00:00  |  0 linhas)"
                self.lbl_log_status_bar.color = (0.25, 0.95, 0.45, 1)
            if hasattr(self, "lbl_log_info"):
                self.lbl_log_info.text = f"GRAVANDO ({len(self.pids_gravando_lista)} PIDs):\n{nome_arq}"
        except Exception as e:
            if hasattr(self, "lbl_log_info"):
                self.lbl_log_info.text = f"Erro ao criar CSV: {e}"

    def pausar_gravacao_log(self, *args):
        if not self.gravando_log:
            if hasattr(self, "lbl_log_info"):
                self.lbl_log_info.text = "Nenhum log ativo para pausar."
            return
        self.log_pausado = True
        if hasattr(self, "lbl_log_info"):
            qtd = getattr(self, "linhas_gravadas_log", 0)
            self.lbl_log_info.text = f"LOG PAUSADO ({qtd} linhas gravadas).\nClique em INICIAR / CONTINUAR para retomar."

    def parar_gravacao_log(self, *args):
        qtd = getattr(self, "linhas_gravadas_log", 0)
        arq = getattr(self, "caminho_log_atual", "")
        self.gravando_log = False
        self.log_pausado = False
        if self.arquivo_log:
            try:
                self.arquivo_log.flush()
                self.arquivo_log.close()
            except Exception:
                pass
            self.arquivo_log = None
            self.writer_log = None
        if hasattr(self, "lbl_log_status_bar"):
            self.lbl_log_status_bar.text = f"STATUS LOG: ENCERRADO ({qtd} linhas salvas)"
            self.lbl_log_status_bar.color = (0.75, 0.80, 0.88, 1)
        if hasattr(self, "lbl_log_info") and arq:
            self.lbl_log_info.text = f"LOG ENCERRADO E SALVO ({qtd} linhas):\n{arq}"
    def _classificar_estado_calibracao(self, b_a2, b_a6):
        if len(b_a2) >= 2:
            r0, r1 = itemgetter(0, 1)(b_a2)
            rpm = (r0 << 8) | r1
        else:
            rpm = 0

        if len(b_a2) >= 8:
            e0, e1 = itemgetter(6, 7)(b_a2)
            ect = ((e0 << 8) | e1) - 40
        else:
            ect = 0

        if len(b_a2) >= 10:
            t0, t1 = itemgetter(8, 9)(b_a2)
            tps_raw = (t0 << 8) | t1
        else:
            tps_raw = 0
        tps = max(0.0, ((tps_raw - 1.0) / 835.0) * 100.0)

        if len(b_a6) >= 4:
            v0, v1 = itemgetter(2, 3)(b_a6)
            vel = (v0 << 8) | v1
        else:
            vel = 0

        if rpm == 0:
            cod = "E1_CHAVE_LIGADA_MOTOR_PARADO"
            desc = f"ESTADO 1: Chave ligada / Motor parado (ECT={ect}C)"
        elif vel >= 10 and tps <= 1.5 and rpm >= 1800:
            cod = "E4_CUTOFF_DESACELERACAO"
            desc = f"ESTADO 4: Cut-off em desaceleracao (RPM={rpm}, VEL={vel}km/h, TPS={tps:.1f}%)"
        elif ect >= 95:
            cod = "E3_VENTOINHA_ALTA_TEMP"
            desc = f"ESTADO 3: Motor quente / Ventoinha (~{ect}C, RPM={rpm})"
        elif ect >= 78 and vel == 0 and tps <= 1.5:
            cod = "E2_LENTA_AQUECIDA"
            desc = f"ESTADO 2: Marcha lenta aquecida (ECT={ect}C, RPM={rpm})"
        else:
            cod = f"EXTRA_RPM{rpm}_ECT{ect}"
            desc = f"ESTADO EXTRA: RPM={rpm}, ECT={ect}C, VEL={vel}km/h, TPS={tps:.1f}%"
        return cod, desc

    def capturar_calibracao_ecu(self, *args):
        if self.modo_simulacao:
            self.lbl_eng.text = "Modo Simulacao ativo: conecte no carro para capturar bytes reais."
            return
        if not self.rodando or not self.bt_out or not self.bt_in:
            self.lbl_eng.text = "ECU desconectada! Clique em CONECTAR primeiro."
            return
        self.rodando = False
        self.lbl_eng.text = "Capturando Modo 01 + 3 amostras dos blocos Modo 21 (~3s)..."
        threading.Thread(target=self._capturar_calibracao_thread, daemon=True).start()

    def _capturar_calibracao_thread(self):
        time.sleep(0.25)
        b_a2 = self.parse_bytes_kwp(self.enviar_comando_raw("21A2", timeout=0.9), "21A2")
        b_a6 = self.parse_bytes_kwp(self.enviar_comando_raw("21A6", timeout=0.9), "21A6")
        cod_est, desc_est = self._classificar_estado_calibracao(b_a2, b_a6)

        pasta = self._obter_pasta_gravacao()
        arq_atual = getattr(self, "_calib_arquivo_atual", "")
        if not arq_atual:
            arq_atual = os.path.join(pasta, f"CALIBRACAO_IAW4AM_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            self._calib_arquivo_atual = arq_atual
            self._calib_etapas_feitas = []

        novo_arquivo = not os.path.exists(arq_atual)
        linhas = []
        if novo_arquivo:
            linhas.extend([
                f"CALIBRACAO ESTRUTURADA (4 ESTADOS + MODO 01) - ECU IAW 4AM ({datetime.now()})",
                "Configuracao veiculo: Pajero TR4 2.0 16V Flex (Sonda unica pre-catalisador)",
                "=" * 68,
            ])

        linhas.append(f"\n==================== {desc_est} [{datetime.now().strftime('%H:%M:%S')}] ====================")

        m01_ativos = []
        for cmd01, nome01 in CMDS_MODO_01_PROBE:
            resp01 = self.enviar_comando_raw(cmd01, timeout=0.7)
            b01 = self.parse_bytes_kwp(resp01, cmd01)
            if b01:
                hex01 = " ".join(f"{x:02X}" for x in b01)
                m01_ativos.append(f"  {cmd01} ({nome01}) -> {hex01}")
        if m01_ativos:
            linhas.append("[MODO 01 OBD2 ATIVOS]")
            linhas.extend(m01_ativos)
        else:
            linhas.append("[MODO 01 OBD2] Nenhum PID respondeu sob cabecalho KWP 8110F1")

        for amostra in range(1, 4):
            linhas.append(f"\n--- AMOSTRA {amostra}/3 ({datetime.now().strftime('%H:%M:%S')}) ---")
            for cmd in CMDS_MODO_21_VIVOS:
                resp = self.enviar_comando_raw(cmd, timeout=0.8)
                b_list = self.parse_bytes_kwp(resp, cmd)
                hex_fmt = " ".join(f"{x:02X}" for x in b_list) if b_list else f"RAW: {resp}"
                linhas.append(f"{cmd} -> {hex_fmt}")
            time.sleep(0.15)

        if cod_est not in self._calib_etapas_feitas:
            self._calib_etapas_feitas.append(cod_est)

        e1 = "OK" if "E1_CHAVE_LIGADA_MOTOR_PARADO" in self._calib_etapas_feitas else "PENDENTE"
        e2 = "OK" if "E2_LENTA_AQUECIDA" in self._calib_etapas_feitas else "PENDENTE"
        e3 = "OK" if "E3_VENTOINHA_ALTA_TEMP" in self._calib_etapas_feitas else "PENDENTE"
        e4 = "OK" if "E4_CUTOFF_DESACELERACAO" in self._calib_etapas_feitas else "PENDENTE"

        try:
            with open(arq_atual, "a", encoding="utf-8") as f:
                f.write("\n".join(linhas) + "\n")
            msg = (
                f"Capturado: {desc_est}\n"
                f"PIDs Modo 01 ativos: {len(m01_ativos)}\n\n"
                f"Progresso dos 4 Estados:\n"
                f"[{e1}] 1. Chave ligada / Motor parado\n"
                f"[{e2}] 2. Marcha lenta quente (80-94 C)\n"
                f"[{e3}] 3. Ventoinha ligada (~97 C)\n"
                f"[{e4}] 4. Cut-off (>2200 RPM, TPS 0%)\n\n"
                f"Arquivo unico:\n{arq_atual}"
            )
        except Exception as e:
            msg = f"Erro ao salvar calibracao: {e}"

        Clock.schedule_once(lambda dt, m=msg: setattr(self.lbl_eng, "text", m))
        if self.estado_conexao == "CONECTADO" and self.bt_socket:
            self.rodando = True
            self.loop_leitura()
    def ler_info_ecu(self, *args):
        if self.modo_simulacao:
            self.lbl_eng.text = (
                "Codigo Projeto ECU: CA130195\n\n"
                "Numero HW: IAW4AMHWM44  (Ver: 00)\n\n"
                "Numero SW: 0401BA83  (Ver: 0000)\n\n"
                "Homologacao: 4AMMS  |  ISO: 0000000000\n\n"
                "Data Programacao: 20/10/2009\n\n"
                "Reescritas Flash: 1  |  Odo Reescr: 0 km\n\n"
                "Odometro Real ECU: 69.456 km"
            )
            return
        if not self.rodando or not self.bt_out or not self.bt_in:
            self.lbl_eng.text = "ECU desconectada! Clique em CONECTAR primeiro."
            return
        self.rodando = False
        self.lbl_eng.text = "Lendo identificacao completa e odometro da ECU..."
        threading.Thread(target=self._ler_info_ecu_thread, daemon=True).start()

    def _ler_info_ecu_thread(self):
        def _ascii(b_list):
            return "".join(chr(x) if 32 <= x <= 126 else "" for x in b_list).strip()

        time.sleep(0.25)
        b80 = self.parse_bytes_kwp(self.enviar_comando_raw("2180", timeout=2.0), "2180")
        b71 = self.parse_bytes_kwp(self.enviar_comando_raw("2171", timeout=1.5), "2171")
        b72 = self.parse_bytes_kwp(self.enviar_comando_raw("2172", timeout=1.5), "2172")
        b73 = self.parse_bytes_kwp(self.enviar_comando_raw("2173", timeout=1.5), "2173")

        if len(b80) >= 61:
            desenho = _ascii(b80[0:11]) or "N/D"
            hw = _ascii(b80[11:22]) or "N/D"
            hw_v0 = itemgetter(22)(b80)
            hw_ver = f"{hw_v0:02X}"
            sw = _ascii(b80[23:34]) or "N/D"
            sw_v0, sw_v1 = itemgetter(34, 35)(b80)
            sw_ver = f"{sw_v0:02X}{sw_v1:02X}"
            homolog = _ascii(b80[36:42]) or "N/D"
            iso = "".join(f"{x:02X}" for x in b80[42:47])
            d_dia, d_mes, d_ano = itemgetter(60, 59, 58)(b80)
            data_prog = f"{d_dia:02X}/{d_mes:02X}/20{d_ano:02X}"
        else:
            desenho, hw, hw_ver, sw, sw_ver, homolog, iso, data_prog = ("N/D", "N/D", "00", "N/D", "0000", "N/D", "N/D", "N/D")

        odo_txt = "Nao disponivel"
        if len(b71) >= 3:
            b_o0, b_o1, b_o2 = itemgetter(0, 1, 2)(b71)
            km_val = (b_o0 << 16) | (b_o1 << 8) | b_o2
            odo_txt = f"{km_val:,} km".replace(",", ".")

        reescr = 0
        if len(b72) >= 2:
            r0, r1 = itemgetter(0, 1)(b72)
            reescr = (r0 << 8) | r1

        odo_reescr = 0
        if len(b73) >= 3:
            or0, or1, or2 = itemgetter(0, 1, 2)(b73)
            odo_reescr = (or0 << 16) | (or1 << 8) | or2

        texto = (
            f"Codigo Projeto ECU: {desenho}\n\n"
            f"Numero HW: {hw}  (Ver: {hw_ver})\n\n"
            f"Numero SW: {sw}  (Ver: {sw_ver})\n\n"
            f"Homologacao: {homolog}  |  ISO: {iso}\n\n"
            f"Data Programacao: {data_prog}\n\n"
            f"Reescritas Flash: {reescr}  |  Odo Reescr: {odo_reescr} km\n\n"
            f"Odometro Real ECU: {odo_txt}"
        )
        Clock.schedule_once(lambda dt: setattr(self.lbl_eng, "text", texto))
        if self.estado_conexao == "CONECTADO" and self.bt_socket:
            self.rodando = True
            self.loop_leitura()

    def ler_dtcs(self, *args):
        if self.modo_simulacao:
            self.lbl_eng.text = "Nenhuma falha armazenada na ECU."
            return
        if not self.rodando or not self.bt_out or not self.bt_in:
            self.lbl_eng.text = "ECU desconectada! Clique em CONECTAR primeiro."
            return
        self.rodando = False
        self.lbl_eng.text = "Consultando memoria de falhas (DTC)..."
        threading.Thread(target=self._ler_dtcs_thread, daemon=True).start()

    def _ler_dtcs_thread(self):
        time.sleep(0.25)
        resp = self.enviar_comando_raw("1800FF00", timeout=2.0)
        limpo = "".join(c for c in resp.upper() if c in "0123456789ABCDEF")
        idx = limpo.find("58")
        if idx != -1:
            qtd = int(limpo[idx + 2:idx + 4], 16) if len(limpo) >= idx + 4 else 0
            if qtd == 0:
                msg = "Nenhuma falha ativa ou pendente na ECU."
            else:
                dados = limpo[idx + 4:]
                cods = []
                prefixos = {"0": "P0", "1": "P1", "2": "P2", "3": "P3", "4": "C0", "8": "B0", "C": "U0"}
                for i in range(0, len(dados) - 5, 6):
                    dtc_hex = dados[i:i + 4]
                    p_letra = prefixos.get(dtc_hex[:1], "P" + dtc_hex[:1])
                    cods.append(f"{p_letra}{dtc_hex[1:4]}")
                msg = f"Falhas encontradas ({qtd}):\n\n" + (", ".join(cods) if cods else dados)
        else:
            msg = f"Retorno da ECU:\n{resp if resp else 'Sem resposta'}"
        Clock.schedule_once(lambda dt: setattr(self.lbl_eng, "text", msg))
        if self.estado_conexao == "CONECTADO" and self.bt_socket:
            self.rodando = True
            self.loop_leitura()
    def apagar_dtcs(self, *args):
        if self.modo_simulacao:
            self.lbl_eng.text = "Memoria de falhas limpa!"
            return
        if not self.rodando or not self.bt_out or not self.bt_in:
            self.lbl_eng.text = "ECU desconectada! Clique em CONECTAR primeiro."
            return
        self.rodando = False
        threading.Thread(target=self._apagar_dtcs_thread, daemon=True).start()

    def _apagar_dtcs_thread(self):
        time.sleep(0.25)
        resp = self.enviar_comando_raw("14FF00", timeout=2.0)
        msg = "Falhas apagadas com sucesso!" if "54" in resp.upper() else f"Comando enviado ({resp})"
        Clock.schedule_once(lambda dt: setattr(self.lbl_eng, "text", msg))
        if self.estado_conexao == "CONECTADO" and self.bt_socket:
            self.rodando = True
            self.loop_leitura()

    def buscar_modulos_kwp(self, *args):
        if self.modo_simulacao:
            self.lbl_eng.text = "Simulacao:\n[0x10] Injecao Motor (IAW 4AM) - ATIVO\n[0x18] Cambio AT - Sem resposta"
            return
        if not self.bt_socket or not self.bt_out or not self.bt_in:
            self.lbl_eng.text = "Conecte o scanner primeiro!"
            return
        self.rodando = False
        self.lbl_eng.text = "Encerrando sessao atual e buscando modulos no Pino 7...\n\nAguarde ~20 segundos..."
        threading.Thread(target=self._buscar_modulos_thread, daemon=True).start()

    def _buscar_modulos_thread(self):
        time.sleep(0.35)
        self.enviar_comando_raw("82", timeout=1.0)
        self.enviar_comando_raw("ATPC", timeout=0.8)
        time.sleep(0.4)

        alvos = [
            ("10", "Injecao Eletronica (ECU)"),
            ("11", "Motor / Coprocessador"),
            ("18", "Transmissao Automatica (TCU)"),
            ("28", "Freios ABS / Tracao"),
            ("40", "Carroceria / BCM"),
            ("58", "Airbag (SRS)"),
            ("60", "Painel / Imobilizador"),
        ]
        resultados = []
        for addr, nome in alvos:
            if self.estado_conexao != "CONECTADO":
                return
            msg_step = f"Testando endereco 0x{addr} ({nome})..."
            Clock.schedule_once(lambda dt, m=msg_step: setattr(self.lbl_eng, "text", m))
            self.enviar_comando_raw("ATSP5", timeout=0.8)
            self.enviar_comando_raw("ATST64", timeout=0.8)
            self.enviar_comando_raw(f"ATSH81{addr}F1", timeout=0.8)
            self.enviar_comando_raw(f"ATWM81{addr}F13E", timeout=0.8)
            r_fi = self.enviar_comando_raw("ATFI", timeout=2.5)
            r_ses = self.enviar_comando_raw("1081", timeout=1.5)
            limpo = "".join(c for c in (r_fi + r_ses).upper() if c in "0123456789ABCDEF")
            if "OK" in r_fi.upper() or "5081" in limpo or "C1" in limpo:
                resultados.append(f"[0x{addr}] {nome}: RESPONDEU!")
                self.enviar_comando_raw("82", timeout=0.8)
            else:
                resultados.append(f"[0x{addr}] {nome}: Sem resposta")
            self.enviar_comando_raw("ATPC", timeout=0.8)
            time.sleep(0.35)

        if self.estado_conexao != "CONECTADO":
            return
        self.enviar_comando_raw("ATSP5", timeout=0.8)
        self.enviar_comando_raw("ATST64", timeout=0.8)
        self.enviar_comando_raw("ATSH8110F1", timeout=0.8)
        self.enviar_comando_raw("ATWM8110F13E", timeout=0.8)
        self.enviar_comando_raw("ATFI", timeout=2.5)
        self.enviar_comando_raw("1081", timeout=1.5)

        texto_final = "Resultado da Busca de Modulos (Pino 7):\n\n" + "\n".join(resultados)
        Clock.schedule_once(lambda dt, t=texto_final: setattr(self.lbl_eng, "text", t))
        if self.estado_conexao == "CONECTADO" and self.bt_socket:
            self.rodando = True
            self.loop_leitura()

    def desconectar_ecu(self, *args):
        self.cancelar_conexao = True
        self._con_seq = getattr(self, "_con_seq", 0) + 1
        estava_conectado = (getattr(self, "estado_conexao", "") == "CONECTADO")
        self.rodando = False
        self.varrendo = False
        self.modo_simulacao = False
        self.parar_gravacao_log()

        if estava_conectado and self.bt_out and self.bt_in:
            try:
                self.enviar_comando_raw("82", timeout=0.5)
                self.enviar_comando_raw("ATPC", timeout=0.4)
            except Exception:
                pass

        self._fechar_socket_bt()
        self.valores_atuais = {p["id"]: "--" for p in PIDS_DB}
        self.valores_min = {}
        self.valores_max = {}
        self.atualizar_interface(0)
        self._atualizar_estado_conexao("DESCONECTADO")
        if hasattr(self, "lbl_eng"):
            self.lbl_eng.text = "Desconectado."
        self._atualizar_status("DESCONECTADO | ECU: IAW 4AM.AR (4AMMS)", (1, 0.78, 0.2, 1))

    def iniciar_varredura_ecu(self, *args):
        if getattr(self, "varrendo", False):
            return
        if self.modo_simulacao:
            self.lbl_eng.text = "Simulacao: 2131, 213B, 2147 ativos."
            return
        if not self.rodando or not self.bt_out or not self.bt_in:
            self.lbl_eng.text = "ECU desconectada! Clique em CONECTAR primeiro."
            return
        self.rodando = False
        self.varrendo = True
        self.lbl_eng.text = "Iniciando varredura completa da ECU..."
        threading.Thread(target=self._executar_varredura_thread, daemon=True).start()

    def parar_varredura_ecu(self, *args):
        if getattr(self, "varrendo", False):
            self.varrendo = False
            self.lbl_eng.text = "Parando varredura e salvando parcial..."

    def _executar_varredura_thread(self):
        time.sleep(0.35)
        pasta = self._obter_pasta_gravacao()
        nome_arq = os.path.join(pasta, f"MAPA_IAW4AM_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        encontrados = []
        for code in range(0x00, 0x100):
            if not getattr(self, "varrendo", False):
                break
            cmd = f"21{code:02X}"
            if code % 8 == 0:
                msg_prog = f"Varrendo endereco {cmd} de 21FF...\n\nPIDs ativos encontrados: {len(encontrados)}"
                Clock.schedule_once(lambda dt, m=msg_prog: setattr(self.lbl_eng, "text", m))
            resp = self.enviar_comando_raw(cmd, timeout=0.9)
            limpo = "".join(c for c in resp.upper() if c in "0123456789ABCDEF")
            prefixo_ok = f"61{code:02X}"
            idx = limpo.find(prefixo_ok)
            if idx != -1:
                dados = limpo[idx + 4:]
                pares = " ".join(dados[i:i + 2] for i in range(0, len(dados) - 1, 2))
                encontrados.append(f"{cmd} -> {pares}")

        self.varrendo = False
        try:
            with open(nome_arq, "w", encoding="utf-8") as f:
                f.write(f"MAPA DE PIDS ATIVOS - ECU IAW 4AM ({datetime.now()})\n")
                f.write(f"Total encontrados: {len(encontrados)}\n" + "=" * 45 + "\n")
                f.write("\n".join(encontrados))
            resumo = f"Salvo em:\n{nome_arq}"
        except Exception as e:
            resumo = f"Erro ao salvar arquivo: {e}"

        msg_fim = f"Varredura finalizada!\n\nTotal encontrados: {len(encontrados)}\n\n{resumo}"
        Clock.schedule_once(lambda dt, m=msg_fim: setattr(self.lbl_eng, "text", m))
        if self.estado_conexao == "CONECTADO" and self.bt_socket:
            self.rodando = True
            self.loop_leitura()
