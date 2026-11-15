# coding: utf-8
import os
import csv
import json
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
    def _caminho_config_bt(self):
        base = getattr(self, "user_data_dir", ".")
        try:
            os.makedirs(base, exist_ok=True)
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
        self.desconectar_ecu()
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
            self._abrir_seletor_bt(pareados)
        except Exception as e:
            err = str(e)
            if "BLUETOOTH_CONNECT" in err or "SecurityException" in err:
                self._atualizar_status("ACEITE A PERMISSAO BLUETOOTH E CLIQUE DE NOVO", (1.0, 0.78, 0.2, 1))
            else:
                self._atualizar_status(f"ERRO BT: {err[:42]}", (1.0, 0.35, 0.35, 1))

    def _abrir_seletor_bt(self, pareados):
        box = BoxLayout(orientation="vertical", padding=10, spacing=10)
        box.add_widget(
            Label(
                text="Toque no scanner para conectar imediatamente:",
                size_hint_y=0.10,
                bold=True,
                font_size="14sp",
            )
        )
        scroll = ScrollView(size_hint_y=0.78)
        lista = GridLayout(cols=1, spacing=12, size_hint_y=None, padding=(4, 6))
        lista.bind(minimum_height=lista.setter("height"))
        popup = Popup(title="Selecionar Scanner Bluetooth", content=box, size_hint=(0.95, 0.85))
        for dev in pareados:
            addr = str(dev.getAddress() or "").strip()
            nome = str(dev.getName() or "").strip() or addr or "Dispositivo Sem Nome"
            eh_salvo = (addr and addr == self.bt_salvo_addr)
            rotulo = f"{nome}  [SALVO]" if eh_salvo else nome
            cor_btn = (0.14, 0.58, 0.38, 1) if eh_salvo else (0.14, 0.42, 0.68, 1)
            btn = Button(
                text=rotulo,
                size_hint_y=None,
                height=68,
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
        popup.dismiss()
        self._salvar_bt_salvo(addr, nome)
        self._iniciar_conexao_completa(addr, nome)

    def _iniciar_conexao_completa(self, addr, nome_dev):
        self._pedir_permissoes_android()
        if self.rodando or self.modo_simulacao:
            self.desconectar_ecu()
        self.cancelar_conexao = False
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

            setup_cmds = ["ATE0", "ATL0", "ATS0", "ATH0", "ATAT1", "ATST64", "ATSP5", "ATSH8110F1", "ATWM8110F13E"]
            for cmd in setup_cmds:
                if self._abortado(seq):
                    return
                self.enviar_comando_raw(cmd, timeout=1.0)

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

            r_sess = self.enviar_comando_raw("1081", timeout=2.5)
            log_hs.append(f"Sessao KWP: {r_sess or 'TIMEOUT'}")
            r_map = self.enviar_comando_raw("2131", timeout=2.0)
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
            self.lbl_eng.text = "ECU conectada com sucesso!\n\nPronta para leitura de falhas, info ou varredura."

    def _falha_conexao(self, titulo, log_hs):
        self.rodando = False
        self._fechar_socket_bt()
        self._atualizar_estado_conexao("DESCONECTADO")
        self._atualizar_status(titulo, (1.0, 0.30, 0.30, 1))
        if hasattr(self, "lbl_eng") and log_hs:
            detalhes = "\n".join(log_hs[-6:])
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
                    linha = [round(time.time() - self.inicio_log_ts, 2)] + [
                        self.valores_atuais.get(pid_id, "") for pid_id in self.pids_gravando_lista
                    ]
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
                    p_letra = prefixos.get(dtc_hex[:1], "P" + dtc_hex[:1])
                    cods.append(f"{p_letra}{dtc_hex[1:4]}")
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

    def buscar_modulos_kwp(self, *args):
        if self.modo_simulacao:
            self.lbl_eng.text = "Simulacao:\n[0x10] Injecao Motor (IAW 4AM) - ATIVO\n[0x18] Cambio AT - Sem resposta"
            return
        if not self.bt_socket or not self.bt_out or not self.bt_in:
            self.lbl_eng.text = "Conecte o Bluetooth primeiro!"
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

        self.enviar_comando_raw("ATSP5", timeout=0.8)
        self.enviar_comando_raw("ATST64", timeout=0.8)
        self.enviar_comando_raw("ATSH8110F1", timeout=0.8)
        self.enviar_comando_raw("ATWM8110F13E", timeout=0.8)
        self.enviar_comando_raw("ATFI", timeout=2.5)
        self.enviar_comando_raw("1081", timeout=1.5)

        texto_final = "Resultado da Busca de Modulos (Pino 7):\n\n" + "\n".join(resultados)
        Clock.schedule_once(lambda dt, t=texto_final: setattr(self.lbl_eng, "text", t))
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
        if self.bt_socket:
            self.rodando = True
            self.loop_leitura()
