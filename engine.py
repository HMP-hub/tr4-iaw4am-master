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

    def _registrar_valor(self, pid_id, valor):
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
        while self.rodando:
            t_atual = time.time() - t0
            cache_comandos = {}
            log_ativos = getattr(self, "selecionados_log", {}) if self.gravando_log else {}
            for pid in PIDS_DB:
                if not self.rodando:
                    break
                ativo = self.selecionados.get(pid["id"], False) or log_ativos.get(pid["id"], False)
                if not ativo or pid["cmd"] == "CALC_HIBRIDO":
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
                self._registrar_valor(pid["id"], valor)

            et_sfs = self.valores_atuais.get("ETANOL_REAL")
            stft_v = self.valores_atuais.get("STFT")
            ltft_v = self.valores_atuais.get("LTFT")
            if isinstance(et_sfs, (int, float)) and isinstance(stft_v, (int, float)) and isinstance(ltft_v, (int, float)):
                ajuste_trim = (stft_v + ltft_v) * 1.8
                self._registrar_valor("ETANOL_INST", round(max(0.0, min(100.0, et_sfs + ajuste_trim)), 0))

            if self.gravando_log and self.writer_log and hasattr(self, "pids_gravando_lista"):
                try:
                    linha = [round(time.time() - self.inicio_log_ts, 2)] + [self.valores_atuais.get(pid_id, "") for pid_id in self.pids_gravando_lista]
                    self.writer_log.writerow(linha)
                    self.arquivo_log.flush()
                except Exception:
                    pass
            Clock.schedule_once(self.atualizar_interface)
            time.sleep(0.12 if self.modo_simulacao else 0.04)

    def atualizar_interface(self, dt):
        for pid_id, widgets in self.cards_ui.items():
            lbl_val, lbl_mm, unidade = widgets
            val = self.valores_atuais.get(pid_id, "--")
            lbl_val.text = f"{val} {unidade}"
            vmin = self.valores_min.get(pid_id, "--")
            vmax = self.valores_max.get(pid_id, "--")
            lbl_mm.text = f"MIN: {vmin}   |   MAX: {vmax}"
        if hasattr(self, "graficos_lista") and hasattr(self, "pids_graf"):
            for idx, graf in enumerate(self.graficos_lista):
                val = self.valores_atuais.get(self.pids_graf[idx])
                if isinstance(val, (int, float)):
                    graf.adicionar_ponto(val)

    def iniciar_gravacao_log(self, *args):
        if self.gravando_log:
            return
        try:
            sel_log = getattr(self, "selecionados_log", {p["id"]: p["rapido"] for p in PIDS_DB})
            self.pids_gravando_lista = [p["id"] for p in PIDS_DB if sel_log.get(p["id"], False)]
            if not self.pids_gravando_lista:
                self.pids_gravando_lista = [p["id"] for p in PIDS_DB if p["rapido"]]
            pasta = "/sdcard/Download" if os.path.exists("/sdcard/Download") else "."
            nome_arq = os.path.join(pasta, f"TR4_IAW4AM_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            self.arquivo_log = open(nome_arq, "w", newline="", encoding="utf-8")
            self.writer_log = csv.writer(self.arquivo_log, delimiter=";")
            self.writer_log.writerow(["Tempo_s"] + self.pids_gravando_lista)
            self.inicio_log_ts = time.time()
            self.gravando_log = True
            if hasattr(self, "lbl_log_info"):
                self.lbl_log_info.text = f"GRAVANDO ({len(self.pids_gravando_lista)} PIDs):\n{nome_arq}"
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

    def ler_info_ecu(self, *args):
        if self.modo_simulacao:
            self.lbl_eng.text = "INFO ECU (SIMULACAO):\nModelo: IAW4AMS4 (4AM.AR)\nOdometro ECU: 69.412 km\nHardware/SW: 4AMMS"
            return
        if not self.bt_out or not self.bt_in:
            self.lbl_eng.text = "Conecte ao OBDLink MX+ primeiro!"
            return
        estava_rodando = self.rodando
        self.rodando = False
        time.sleep(0.15)
        threading.Thread(target=self._ler_info_ecu_thread, args=(estava_rodando,), daemon=True).start()

    def _ler_info_ecu_thread(self, retomar):
        def _ascii(b_list):
            return "".join(chr(x) if 32 <= x <= 126 else "" for x in b_list).strip()
        b80 = self.parse_bytes_kwp(self.enviar_comando_raw("2180"), "2180")
        b92 = self.parse_bytes_kwp(self.enviar_comando_raw("2192"), "2192")
        b94 = self.parse_bytes_kwp(self.enviar_comando_raw("2194"), "2194")
        b96 = self.parse_bytes_kwp(self.enviar_comando_raw("2196"), "2196")
        b71 = self.parse_bytes_kwp(self.enviar_comando_raw("2171"), "2171")
        odo_txt = "N/D"
        if len(b71) >= 3:
            km_val = (b71[0] << 16) | (b71[1] << 8) | b71[2]
            odo_txt = f"{km_val:,} km (HEX: {b71[0]:02X} {b71[1]:02X} {b71[2]:02X})".replace(",", ".")
        texto = (
            f"=== IDENTIFICACAO ECU IAW 4AM ===\n"
            f"ID Geral (2180): {_ascii(b80)}\n"
            f"Modelo/SW (2192): {_ascii(b92)}\n"
            f"Serie/Calib (2194): {_ascii(b94)}\n"
            f"Codigo ECU (2196): {_ascii(b96)}\n"
            f"Odometro Real ECU (2171): {odo_txt}"
        )
        Clock.schedule_once(lambda dt: setattr(self.lbl_eng, "text", texto))
        if retomar:
            self.rodando = True
            self.loop_leitura()

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

    def iniciar_varredura_ecu(self, *args):
        if self.modo_simulacao:
            self.lbl_eng.text = "Simulacao Varredura:\n2131: 03 0C (RPM)\n213B: 80 (ECT)\n2147: A2 (STFT)"
            return
        if not self.bt_out or not self.bt_in:
            self.lbl_eng.text = "Conecte ao OBDLink MX+ primeiro!"
            return
        self.rodando = False
        time.sleep(0.15)
        threading.Thread(target=self._executar_varredura_thread, daemon=True).start()

    def _executar_varredura_thread(self):
        pasta = "/sdcard/Download" if os.path.exists("/sdcard/Download") else "."
        nome_arq = os.path.join(pasta, f"MAPA_IAW4AM_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        encontrados = []
        for code in range(0x00, 0x100):
            cmd = f"21{code:02X}"
            if code % 16 == 0:
                Clock.schedule_once(lambda dt, c=cmd, n=len(encontrados): setattr(self.lbl_eng, "text", f"Varrendo {c} / 21FF...\nAtivos encontrados: {n}"))
            resp = self.enviar_comando_raw(cmd)
            limpo = "".join(c for c in resp.upper() if c in "0123456789ABCDEF")
            prefixo_ok = f"61{code:02X}"
            idx = limpo.find(prefixo_ok)
            if idx != -1:
                dados = limpo[idx + 4:]
                pares = " ".join(dados[i:i + 2] for i in range(0, len(dados) - 1, 2))
                encontrados.append(f"{cmd} -> {pares}")
        with open(nome_arq, "w", encoding="utf-8") as f:
            f.write(f"MAPA DE PIDS ATIVOS - ECU IAW 4AM ({datetime.now()})\n")
            f.write(f"Total encontrados: {len(encontrados)}\n" + "=" * 45 + "\n")
            f.write("\n".join(encontrados))
        resumo = "\n".join(encontrados[:7])
        Clock.schedule_once(lambda dt: setattr(self.lbl_eng, "text", f"Concluido! {len(encontrados)} PIDs salvos em:\n{nome_arq}\n\n{resumo}"))
