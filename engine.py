# coding: utf-8
import os
import csv
import time
import threading
from datetime import datetime
from kivy.clock import Clock
from pids import PIDS_DB


class TR4EngineMixin:
    def iniciar_simulacao(self, *args):
        self.parar_conexao()
        self.modo_simulacao = True
        self.rodando = True
        self.lbl_status.text = "MODO SIMULACAO ATIVO | IAW 4AM.AR"
        self.lbl_status.color = (0.3, 0.9, 0.5, 1)
        threading.Thread(target=self.loop_leitura, daemon=True).start()

    def iniciar_bluetooth(self, *args):
        self.parar_conexao()
        self.lbl_status.text = "CONECTANDO AO OBDLINK MX+..."
        threading.Thread(target=self._conectar_bt_thread, daemon=True).start()

    def _conectar_bt_thread(self):
        try:
            from jnius import autoclass
            BluetoothAdapter = autoclass("android.bluetooth.BluetoothAdapter")
            UUID = autoclass("java.util.UUID")
            adapter = BluetoothAdapter.getDefaultAdapter()
            if not adapter or not adapter.isEnabled():
                Clock.schedule_once(lambda dt: setattr(self.lbl_status, "text", "ERRO: LIGUE O BLUETOOTH"))
                return
            spp_uuid = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
            dispositivo_alvo = None
            for dev in adapter.getBondedDevices().toArray():
                nome = str(dev.getName()).upper()
                if "OBDLINK" in nome or "MX" in nome or "OBD" in nome or "ELM" in nome:
                    dispositivo_alvo = dev
                    break
            if not dispositivo_alvo:
                Clock.schedule_once(lambda dt: setattr(self.lbl_status, "text", "OBDLINK MX+ NAO PAREADO"))
                return
            self.bt_socket = dispositivo_alvo.createRfcommSocketToServiceRecord(spp_uuid)
            adapter.cancelDiscovery()
            self.bt_socket.connect()
            self.bt_in = self.bt_socket.getInputStream()
            self.bt_out = self.bt_socket.getOutputStream()
            for cmd in ["ATZ", "ATE0", "ATL0", "ATS0", "ATH0", "ATSP5", "ATSH8110F1", "ATFI", "1081"]:
                self.enviar_comando_raw(cmd)
                time.sleep(0.15)
            self.modo_simulacao = False
            self.rodando = True
            Clock.schedule_once(lambda dt: setattr(self.lbl_status, "text", f"CONECTADO: {dispositivo_alvo.getName()} | IAW 4AM"))
            self.loop_leitura()
        except Exception as e:
            Clock.schedule_once(lambda dt, err=str(e): setattr(self.lbl_status, "text", f"FALHA BT: {err[:38]}"))

    def enviar_comando_raw(self, cmd):
        if not self.bt_out or not self.bt_in:
            return ""
        try:
            self.bt_out.write((cmd + "\r").encode("ascii"))
            self.bt_out.flush()
            resposta = bytearray()
            t_limite = time.time() + 1.2
            while time.time() < t_limite:
                if self.bt_in.available() > 0:
                    b = self.bt_in.read()
                    if b == 62:
                        break
                    resposta.append(b)
                else:
                    time.sleep(0.01)
            return resposta.decode("ascii", errors="ignore").strip()
        except Exception:
            return ""

    def parse_bytes_kwp(self, resp_str, cmd_enviado):
        limpo = "".join(c for c in resp_str.upper() if c in "0123456789ABCDEF")
        prefixo_ok = "61" + cmd_enviado[2:4].upper()
        idx = limpo.find(prefixo_ok)
        if idx == -1:
            return []
        dados_hex = limpo[idx + 4:]
        return [int(dados_hex[i:i + 2], 16) for i in range(0, len(dados_hex) - 1, 2)]
    def loop_leitura(self):
        t0 = time.time()
        while self.rodando:
            t_atual = time.time() - t0
            cache_comandos = {}
            for pid in PIDS_DB:
                if not self.rodando:
                    break
                if not self.selecionados.get(pid["id"], False):
                    continue
                if pid["cmd"] == "CALC_HIBRIDO":
                    continue
                if self.modo_simulacao:
                    valor = pid["sim"](t_atual)
                else:
                    cmd = pid["cmd"]
                    if cmd not in cache_comandos:
                        raw = self.enviar_comando_raw(cmd)
                        cache_comandos[cmd] = self.parse_bytes_kwp(raw, cmd)
                    bytes_resp = cache_comandos[cmd]
                    if not bytes_resp:
                        continue
                    valor = pid["calc"](bytes_resp)
                self.valores_atuais[pid["id"]] = valor

            et_sfs = self.valores_atuais.get("ETANOL_REAL")
            stft_v = self.valores_atuais.get("STFT")
            ltft_v = self.valores_atuais.get("LTFT")
            if isinstance(et_sfs, (int, float)) and isinstance(stft_v, (int, float)) and isinstance(ltft_v, (int, float)):
                ajuste_trim = (stft_v + ltft_v) * 1.8
                self.valores_atuais["ETANOL_INST"] = round(max(0.0, min(100.0, et_sfs + ajuste_trim)), 0)

            if self.gravando_log and self.writer_log:
                try:
                    linha = [round(time.time() - self.inicio_log_ts, 2)] + [self.valores_atuais.get(p["id"], "") for p in PIDS_DB]
                    self.writer_log.writerow(linha)
                    self.arquivo_log.flush()
                except Exception:
                    pass
            Clock.schedule_once(self.atualizar_interface)
            time.sleep(0.12 if self.modo_simulacao else 0.04)

    def atualizar_interface(self, dt):
        for pid_id, (lbl_val, unidade) in self.cards_ui.items():
            lbl_val.text = f"{self.valores_atuais.get(pid_id, '--')} {unidade}"
        if hasattr(self, "graficos_lista") and hasattr(self, "pids_graf"):
            for idx, graf in enumerate(self.graficos_lista):
                val = self.valores_atuais.get(self.pids_graf[idx])
                if isinstance(val, (int, float)):
                    graf.adicionar_ponto(val)

    def iniciar_gravacao_log(self, *args):
        if self.gravando_log:
            return
        try:
            pasta = "/sdcard/Download" if os.path.exists("/sdcard/Download") else "."
            nome_arq = os.path.join(pasta, f"TR4_IAW4AM_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            self.arquivo_log = open(nome_arq, "w", newline="", encoding="utf-8")
            self.writer_log = csv.writer(self.arquivo_log, delimiter=";")
            self.writer_log.writerow(["Tempo_s"] + [p["id"] for p in PIDS_DB])
            self.inicio_log_ts = time.time()
            self.gravando_log = True
            if hasattr(self, "lbl_log_info"):
                self.lbl_log_info.text = f"GRAVANDO LOG:\n{nome_arq}"
        except Exception as e:
            if hasattr(self, "lbl_log_info"):
                self.lbl_log_info.text = f"Erro ao criar CSV: {e}"

    def parar_gravacao_log(self, *args):
        self.gravando_log = False
        if self.arquivo_log:
            try:
                self.arquivo_log.close()
            except Exception:
                pass
            self.arquivo_log = None
            self.writer_log = None
        if hasattr(self, "lbl_log_info"):
            self.lbl_log_info.text = "Log salvo e fechado com sucesso."

    def ler_dtcs(self, *args):
        if self.modo_simulacao:
            self.lbl_eng.text = "Simulacao DTC:\nNenhuma falha ativa (P0000)"
            return
        resp = self.enviar_comando_raw("1800FF00")
        self.lbl_eng.text = f"Resposta DTC ECU (18 00 FF 00):\n{resp if resp else 'Sem resposta'}"

    def apagar_dtcs(self, *args):
        if self.modo_simulacao:
            self.lbl_eng.text = "Simulacao DTC:\nMemoria de falhas limpa!"
            return
        resp = self.enviar_comando_raw("14FF00")
        self.lbl_eng.text = f"Apagar Falhas (14 FF 00):\n{resp if resp else 'Comando enviado'}"

    def parar_conexao(self, *args):
        self.rodando = False
        self.modo_simulacao = False
        self.parar_gravacao_log()
        if self.bt_socket:
            try:
                self.bt_socket.close()
            except Exception:
                pass
            self.bt_socket = None
        self.lbl_status.text = "DESCONECTADO | ECU: IAW 4AM.AR (4AMMS)"
        self.lbl_status.color = (1, 0.78, 0.2, 1)
