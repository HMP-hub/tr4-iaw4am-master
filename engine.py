# coding: utf-8
import os
import re
import csv
import json
import time
import threading
from datetime import datetime
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from pids import PIDS_DB, PIDS_VIGILANCIA_BG

class TR4EngineMixin:
    def _manter_tela_acesa(self, ativar):
        try:
            from jnius import autoclass
            from android.runnable import run_on_ui_thread
            @run_on_ui_thread
            def _aplicar_flag():
                try:
                    activity = autoclass("org.kivy.android.PythonActivity").mActivity
                    win = activity.getWindow()
                    if ativar: win.addFlags(autoclass("android.view.WindowManager$LayoutParams").FLAG_KEEP_SCREEN_ON)
                    else: win.clearFlags(autoclass("android.view.WindowManager$LayoutParams").FLAG_KEEP_SCREEN_ON)
                except Exception: pass
            _aplicar_flag()
        except Exception: pass

    def _init_telemetria_viagem(self):
        self.tel = {
            "inicio_ts": time.time(), "amostras": 0, "amostras_mov": 0,
            "vel_max": 0.0, "rpm_max": 0.0, "ect_ini": None, "ect_max": None,
            "tempo_para_80c": None, "tempo_acima_98c": 0.0, "ultimo_ts": None,
            "knock_eventos": 0, "knock_sensor_max_v": 0.0, "knock_pior_graus": 0.0,
        }

    def reiniciar_telemetria_viagem(self, *args):
        self._init_telemetria_viagem()
        if hasattr(self, "lbl_boletim"):
            self.lbl_boletim.text = "[b][color=#55bbff]Nova viagem iniciada! Telemetria zerada.[/color][/b]"

    def _processar_amostra_telemetria(self):
        if not hasattr(self, "tel"): self._init_telemetria_viagem()
        t = self.tel
        agora = time.time()
        t["ultimo_ts"] = agora
        t["amostras"] += 1
        rpm, vel, ect, kv = self.valores_atuais.get("RPM"), self.valores_atuais.get("VEL"), self.valores_atuais.get("ECT"), self.valores_atuais.get("KNOCK_SENSOR")
        if isinstance(vel, (int, float)) and vel > t["vel_max"]: t["vel_max"] = vel
        if isinstance(rpm, (int, float)) and rpm > t["rpm_max"]: t["rpm_max"] = rpm
        if isinstance(ect, (int, float)) and ect > -5:
            if t["ect_ini"] is None: t["ect_ini"] = ect
            if t["ect_max"] is None or ect > t["ect_max"]: t["ect_max"] = ect
        if isinstance(kv, (int, float)) and kv > t["knock_sensor_max_v"]: t["knock_sensor_max_v"] = kv

    def gerar_texto_boletim(self, colorido=True):
        if not hasattr(self, "tel"): self._init_telemetria_viagem()
        t = self.tel
        dur_s = max(1, int(time.time() - t["inicio_ts"]))
        mins, segs = divmod(dur_s, 60)
        return (
            f"[b][color=#77bbff]=== BOLETIM PREDITIVO - TR4 2.0 ===[/color][/b]\n"
            f"Tempo monitorado: {mins}m {segs}s | Amostras: {t['amostras']}\n"
            f"RPM Max: {t['rpm_max']:.0f} rpm | Vel Max: {t['vel_max']:.0f} km/h\n\n"
            f"[b]1. TEMPERATURA AGUA MAX:[/b] {t['ect_max']} C\n"
            f"[b]2. SENSOR DE KNOCK MAX:[/b] {t['knock_sensor_max_v']:.2f} V\n"
            f"[b]Status:[/b] Coleta automatica ativa em segundo plano."
        )

    def atualizar_tela_boletim(self):
        if hasattr(self, "lbl_boletim"): self.lbl_boletim.text = self.gerar_texto_boletim(colorido=True)

    def salvar_boletim_txt(self, *args):
        try:
            pasta = self._obter_pasta_gravacao()
            arq = os.path.join(pasta, f"BOLETIM_TR4_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            with open(arq, "w", encoding="utf-8") as f:
                f.write(re.sub(r"\[/?[^\]]+\]", "", self.gerar_texto_boletim(colorido=False)))
            if hasattr(self, "lbl_eng"): self.lbl_eng.text = f"Boletim salvo em:\n{arq}"
        except Exception as e:
            if hasattr(self, "lbl_eng"): self.lbl_eng.text = f"Erro: {e}"

    def _caminho_config_bt(self):
        return os.path.join(getattr(self, "user_data_dir", "."), "bt_config.json")

    def _carregar_bt_salvo(self):
        try:
            if os.path.exists(arq := self._caminho_config_bt()):
                with open(arq, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    self.bt_salvo_addr, self.bt_salvo_nome = str(d.get("addr", "")), str(d.get("nome", ""))
        except Exception:
            self.bt_salvo_addr = self.bt_salvo_nome = ""

    def _salvar_bt_salvo(self, addr, nome):
        self.bt_salvo_addr, self.bt_salvo_nome = str(addr), str(nome)
        try:
            with open(self._caminho_config_bt(), "w", encoding="utf-8") as f:
                json.dump({"addr": self.bt_salvo_addr, "nome": self.bt_salvo_nome}, f)
        except Exception: pass

    def _atualizar_estado_conexao(self, est):
        self.estado_conexao = est
        self._manter_tela_acesa(est in ("CONECTADO", "SIMULACAO"))
        if hasattr(self, "btn_bt_lista"):
            self.btn_bt_lista.text = "TROCAR\nBLUETOOTH" if self.bt_salvo_addr else "ESCOLHER\nBLUETOOTH"

    def acao_botao_conexao(self, *args):
        if self.estado_conexao == "CONECTANDO": self.cancelar_tentativa_conexao()
        elif self.estado_conexao in ("CONECTADO", "SIMULACAO"): self.desconectar_ecu()
        else:
            if self.bt_salvo_addr: self._iniciar_conexao_completa(self.bt_salvo_addr, self.bt_salvo_nome)
            else: self.conectar_bluetooth()

    def cancelar_tentativa_conexao(self):
        self.cancelar_conexao = True
        self._fechar_socket_bt()
        self._atualizar_estado_conexao("DESCONECTADO")

    def _fechar_socket_bt(self):
        if (s := getattr(self, "bt_socket", None)):
            try: s.close()
            except Exception: pass
        self.bt_socket = self.bt_in = self.bt_out = None

    def iniciar_simulacao(self, *args):
        self.desconectar_ecu()
        self.modo_simulacao, self.rodando = True, True
        self._atualizar_estado_conexao("SIMULACAO")
        threading.Thread(target=self.loop_leitura, daemon=True).start()

    def conectar_bluetooth(self, *args):
        try:
            from jnius import autoclass
            adapter = autoclass("android.bluetooth.BluetoothAdapter").getDefaultAdapter()
            if not adapter or not adapter.isEnabled(): return
            self._abrir_seletor_bt(list(adapter.getBondedDevices().toArray()))
        except Exception: pass

    def _abrir_seletor_bt(self, pareados):
        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        scroll = ScrollView(size_hint_y=0.8)
        lista = GridLayout(cols=1, spacing=dp(10), size_hint_y=None)
        lista.bind(minimum_height=lista.setter("height"))
        popup = Popup(title="Selecionar Bluetooth", content=box, size_hint=(0.9, 0.8))
        for dev in pareados:
            addr, nome = str(dev.getAddress()), str(dev.getName() or "Sem Nome")
            btn = Button(text=nome, size_hint_y=None, height=dp(50), background_color=(0.14, 0.42, 0.68, 1))
            btn.bind(on_release=lambda inst, a=addr, n=nome, p=popup: (p.dismiss(), self._salvar_bt_salvo(a, n), self._iniciar_conexao_completa(a, n)))
            lista.add_widget(btn)
        scroll.add_widget(lista)
        box.add_widget(scroll)
        popup.open()

    def _iniciar_conexao_completa(self, addr, nome):
        self.desconectar_ecu()
        self.cancelar_conexao = False
        self._atualizar_estado_conexao("CONECTANDO")
        threading.Thread(target=self._conectar_tudo_thread, args=(addr, nome), daemon=True).start()

    def _conectar_tudo_thread(self, addr, nome):
        try:
            from jnius import autoclass
            sock = autoclass("android.bluetooth.BluetoothAdapter").getDefaultAdapter().getRemoteDevice(addr).createRfcommSocketToServiceRecord(autoclass("java.util.UUID").fromString("00001101-0000-1000-8000-00805F9B34FB"))
            self.bt_socket = sock
            sock.connect()
            self.bt_in, self.bt_out = sock.getInputStream(), sock.getOutputStream()
            self.enviar_comando_raw("ATZ", 2.0)
            for c in ["ATE0", "ATL0", "ATS0", "ATH0", "ATAT1", "ATST64", "ATSP5", "ATSH8110F1", "ATWM8110F13E"]:
                self.enviar_comando_raw(c, 1.0)
            self.enviar_comando_raw("ATFI", 3.0)
            self.enviar_comando_raw("1081", 2.0)
            self.rodando, self.modo_simulacao = True, False
            Clock.schedule_once(lambda dt: self._atualizar_estado_conexao("CONECTADO"))
            self.loop_leitura()
        except Exception:
            self.desconectar_ecu()

    def enviar_comando_raw(self, cmd, timeout=1.5):
        if not self.bt_out or not self.bt_in: return ""
        try:
            self.bt_out.write((cmd + "\r").encode("ascii"))
            self.bt_out.flush()
            resp = bytearray()
            lim = time.time() + timeout
            while time.time() < lim:
                if self.bt_in.available() > 0:
                    if (b := self.bt_in.read()) < 0 or b == 62: break
                    resp.append(b)
                else: time.sleep(0.01)
            return resp.decode("ascii", errors="ignore").replace("\r", " ").replace("\n", " ").strip()
        except Exception: return ""

    def parse_bytes_kwp(self, resp, cmd):
        limpo = "".join(c for c in resp.upper() if c in "0123456789ABCDEF")
        try: srv = f"{(int(cmd[:2], 16) + 0x40):02X}"
        except Exception: srv = "61"
        idx = limpo.find(srv + cmd[2:4].upper())
        if idx == -1: return []
        d = limpo[idx + 4:]
        return [int(d[i:i+2], 16) for i in range(0, len(d)-1, 2)]

    def _registrar_valor(self, pid_id, val):
        if val is None: return
        self.valores_atuais[pid_id] = val
        if isinstance(val, (int, float)):
            if pid_id not in self.valores_min or val < self.valores_min[pid_id]: self.valores_min[pid_id] = val
            if pid_id not in self.valores_max or val > self.valores_max[pid_id]: self.valores_max[pid_id] = val

    def zerar_min_max(self, *args):
        self.valores_min, self.valores_max = {}, {}
        for k, v in self.valores_atuais.items():
            if isinstance(v, (int, float)): self.valores_min[k] = self.valores_max[k] = v
        self.atualizar_interface(0)

    def loop_leitura(self):
        t0, ciclo = time.time(), 0
        while self.rodando:
            ciclo += 1
            t_atu = time.time() - t0
            cache = {}
            for p in PIDS_DB:
                if not self.rodando: break
                pid_id = p["id"]
                if not (self.selecionados.get(pid_id, False) or (ciclo % 5 == 1 and pid_id in PIDS_VIGILANCIA_BG)): continue
                if self.modo_simulacao: val = p["sim"](t_atu)
                else:
                    cmd = p["cmd"]
                    if cmd not in cache: cache[cmd] = self.parse_bytes_kwp(self.enviar_comando_raw(cmd, 1.0), cmd)
                    if not cache[cmd]: continue
                    val = p["calc"](cache[cmd])
                self._registrar_valor(pid_id, val)
            
            if getattr(self, "gravando_log", False) and not getattr(self, "log_pausado", False):
                dur = int(time.time() - getattr(self, "inicio_log_ts", time.time()))
                m_log, s_log = divmod(dur, 60)
                linhas_gravadas = getattr(self, "linhas_gravadas_log", 0)
                txt_status_log = f"[b][color=#ff9922]GRAVANDO LOG... ({m_log:02d}:{s_log:02d} | {linhas_gravadas} linhas)[/color][/b]"
                Clock.schedule_once(lambda dt, txt=txt_status_log: setattr(self.lbl_log_info, "text", txt))

            self._processar_amostra_telemetria()
            Clock.schedule_once(self.atualizar_interface)
            time.sleep(0.05 if self.modo_simulacao else 0.04)

    def atualizar_interface(self, dt):
        for pid_id, w in self.cards_ui.items():
            lbl_val, lbl_min, lbl_max, uni = w
            val = self.valores_atuais.get(pid_id, "--")
            lbl_val.text = f"{val} {uni}" if val != "--" else "--"

    def _obter_pasta_gravacao(self):
        return "/sdcard/Download" if os.path.exists("/sdcard/Download") else getattr(self, "user_data_dir", ".")

    def iniciar_gravacao_log(self, *args):
        if not self.rodando:
            if hasattr(self, "lbl_log_info"): self.lbl_log_info.text = "Conecte a ECU antes de gravar o log!"
            return
        if self.gravando_log:
            if getattr(self, "log_pausado", False):
                self.log_pausado = False
            return
        try:
            pasta = self._obter_pasta_gravacao()
            arq = os.path.join(pasta, f"TR4_LOG_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            self.caminho_log_atual = arq
            self.arquivo_log = open(arq, "w", newline="", encoding="utf-8")
            self.writer_log = csv.writer(self.arquivo_log, delimiter=";")
            self.writer_log.writerow(["Tempo_s"] + [p["id"] for p in PIDS_DB if self.selecionados_log.get(p["id"], False)])
            self.arquivo_log.flush()
            self.inicio_log_ts = time.time()
            self.linhas_gravadas_log = 0
            self.gravando_log = True
            self.log_pausado = False
        except Exception as e:
            if hasattr(self, "lbl_log_info"): self.lbl_log_info.text = f"Erro ao criar log: {e}"

    def pausar_gravacao_log(self, *args):
        if not self.gravando_log: return
        self.log_pausado = True
        if hasattr(self, "lbl_log_info"):
            self.lbl_log_info.text = f"[b][color=#e5c158]LOG PAUSADO ({self.linhas_gravadas_log} linhas)[/color][/b]"

    def parar_gravacao_log(self, *args):
        if not self.gravando_log: return
        qtd = getattr(self, "linhas_gravadas_log", 0)
        arq = getattr(self, "caminho_log_atual", "")
        self.gravando_log = False
        self.log_pausado = False
        if self.arquivo_log:
            try: self.arquivo_log.close()
            except Exception: pass
            self.arquivo_log = None
        if hasattr(self, "lbl_log_info"):
            self.lbl_log_info.text = f"[b][color=#33dd77]LOG SALVO COM SUCESSO![/color][/b]\nArquivo: {arq}\nTotal: {qtd} linhas."

    def desconectar_ecu(self, *args):
        self.rodando = self.modo_simulacao = False
        self.parar_gravacao_log()
        self._fechar_socket_bt()
        self.valores_atuais = {p["id"]: "--" for p in PIDS_DB}
        self._atualizar_estado_conexao("DESCONECTADO")
