    def mostrar_aba_grafico(self, *args):
        self.limpar_area_central()
        self.graficos_lista = []
        self.labels_graf_lista = []
        opcoes = [("STFT", "STFT"), ("SONDA_PRE", "SONDA1"), ("SONDA_POS", "SONDA2"), ("MAP_KPA", "MAP"), ("TI_PRINCIPAL", "INJ"), ("AVANCO_IGN", "IGN"), ("RPM", "RPM"), ("TPS_PCT", "TPS")]
        box = BoxLayout(orientation="vertical", spacing=4)
        for idx in range(3):
            linha_btn = BoxLayout(size_hint_y=0.08, spacing=2)
            for pid_id, rot in opcoes:
                b = Button(text=rot, font_size="9sp", bold=True, background_normal="", background_color=(0.22, 0.28, 0.36, 1))
                b.bind(on_release=lambda x, i=idx, p=pid_id: self.mudar_pid_grafico(i, p))
                linha_btn.add_widget(b)
            lbl = Label(text=f"Canal {idx+1}: {self.pids_graf[idx]}", size_hint_y=0.05, font_size="11sp", bold=True, color=(0.3, 0.9, 0.6, 1))
            graf = GraficoTempoReal(size_hint_y=0.20)
            box.add_widget(linha_btn)
            box.add_widget(lbl)
            box.add_widget(graf)
            self.labels_graf_lista.append(lbl)
            self.graficos_lista.append(graf)
        self.area_central.add_widget(box)

    def mudar_pid_grafico(self, idx, pid_id):
        self.pids_graf[idx] = pid_id
        if hasattr(self, "graficos_lista") and idx < len(self.graficos_lista):
            self.graficos_lista[idx].dados.clear()
        if hasattr(self, "labels_graf_lista") and idx < len(self.labels_graf_lista):
            self.labels_graf_lista[idx].text = f"Canal {idx+1}: {pid_id}"

    def mostrar_aba_log(self, *args):
        self.limpar_area_central()
        box = BoxLayout(orientation="vertical", spacing=5, padding=4)
        self.lbl_log_info = Label(text="Toque na barra do sensor para ativar/desativar no CSV:", font_size="12sp", size_hint_y=0.08)
        box.add_widget(self.lbl_log_info)
        botoes = BoxLayout(size_hint_y=0.11, spacing=6)
        b_ini = Button(text="INICIAR LOG", background_normal="", background_color=(0.18, 0.62, 0.34, 1), bold=True, font_size="12sp")
        b_ini.bind(on_release=self.iniciar_gravacao_log)
        b_parar = Button(text="FECHAR LOG", background_normal="", background_color=(0.78, 0.22, 0.22, 1), bold=True, font_size="12sp")
        b_parar.bind(on_release=self.parar_gravacao_log)
        botoes.add_widget(b_ini)
        botoes.add_widget(b_parar)
        box.add_widget(botoes)
        acoes = BoxLayout(size_hint_y=0.09, spacing=4)
        for txt, modo, cor in [("TODOS", "TODOS", (0.15, 0.55, 0.80, 1)), ("LOG RAPIDO", "RAPIDO", (0.20, 0.65, 0.40, 1)), ("DESMARCAR", "NENHUM", (0.65, 0.25, 0.25, 1))]:
            b = Button(text=txt, font_size="10sp", background_normal="", background_color=cor, bold=True)
            b.bind(on_release=lambda x, m=modo: self.definir_pids_log(m))
            acoes.add_widget(b)
        box.add_widget(acoes)
        scroll = ScrollView(size_hint_y=0.72)
        lista = GridLayout(cols=1, spacing=6, size_hint_y=None, padding=(2, 4))
        lista.bind(minimum_height=lista.setter("height"))
        self.btns_log_ui = {}
        for pid in PIDS_DB:
            btn = Button(size_hint_y=None, height=50, font_size="12sp", bold=True, background_normal="", halign="left", valign="middle", padding=(12, 0))
            btn.bind(size=btn.setter("text_size"))
            self._estilo_btn_pid(btn, pid, self.selecionados_log.get(pid["id"], False), False)
            btn.bind(on_release=lambda inst, p=pid: self._alternar_pid_log(inst, p))
            lista.add_widget(btn)
            self.btns_log_ui[pid["id"]] = (btn, pid)
        scroll.add_widget(lista)
        box.add_widget(scroll)
        self.area_central.add_widget(box)

    def definir_pids_log(self, modo):
        for pid in PIDS_DB:
            estado = True if modo == "TODOS" else (pid["rapido"] if modo == "RAPIDO" else False)
            self.selecionados_log[pid["id"]] = estado
            if pid["id"] in self.btns_log_ui:
                btn, p_obj = self.btns_log_ui[pid["id"]]
                self._estilo_btn_pid(btn, p_obj, estado, False)

    def mostrar_aba_engenharia(self, *args):
        self.limpar_area_central()
        box = BoxLayout(orientation="vertical", spacing=8, padding=8)
        self.lbl_eng = Label(text="Modulo de Engenharia IAW 4AM.AR (SW 4AMMS)\nSessao Estendida KWP2000 (10 81)", font_size="12sp", size_hint_y=0.55)
        box.add_widget(self.lbl_eng)
        botoes = BoxLayout(size_hint_y=0.20, spacing=8)
        b_dtc = Button(text="LER FALHAS (DTC)", background_normal="", background_color=(0.15, 0.50, 0.80, 1), bold=True)
        b_dtc.bind(on_release=self.ler_dtcs)
        b_clear = Button(text="APAGAR FALHAS", background_normal="", background_color=(0.80, 0.40, 0.12, 1), bold=True)
        b_clear.bind(on_release=self.apagar_dtcs)
        botoes.add_widget(b_dtc)
        botoes.add_widget(b_clear)
        box.add_widget(botoes)
        b_scan = Button(text="VARRER ECU (2100 - 21FF) E SALVAR MAPA", size_hint_y=0.18, background_normal="", background_color=(0.20, 0.62, 0.45, 1), bold=True)
        b_scan.bind(on_release=self.iniciar_varredura_ecu)
        box.add_widget(b_scan)
        self.area_central.add_widget(box)


