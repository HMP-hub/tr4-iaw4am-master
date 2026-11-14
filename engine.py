# coding: utf-8
import os
import csv
import time
import threading
from datetime import datetime
from operator import itemgetter
from kivy.clock import Clock
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from pids import PIDS_DB


class TR4EngineMixin:
    def iniciar_simulacao(self, *args):
        self.desconectar_ecu()
        self.modo_simulacao = True
        self.rodando = True
        self.lbl_status.text = "SIMULACAO ATIVA | ECU: IAW 4AM.AR"
        self.lbl_status.color = (0.3, 0.9, 0.5, 1)
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
        self._pedir_permissoes_android()
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
            self._abrir_seletor_bt(adapter, pareados)
        except Exception as e:
            err = str(e)
            if "BLUETOOTH_CONNECT" in err or "SecurityException" in err:
                self._atualizar_status("ACEITE A PERMISSAO BLUETOOTH E CLIQUE DE NOVO", (1.0, 0.78, 0.2, 1))
            else:
                self._atualizar_status(f"ERRO BT: {err[:42]}", (1.0, 0.35, 0.35, 1))

    def _abrir_seletor_bt(self, adapter, pareados):
        box = BoxLayout(orientation="vertical", padding=10, spacing=10)
        box.add_widget(Label(text="Toque no Scanner Bluetooth pareado:", size_hint_y=0.10, bold=True, font_size="15sp"))
        scroll = ScrollView(size_hint_y=0.78)
        lista = GridLayout(cols=1, spacing=12, size_hint_y=None, padding=(4, 6))
        lista.bind(minimum_height=lista.setter("height"))
        popup = Popup(title="Selecionar Scanner Bluetooth", content=box, size_hint=(0.95, 0.85))
        for dev in pareados:
            nome = str(dev.getName() or "").strip()
            if not nome:
                nome = str(dev.getAddress() or "Dispositivo Sem Nome")
            btn = Button(
                text=nome,
                size_hint_y=None,
                height=68,
                font_size="16sp",
                bold=True,
                background_normal="",
                background_color=(0.14, 0.42, 0.68, 1),
            )
            btn.bind(on_release=lambda inst, d=dev, p=popup: self._iniciar_conexao_bt_escolhido(adapter, d, p))
            lista.add_widget(btn)
        scroll.add_widget(lista)
        box.add_widget(scroll)
        btn_fechar = Button(text="CANCELAR", size_hint_y=0.12, font_size="14sp", background_normal="", background_color=(0.75, 0.22, 0.22, 1), bold=True)
        btn_fechar.bind(on_release=popup.dismiss)
        box.add_widget(btn_fechar)
        popup.open()

    def _iniciar_conexao_bt_escolhido(self, adapter, dispositivo, popup):
        popup.dismiss()
        nome_dev = str(dispositivo.getName() or "Scanner")
        self._atualizar_status(f"CONECTANDO A {nome_dev}...", (1.0, 0.78, 0.2, 1))
        threading.Thread(target=self._conectar_bt_thread, args=(adapter, dispositivo, nome_dev), daemon=True).start()

    def _conectar_bt_thread(self, adapter, dispositivo_alvo, nome_dev):
        try:
            from jnius import autoclass
            UUID = autoclass("java.util.UUID")
            spp_uuid = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
            if self.bt_socket:
                try:
                    self.bt_socket.close()
                except Exception:
                    pass
            self.bt_socket = dispositivo_alvo.createRfcommSocketToServiceRecord(spp_uuid)
            adapter.cancelDiscovery()
            self.bt_socket.connect()
            self.bt_in = self.bt_socket.getInputStream()
            self.bt_out = self.bt_socket.getOutputStream()
            Clock.schedule_once(lambda dt: self._atualizar_status(f"BT OK ({nome_dev}) | CLIQUE EM CONECTAR ECU", (0.3, 0.85, 1.0, 1)))
        except Exception as e:
            self.bt_socket = None
            self.bt_in = None
            self.bt_out = None
            Clock.schedule_once(lambda dt, err=str(e): self._atualizar_status(f"FALHA SOCKET BT: {err[:34]}", (1.0, 0.35, 0.35, 1)))
    def conectar_ecu(self, *args):
        if self.rodando and not self.modo_simulacao:
            self.lbl_status.text = "ECU IAW 4AM JA CONECTADA"
            return
        if not self.bt_socket or not self.bt_in or not self.bt_out:
            self.lbl_status.text = "ERRO: FACA A CONEXAO BLUETOOTH PRIMEIRO!"
            self.lbl_status.color = (1.0, 0.35, 0.35, 1)
            return
        self.lbl_status.text = "INICIANDO K-LINE (KWP2000) NA ECU..."
        self.lbl_status.color = (1.0, 0.78, 0.2, 1)
        threading.Thread(target=self._conectar_ecu_thread, daemon=True).start()

    def _conectar_ecu_thread(self):
        log_hs = []
        try:
            self._limpar_buffer_bt()
            r_atz = self.enviar_comando_raw("ATZ", timeout=2.5)
            log_hs.append(f"Reset Scanner: {r_atz or 'SEM RESPOSTA'}")
            if not r_atz:
                Clock.schedule_once(lambda dt: self._falha_handshake("SCANNER NAO RESPONDEU", log_hs))
                return

            setup_cmds = ["ATE0", "ATL0", "ATS0", "ATH0", "ATAT1", "ATST64", "ATSP5", "ATSH8110F1", "ATWM8110F13E"]
            for cmd in setup_cmds:
                self.enviar_comando_raw(cmd, timeout=1.0)

            Clock.schedule_once(lambda dt: self._atualizar_status("SINCRONIZANDO BARRAMENTO K-LINE...", (1.0, 0.78, 0.2, 1)))
            r_init = self.enviar_comando_raw("ATFI", timeout=3.5)
            log_hs.append(f"Fast Init: {r_init or 'TIMEOUT'}")

            if "OK" not in r_init.upper():
                self.enviar_comando_raw("ATSP4", timeout=1.0)
                self.enviar_comando_raw("ATSH8110F1", timeout=1.0)
                r_init = self.enviar_comando_raw("ATSI", timeout=4.5)
                log_hs.append(f"Slow Init: {r_init or 'TIMEOUT'}")

            r_sess = self.enviar_comando_raw("1081", timeout=2.5)
            log_hs.append(f"Sessao KWP: {r_sess or 'TIMEOUT'}")
            r_rpm = self.enviar_comando_raw("2131", timeout=2.0)
            log_hs.append(f"Teste RPM: {r_rpm or 'TIMEOUT'}")

            limpo_rpm = "".join(c for c in r_rpm.upper() if c in "0123456789ABCDEF")
            limpo_sess = "".join(c for c in r_sess.upper() if c in "0123456789ABCDEF")
            conectou_real = ("5081" in limpo_sess) or ("6131" in limpo_rpm)

            if not conectou_real:
                Clock.schedule_once(lambda dt: self._falha_handshake("ECU NAO RESPONDEU (CHAVE LIGADA?)", log_hs))
                return

            self.modo_simulacao = False
            self.rodando = True
            Clock.schedule_once(lambda dt: self._sucesso_handshake())
            self.loop_leitura()
        except Exception as e:
            self.rodando = False
            log_hs.append(f"Erro: {e}")
            Clock.schedule_once(lambda dt: self._falha_handshake("ERRO NA COMUNICACAO K-LINE", log_hs))

    def _sucesso_handshake(self):
        self._atualizar_status("ECU CONECTADA | KWP2000 K-LINE ATIVO", (0.2, 0.95, 0.45, 1))
        if hasattr(self, "lbl_eng"):
            self.lbl_eng.text = "ECU conectada com sucesso!\nPronta para leitura de falhas, info ou varredura."

    def _falha_handshake(self, titulo, log_hs):
        self.rodando = False
        self._atualizar_status(titulo, (1.0, 0.30, 0.30, 1))
        detalhes = "\n".join(log_hs[-6:])
        if hasattr(self, "lbl_eng"):
            self.lbl_eng.text = f"{titulo}\n\n{detalhes}"

    def _atualizar_status(self, texto, cor):
        self.lbl_status.text = texto
        self.lbl_status.color = cor

    def _limpar_buffer_bt(self):
        try:
            while self.bt_in and self.bt_in.available() > 0:
                self.bt_in.read()
        except Exception:
            pass

    def enviar_comando_raw(self, cmd, timeout=1.5):
        if not self.bt_out or not self.bt_in:
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
                    if b == 62:
                        break
                    resposta.append(b)
                else:
                    time.sleep(0.01)
            return resposta.decode("ascii", errors="ignore").replace("\r", " ").replace("\n", " ").strip()
        except Exception:
            return ""
        finally:
            if lock:
                lock.release()
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
            gravando_ativo = self.gravando_log and not getattr(self, "log_pausado", False)
            log_ativos = getattr(self, "selecionados_log", {}) if gravando_ativo else {}

            for pid in PIDS_DB:
                if not self.rodando:
                    break
                ativo = self.selecionados.get(pid["id"], False) or log_ativos.get(pid["id"], False)
                if not ativo:
                    continue
                if self.modo_simulacao:
                    valor = pid["sim"](t_atual)
                else:
                    cmd = pid["cmd"]
                    if cmd not in cache_comandos:
                        raw = self.enviar_comando_raw(cmd, timeout=1.2)
                        cache_comandos[cmd] = self.parse_bytes_kwp(raw, cmd)
                    bytes_resp = cache_comandos[cmd]
                    if not bytes_resp:
                        continue
                    valor = pid["calc"](bytes_resp)
                self._registrar_valor(pid["id"], valor)

            if not self.rodando:
                break

            if gravando_ativo and self.writer_log and hasattr(self, "pids_gravando_lista"):
                try:
                    linha = [round(time.time() - self.inicio_log_ts, 2)] + [self.valores_atuais.get(pid_id, "") for pid_id in self.pids_gravando_lista]
                    self.writer_log.writerow(linha)
                    self.arquivo_log.flush()
                    self.linhas_gravadas_log = getattr(self, "linhas_gravadas_log", 0) + 1
                except Exception:
                    pass
            Clock.schedule_once(self.atualizar_interface)
            time.sleep(0.12 if self.modo_simulacao else 0.04)

    def atualizar_interface(self, dt):
        for pid_id, widgets in self.cards_ui.items():
            lbl_val, lbl_mm, unidade = widgets
            val = self.valores_atuais.get(pid_id, "--")
            lbl_val.text = f"{val} {unidade}" if val != "--" else "--"
            vmin = self.valores_min.get(pid_id, "--")
            vmax = self.valores_max.get(pid_id, "--")
            lbl_mm.text = f"MIN: {vmin}   |   MAX: {vmax}"
        if hasattr(self, "graficos_lista") and hasattr(self, "pids_graf"):
            for idx, graf in enumerate(self.graficos_lista):
                val = self.valores_atuais.get(self.pids_graf[idx])
                if isinstance(val, (int, float)):
                    graf.adicionar_ponto(val)

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
        if hasattr(self, "lbl_log_info") and arq:
            self.lbl_log_info.text = f"LOG ENCERRADO E SALVO ({qtd} linhas):\n{arq}"
    def ler_info_ecu(self, *args):
        if self.modo_simulacao:
            self.lbl_eng.text = (
                "Desenho FIAT: CA130195\n"
                "Numero HW: IAW4AMHWM44 (Ver: 00)\n"
                "Numero SW: 0401BA83 (Ver: 0000)\n"
                "Homologacao: 4AMMS | ISO: 0000000000\n"
                "Data Programacao: 20/10/2009\n"
                "Reescritas Flash: 1 | Odo Reescr: 0 km\n"
                "Odometro Real ECU: 69.456 km"
            )
            return
        if not self.rodando or not self.bt_out or not self.bt_in:
            self.lbl_eng.text = "ECU desconectada! Clique em CONECTAR ECU primeiro."
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
            hw_ver = f"{b80[22]:02X}"
            sw = _ascii(b80[23:34]) or "N/D"
            sw_ver = f"{b80[34]:02X}{b80[35]:02X}"
            homolog = _ascii(b80[36:42]) or "N/D"
            iso = "".join(f"{x:02X}" for x in b80[42:47])
            data_prog = f"{b80[60]:02X}/{b80[59]:02X}/20{b80[58]:02X}"
        else:
            desenho, hw, hw_ver, sw, sw_ver, homolog, iso, data_prog = ("N/D", "N/D", "00", "N/D", "0000", "N/D", "N/D", "N/D")

        odo_txt = "Nao disponivel"
        if len(b71) >= 3:
            b_o0, b_o1, b_o2 = itemgetter(0, 1, 2)(b71)
            km_val = (b_o0 << 16) | (b_o1 << 8) | b_o2
            odo_txt = f"{km_val:,} km".replace(",", ".")

        reescr = ((b72[0] << 8) | b72[1]) if len(b72) >= 2 else 0
        odo_reescr = ((b73[0] << 16) | (b73[1] << 8) | b73[2]) if len(b73) >= 3 else 0

        texto = (
            f"Desenho FIAT: {desenho}\n"
            f"Numero HW: {hw} (Ver: {hw_ver})\n"
            f"Numero SW: {sw} (Ver: {sw_ver})\n"
            f"Homologacao: {homolog} | ISO: {iso}\n"
            f"Data Programacao: {data_prog}\n"
            f"Reescritas Flash: {reescr} | Odo Reescr: {odo_reescr} km\n"
            f"Odometro Real ECU: {odo_txt}"
        )
        Clock.schedule_once(lambda dt: setattr(self.lbl_eng, "text", texto))
        if self.bt_socket:
            self.rodando = True
            self.loop_leitura()

    def ler_dtcs(self, *args):
        if self.modo_simulacao:
            self.lbl_eng.text = "Nenhuma falha armazenada na ECU."
            return
        if not self.rodando or not self.bt_out or not self.bt_in:
            self.lbl_eng.text = "ECU desconectada! Clique em CONECTAR ECU primeiro."
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
                    p_letra = prefixos.get(dtc_hex[0], "P" + dtc_hex[0])
                    cods.append(f"{p_letra}{dtc_hex[1:]}")
                msg = f"Falhas encontradas ({qtd}):\n\n" + (", ".join(cods) if cods else dados)
        else:
            msg = f"Retorno da ECU:\n{resp if resp else 'Sem resposta'}"
        Clock.schedule_once(lambda dt: setattr(self.lbl_eng, "text", msg))
        if self.bt_socket:
            self.rodando = True
            self.loop_leitura()

    def apagar_dtcs(self, *args):
        if self.modo_simulacao:
            self.lbl_eng.text = "Memoria de falhas limpa!"
            return
        if not self.rodando or not self.bt_out or not self.bt_in:
            self.lbl_eng.text = "ECU desconectada! Clique em CONECTAR ECU primeiro."
            return
        self.rodando = False
        threading.Thread(target=self._apagar_dtcs_thread, daemon=True).start()

    def _apagar_dtcs_thread(self):
        time.sleep(0.25)
        resp = self.enviar_comando_raw("14FF00", timeout=2.0)
        msg = "Falhas apagadas com sucesso!" if "54" in resp.upper() else f"Comando enviado ({resp})"
        Clock.schedule_once(lambda dt: setattr(self.lbl_eng, "text", msg))
        if self.bt_socket:
            self.rodando = True
            self.loop_leitura()

    def desconectar_ecu(self, *args):
        self.rodando = False
        self.varrendo = False
        self.modo_simulacao = False
        self.parar_gravacao_log()
        self.valores_atuais = {p["id"]: "--" for p in PIDS_DB}
        self.valores_min = {}
        self.valores_max = {}
        self.atualizar_interface(0)
        if hasattr(self, "lbl_eng"):
            self.lbl_eng.text = "ECU desconectada."
        if self.bt_socket:
            self.lbl_status.text = "ECU DESCONECTADA | BLUETOOTH ATIVO"
            self.lbl_status.color = (0.3, 0.85, 1.0, 1)
        else:
            self.lbl_status.text = "DESCONECTADO | ECU: IAW 4AM.AR (4AMMS)"
            self.lbl_status.color = (1, 0.78, 0.2, 1)

    def iniciar_varredura_ecu(self, *args):
        if getattr(self, "varrendo", False):
            return
        if self.modo_simulacao:
            self.lbl_eng.text = "Simulacao: 2131, 213B, 2147 ativos."
            return
        if not self.rodando or not self.bt_out or not self.bt_in:
            self.lbl_eng.text = "ECU desconectada! Clique em CONECTAR ECU primeiro."
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
                Clock.schedule_once(
                    lambda dt, c=cmd, n=len(encontrados): setattr(
                        self.lbl_eng, "text", f"Varrendo endereco {c} de 21FF...\n\nPIDs ativos encontrados: {n}"
                    )
                )
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

        Clock.schedule_once(
            lambda dt: setattr(
                self.lbl_eng, "text", f"Varredura finalizada!\n\nTotal encontrados: {len(encontrados)}\n\n{resumo}"
            )
        )
        if self.bt_socket:
            self.rodando = True
            self.loop_leitura()
