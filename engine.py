# coding: utf-8
import os
import csv
import time
import threading
from datetime import datetime
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
            ]
            for extra in ["android.permission.BLUETOOTH_CONNECT", "android.permission.BLUETOOTH_SCAN"]:
                perms.append(extra)
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
        box = BoxLayout(orientation="vertical", padding=8, spacing=6)
        box.add_widget(Label(text="Toque no Scanner Bluetooth pareado:", size_hint_y=0.14, bold=True, font_size="14sp"))
        scroll = ScrollView(size_hint_y=0.72)
        lista = GridLayout(cols=1, spacing=6, size_hint_y=None)
        lista.bind(minimum_height=lista.setter("height"))
        popup = Popup(title="Selecionar Dispositivo Bluetooth", content=box, size_hint=(0.92, 0.75))
        for dev in pareados:
            nome = str(dev.getName() or "Sem Nome")
            mac = str(dev.getAddress() or "")
            btn = Button(text=f"{nome}\n({mac})", size_hint_y=None, height=62, font_size="13sp", bold=True, background_normal="", background_color=(0.14, 0.42, 0.68, 1))
            btn.bind(on_release=lambda inst, d=dev, p=popup: self._iniciar_conexao_bt_escolhido(adapter, d, p))
            lista.add_widget(btn)
        scroll.add_widget(lista)
        box.add_widget(scroll)
        btn_fechar = Button(text="CANCELAR", size_hint_y=0.14, background_normal="", background_color=(0.75, 0.22, 0.22, 1), bold=True)
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
        self.lbl_status.text = "INICIANDO SESSAO KWP2000 NA ECU..."
        self.lbl_status.color = (1.0, 0.78, 0.2, 1)
        threading.Thread(target=self._conectar_ecu_thread, daemon=True).start()

    def _conectar_ecu_thread(self):
        try:
            for cmd in ["ATZ", "ATE0", "ATL0", "ATS0", "ATH0", "ATSP5", "ATSH8110F1", "ATFI", "1081"]:
                self.enviar_comando_raw(cmd)
                time.sleep(0.15)
            self.modo_simulacao = False
            self.rodando = True
            Clock.schedule_once(lambda dt: self._atualizar_status("ECU CONECTADA | IAW 4AM.AR (4AMMS)", (0.2, 0.95, 0.45, 1)))
            self.loop_leitura()
        except Exception as e:
            self.rodando = False
            Clock.schedule_once(lambda dt, err=str(e): self._atualizar_status(f"FALHA ECU: {err[:35]}", (1.0, 0.35, 0.35, 1)))

    def _atualizar_status(self, texto, cor):
        self.lbl_status.text = texto
        self.lbl_status.color = cor

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