class TelaErroApp(App):
    def __init__(self, msg_erro, **kwargs):
        super().__init__(**kwargs)
        self.msg_erro = msg_erro

    def build(self):
        lbl = Label(text=self.msg_erro, font_size="12sp", halign="left", valign="top")
        lbl.bind(size=lbl.setter("text_size"))
        return lbl


if __name__ == "__main__":
    try:
        TR4MonitorApp().run()
    except Exception:
        TelaErroApp(traceback.format_exc()).run()
    def limpar_area_central(self):
        self.area_central.clear_widgets()
        self.cards_ui = {}

    def _estilo_btn_pid(self, btn, pid, ativo, com_categoria=False):
        tag = "[ON]  " if ativo else "[OFF] "
        prefixo = f"{pid['categoria']} | " if com_categoria else ""
        btn.text = f"{tag}{prefixo}{pid['nome']} ({pid['cmd']})"
        btn.background_color = (0.14, 0.52, 0.32, 1) if ativo else (0.18, 0.21, 0.27, 1)

    def _alternar_pid_painel(self, btn, pid):
        novo = not self.selecionados.get(pid["id"], False)
        self.selecionados[pid["id"]] = novo
        self._estilo_btn_pid(btn, pid, novo, True)

    def _alternar_pid_log(self, btn, pid):
        novo = not self.selecionados_log.get(pid["id"], False)
        self.selecionados_log[pid["id"]] = novo
        self._estilo_btn_pid(btn, pid, novo, False)

    def mostrar_aba_painel(self, *args):
        self.limpar_area_central()
        scroll = ScrollView()
        colunas = 4 if Window.width > Window.height else 2
        grid = GridLayout(cols=colunas, spacing=6, size_hint_y=None, padding=(2, 4))
        grid.bind(minimum_height=grid.setter("height"))
        for pid in PIDS_DB:
            if not self.selecionados.get(pid["id"], False):
                continue
            card = BoxLayout(orientation="vertical", size_hint_y=None, height=82, padding=6)
            with card.canvas.before:
                Color(0.13, 0.16, 0.21, 1)
                rect = Rectangle(pos=card.pos, size=card.size)
            card.bind(pos=lambda inst, v, r=rect: setattr(r, "pos", v), size=lambda inst, v, r=rect: setattr(r, "size", v))
            lbl_nome = Label(text=pid["nome"], font_size="11sp", color=(0.75, 0.80, 0.88, 1), size_hint_y=0.35)
            lbl_val = Label(text=f"{self.valores_atuais.get(pid['id'], '--')} {pid['unidade']}", font_size="17sp", bold=True, color=(0.15, 0.90, 0.50, 1), size_hint_y=0.65)
            card.add_widget(lbl_nome)
            card.add_widget(lbl_val)
            grid.add_widget(card)
            self.cards_ui[pid["id"]] = (lbl_val, pid["unidade"])
        scroll.add_widget(grid)
        self.area_central.add_widget(scroll)

    def mostrar_aba_seletor(self, *args):
        self.limpar_area_central()
        box = BoxLayout(orientation="vertical", spacing=6)
        acoes = BoxLayout(size_hint_y=0.10, spacing=5)
        for texto, modo, cor in [("MARCAR TODOS", "TODOS", (0.15, 0.55, 0.80, 1)), ("PERFIL RAPIDO", "RAPIDO", (0.20, 0.65, 0.40, 1)), ("DESMARCAR", "NENHUM", (0.65, 0.25, 0.25, 1))]:
            b = Button(text=texto, font_size="11sp", background_normal="", background_color=cor, bold=True)
            b.bind(on_release=lambda x, m=modo: self.definir_todos_pids(m))
            acoes.add_widget(b)
        box.add_widget(acoes)
        scroll = ScrollView()
        lista = GridLayout(cols=1, spacing=6, size_hint_y=None, padding=(2, 4))
        lista.bind(minimum_height=lista.setter("height"))
        self.btns_pid_ui = {}
        for pid in PIDS_DB:
            btn = Button(size_hint_y=None, height=54, font_size="12sp", bold=True, background_normal="", halign="left", valign="middle", padding=(12, 0))
            btn.bind(size=btn.setter("text_size"))
            self._estilo_btn_pid(btn, pid, self.selecionados.get(pid["id"], False), True)
            btn.bind(on_release=lambda inst, p=pid: self._alternar_pid_painel(inst, p))
            lista.add_widget(btn)
            self.btns_pid_ui[pid["id"]] = (btn, pid)
        scroll.add_widget(lista)
        box.add_widget(scroll)
        self.area_central.add_widget(box)

    def definir_todos_pids(self, modo):
        for pid in PIDS_DB:
            estado = True if modo == "TODOS" else (pid["rapido"] if modo == "RAPIDO" else False)
            self.selecionados[pid["id"]] = estado
            if pid["id"] in self.btns_pid_ui:
                btn, p_obj = self.btns_pid_ui[pid["id"]]
                self._estilo_btn_pid(btn, p_obj, estado, True)
    def mostrar_aba_grafico(self, *args):
        self.limpar_area_central()
        self.graficos_lista = []
        self.labels_graf_lista = []
        opcoes = [("STFT", "STFT"), ("SONDA_PRE", "SONDA1"), ("SONDA_POS", "SONDA2"), ("MAP_KPA", "MAP"), ("TI_PRINCIPAL", "INJ"), ("AVANCO_IGN", "IGN"), ("RPM", "RPM"), ("TPS_PCT", "TPS")]
        box = BoxLayout(orientation="vertical", spacing=4)
        for idx in range(3):
            linha_btn = BoxLayout(size_hint_y=0.08, spacing=2)
            for pid_id, rot in opcoes:
                b = Button(text=rot, font_size="9sp", bold=True, background_normal="", background_color=(0.22, 0.28, 0.36, 1))
                b.bind(on_release=lambda x, i=idx, p=pid_id: self.mudar_pid_grafico(i, p))
                linha_btn.add_widget(b)
            lbl = Label(text=f"Canal {idx+1}: {self.pids_graf[idx]}", size_hint_y=0.05, font_size="11sp", bold=True, color=(0.3, 0.9, 0.6, 1))
            graf = GraficoTempoReal(size_hint_y=0.20)
            box.add_widget(linha_btn)
            box.add_widget(lbl)
            box.add_widget(graf)
            self.labels_graf_lista.append(lbl)
            self.graficos_lista.append(graf)
        self.area_central.add_widget(box)

    def mudar_pid_grafico(self, idx, pid_id):
        self.pids_graf[idx] = pid_id
        if hasattr(self, "graficos_lista") and idx < len(self.graficos_lista):
            self.graficos_lista[idx].dados.clear()
        if hasattr(self, "labels_graf_lista") and idx < len(self.labels_graf_lista):
            self.labels_graf_lista[idx].text = f"Canal {idx+1}: {pid_id}"

    def mostrar_aba_log(self, *args):
        self.limpar_area_central()
        box = BoxLayout(orientation="vertical", spacing=5, padding=4)
        self.lbl_log_info = Label(text="Toque na barra do sensor para ativar/desativar no CSV:", font_size="12sp", size_hint_y=0.08)
        box.add_widget(self.lbl_log_info)
        botoes = BoxLayout(size_hint_y=0.11, spacing=6)
        b_ini = Button(text="INICIAR LOG", background_normal="", background_color=(0.18, 0.62, 0.34, 1), bold=True, font_size="12sp")
        b_ini.bind(on_release=self.iniciar_gravacao_log)
        b_parar = Button(text="FECHAR LOG", background_normal="", background_color=(0.78, 0.22, 0.22, 1), bold=True, font_size="12sp")
        b_parar.bind(on_release=self.parar_gravacao_log)
        botoes.add_widget(b_ini)
        botoes.add_widget(b_parar)
        box.add_widget(botoes)
        acoes = BoxLayout(size_hint_y=0.09, spacing=4)
        for txt, modo, cor in [("TODOS", "TODOS", (0.15, 0.55, 0.80, 1)), ("LOG RAPIDO", "RAPIDO", (0.20, 0.65, 0.40, 1)), ("DESMARCAR", "NENHUM", (0.65, 0.25, 0.25, 1))]:
            b = Button(text=txt, font_size="10sp", background_normal="", background_color=cor, bold=True)
            b.bind(on_release=lambda x, m=modo: self.definir_pids_log(m))
            acoes.add_widget(b)
        box.add_widget(acoes)
        scroll = ScrollView(size_hint_y=0.72)
        lista = GridLayout(cols=1, spacing=6, size_hint_y=None, padding=(2, 4))
        lista.bind(minimum_height=lista.setter("height"))
        self.btns_log_ui = {}
        for pid in PIDS_DB:
            btn = Button(size_hint_y=None, height=50, font_size="12sp", bold=True, background_normal="", halign="left", valign="middle", padding=(12, 0))
            btn.bind(size=btn.setter("text_size"))
            self._estilo_btn_pid(btn, pid, self.selecionados_log.get(pid["id"], False), False)
            btn.bind(on_release=lambda inst, p=pid: self._alternar_pid_log(inst, p))
            lista.add_widget(btn)
            self.btns_log_ui[pid["id"]] = (btn, pid)
        scroll.add_widget(lista)
        box.add_widget(scroll)
        self.area_central.add_widget(box)

    def definir_pids_log(self, modo):
        for pid in PIDS_DB:
            estado = True if modo == "TODOS" else (pid["rapido"] if modo == "RAPIDO" else False)
            self.selecionados_log[pid["id"]] = estado
            if pid["id"] in self.btns_log_ui:
                btn, p_obj = self.btns_log_ui[pid["id"]]
                self._estilo_btn_pid(btn, p_obj, estado, False)

    def mostrar_aba_engenharia(self, *args):
        self.limpar_area_central()
        box = BoxLayout(orientation="vertical", spacing=8, padding=8)
        self.lbl_eng = Label(text="Modulo de Engenharia IAW 4AM.AR (SW 4AMMS)\nSessao Estendida KWP2000 (10 81)", font_size="12sp", size_hint_y=0.55)
        box.add_widget(self.lbl_eng)
        botoes = BoxLayout(size_hint_y=0.20, spacing=8)
        b_dtc = Button(text="LER FALHAS (DTC)", background_normal="", background_color=(0.15, 0.50, 0.80, 1), bold=True)
        b_dtc.bind(on_release=self.ler_dtcs)
        b_clear = Button(text="APAGAR FALHAS", background_normal="", background_color=(0.80, 0.40, 0.12, 1), bold=True)
        b_clear.bind(on_release=self.apagar_dtcs)
        botoes.add_widget(b_dtc)
        botoes.add_widget(b_clear)
        box.add_widget(botoes)
        b_scan = Button(text="VARRER ECU (2100 - 21FF) E SALVAR MAPA", size_hint_y=0.18, background_normal="", background_color=(0.20, 0.62, 0.45, 1), bold=True)
        b_scan.bind(on_release=self.iniciar_varredura_ecu)
        box.add_widget(b_scan)
        self.area_central.add_widget(box)


class TelaErroApp(App):
    def __init__(self, msg_erro, **kwargs):
        super().__init__(**kwargs)
        self.msg_erro = msg_erro

    def build(self):
        lbl = Label(text=self.msg_erro, font_size="12sp", halign="left", valign="top")
        lbl.bind(size=lbl.setter("text_size"))
        return lbl


if __name__ == "__main__":
    try:
        TR4MonitorApp().run()
    except Exception:
        TelaErroApp(traceback.format_exc()).run()
