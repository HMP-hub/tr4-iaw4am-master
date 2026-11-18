# coding: utf-8
import threading
from operator import itemgetter
from kivy.app import App
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.graphics import Color, Line, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.checkbox import CheckBox
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget

from pids import PIDS_DB
from engine import TR4EngineMixin

Window.clearcolor = (0.08, 0.09, 0.11, 1)


def manter_tela_acesa():
    try:
        from jnius import autoclass
        from android.runnable import run_on_ui_thread

        @run_on_ui_thread
        def _set_flag():
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            WindowManagerParams = autoclass("android.view.WindowManager$LayoutParams")
            activity = PythonActivity.mActivity
            if activity:
                activity.getWindow().addFlags(WindowManagerParams.FLAG_KEEP_SCREEN_ON)

        _set_flag()
    except Exception:
        pass


class GraficoRealtime(Widget):
    def __init__(self, cor_linha=(0.2, 0.85, 0.45, 1), max_pontos=90, **kwargs):
        super().__init__(**kwargs)
        self.cor_linha = cor_linha
        self.max_pontos = max_pontos
        self.pontos = []
        self.lbl_info = Label(
            text="--",
            font_size="12sp",
            bold=True,
            color=(0.95, 0.95, 0.95, 1),
            halign="left",
            valign="top",
        )
        self.add_widget(self.lbl_info)
        self.bind(pos=self._reposicionar, size=self._reposicionar)

    def _reposicionar(self, *args):
        self.lbl_info.pos = (self.x + dp(8), self.top - dp(24))
        self.lbl_info.size = (self.width - dp(16), dp(20))
        self.lbl_info.text_size = self.lbl_info.size
        self._desenhar()

    def limpar(self):
        self.pontos = []
        self.lbl_info.text = "--"
        self._desenhar()

    def adicionar_ponto(self, val):
        self.pontos.append(float(val))
        if len(self.pontos) > self.max_pontos:
            self.pontos.pop(0)
        vmin = min(self.pontos)
        vmax = max(self.pontos)
        self.lbl_info.text = f"Atual: {val}   |   Min: {vmin}   |   Max: {vmax}"
        self._desenhar()

    def _desenhar(self):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(0.12, 0.14, 0.18, 1)
            Rectangle(pos=self.pos, size=self.size)
            Color(0.22, 0.25, 0.30, 1)
            for frac in (0.25, 0.5, 0.75):
                y_grid = self.y + self.height * frac
                Line(points=[self.x, y_grid, self.right, y_grid], width=1)

            if len(self.pontos) >= 2:
                vmin = min(self.pontos)
                vmax = max(self.pontos)
                if vmax - vmin < 1e-6:
                    vmax = vmin + 1.0
                pad_y = dp(10)
                altura_util = max(dp(10), self.height - dp(32))
                passo_x = self.width / max(1, self.max_pontos - 1)
                coords = []
                for idx, v in enumerate(self.pontos):
                    px = self.x + idx * passo_x
                    norm = (v - vmin) / (vmax - vmin)
                    py = self.y + pad_y + norm * altura_util
                    coords.extend([px, py])
                Color(*self.cor_linha)
                Line(points=coords, width=dp(1.8))


class TR4ScannerApp(App, TR4EngineMixin):
    def on_start(self):
        manter_tela_acesa()

    def on_resume(self):
        manter_tela_acesa()
        return True
    def build(self):
        manter_tela_acesa()
        self.title = "TR4 IAW4AM Master"
        self.bt_lock = threading.Lock()
        self.bt_socket = None
        self.bt_in = None
        self.bt_out = None
        self.bt_salvo_addr = ""
        self.bt_salvo_nome = ""
        self.estado_conexao = "DESCONECTADO"
        self.cancelar_conexao = False
        self.rodando = False
        self.varrendo = False
        self.modo_simulacao = False
        self.gravando_log = False
        self.log_pausado = False
        self.arquivo_log = None
        self.writer_log = None

        self.valores_atuais = {p["id"]: "--" for p in PIDS_DB}
        self.valores_min = {}
        self.valores_max = {}
        self.selecionados = {p["id"]: p["rapido"] for p in PIDS_DB}
        self.selecionados_log = {p["id"]: p["rapido"] for p in PIDS_DB}
        self.cards_ui = {}

        self._carregar_bt_salvo()
        self._init_telemetria_viagem()

        root = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(6))

        self.lbl_status = Label(
            text="DESCONECTADO | ECU: IAW 4AM.AR (4AMMS)",
            size_hint_y=None,
            height=dp(28),
            font_size="12sp",
            bold=True,
            color=(1, 0.78, 0.2, 1),
        )
        root.add_widget(self.lbl_status)

        barra_con = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        self.btn_bt_lista = Button(
            text="ESCOLHER\nBLUETOOTH",
            font_size="12sp",
            bold=True,
            halign="center",
            background_normal="",
            background_color=(0.12, 0.45, 0.78, 1),
        )
        self.btn_bt_lista.bind(on_release=self.conectar_bluetooth)

        self.btn_acao_con = Button(
            text="CONECTAR",
            font_size="13sp",
            bold=True,
            halign="center",
            background_normal="",
            background_color=(0.14, 0.62, 0.35, 1),
        )
        self.btn_acao_con.bind(on_release=self.acao_botao_conexao)

        btn_sim = Button(
            text="SIMULACAO",
            font_size="12sp",
            bold=True,
            background_normal="",
            background_color=(0.45, 0.25, 0.68, 1),
        )
        btn_sim.bind(on_release=self.iniciar_simulacao)

        barra_con.add_widget(self.btn_bt_lista)
        barra_con.add_widget(self.btn_acao_con)
        barra_con.add_widget(btn_sim)
        root.add_widget(barra_con)

        barra_abas = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(4))
        self.sm = ScreenManager(transition=NoTransition())
        self.btns_abas = {}
        abas_def = [
            ("painel", "PAINEL"),
            ("pids", "PIDS"),
            ("grafico", "GRAFICO"),
            ("log", "LOG CSV"),
            ("boletim", "BOLETIM"),
            ("eng", "ENG/DTC"),
        ]
        for nome_scr, rotulo in abas_def:
            b = Button(
                text=rotulo,
                font_size="11sp",
                bold=True,
                background_normal="",
                background_color=(0.18, 0.21, 0.27, 1),
            )
            b.bind(on_release=lambda inst, n=nome_scr: self.trocar_aba(n))
            self.btns_abas[nome_scr] = b
            barra_abas.add_widget(b)
        root.add_widget(barra_abas)

        self.sm.add_widget(self._criar_tela_painel())
        self.sm.add_widget(self._criar_tela_pids())
        self.sm.add_widget(self._criar_tela_grafico())
        self.sm.add_widget(self._criar_tela_log())
        self.sm.add_widget(self._criar_tela_boletim())
        self.sm.add_widget(self._criar_tela_eng())
        root.add_widget(self.sm)

        self._atualizar_estado_conexao("DESCONECTADO")
        self.trocar_aba("painel")
        return root

    def trocar_aba(self, nome_scr):
        self.sm.current = nome_scr
        for k, btn in self.btns_abas.items():
            btn.background_color = (0.16, 0.52, 0.78, 1) if k == nome_scr else (0.18, 0.21, 0.27, 1)
        if nome_scr == "boletim":
            self.atualizar_tela_boletim()

    def _criar_tela_painel(self):
        scr = Screen(name="painel")
        box = BoxLayout(orientation="vertical", spacing=dp(6))

        btn_zerar = Button(
            text="ZERAR MIN / MAX",
            size_hint_y=None,
            height=dp(36),
            font_size="12sp",
            bold=True,
            background_normal="",
            background_color=(0.24, 0.28, 0.36, 1),
        )
        btn_zerar.bind(on_release=self.zerar_min_max)
        box.add_widget(btn_zerar)

        scroll = ScrollView(bar_width=dp(5))
        self.grid_painel = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, padding=(dp(2), dp(2)))
        self.grid_painel.bind(minimum_height=self.grid_painel.setter("height"))
        scroll.add_widget(self.grid_painel)
        box.add_widget(scroll)

        self._reconstruir_cards_painel()
        scr.add_widget(box)
        return scr
    def _reconstruir_cards_painel(self):
        self.grid_painel.clear_widgets()
        self.cards_ui = {}
        for p in PIDS_DB:
            pid_id = p["id"]
            if not self.selecionados.get(pid_id, False):
                continue
            card = BoxLayout(
                orientation="vertical",
                size_hint_y=None,
                height=dp(106),
                padding=(dp(6), dp(6)),
                spacing=dp(2),
            )
            with card.canvas.before:
                Color(0.13, 0.15, 0.20, 1)
                bg = Rectangle(pos=card.pos, size=card.size)
            card.bind(pos=lambda inst, v, r=bg: setattr(r, "pos", v))
            card.bind(size=lambda inst, v, r=bg: setattr(r, "size", v))

            lbl_nome = Label(
                text=p["nome"],
                font_size="13sp",
                bold=True,
                color=(0.82, 0.87, 0.94, 1),
                halign="center",
                valign="middle",
                size_hint_y=0.36,
            )
            lbl_nome.bind(size=lambda inst, v: setattr(inst, "text_size", v))

            lbl_val = Label(
                text="--",
                font_size="21sp",
                bold=True,
                color=(0.25, 0.92, 0.55, 1),
                halign="center",
                valign="middle",
                size_hint_y=0.40,
            )
            lbl_val.bind(size=lambda inst, v: setattr(inst, "text_size", v))

            rodape = BoxLayout(size_hint_y=0.24)
            lbl_min = Label(text="MIN: --", font_size="10sp", color=(0.55, 0.75, 0.95, 1), halign="left")
            lbl_max = Label(text="MAX: --", font_size="10sp", color=(0.95, 0.65, 0.45, 1), halign="right")
            rodape.add_widget(lbl_min)
            rodape.add_widget(lbl_max)

            card.add_widget(lbl_nome)
            card.add_widget(lbl_val)
            card.add_widget(rodape)
            self.grid_painel.add_widget(card)
            self.cards_ui[pid_id] = (lbl_val, lbl_min, lbl_max, p["unidade"])

    def _criar_tela_pids(self):
        scr = Screen(name="pids")
        box = BoxLayout(orientation="vertical", spacing=dp(6))

        top_btns = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(5))
        b_rap = Button(
            text="PADRAO\nRAPIDO",
            font_size="10.5sp",
            bold=True,
            halign="center",
            background_normal="",
            background_color=(0.15, 0.48, 0.72, 1),
        )
        b_rap.bind(on_release=lambda *a: self._aplicar_preset_pids("rapido"))

        b_todos = Button(
            text="MARCAR\nTODOS",
            font_size="10.5sp",
            bold=True,
            halign="center",
            background_normal="",
            background_color=(0.18, 0.55, 0.35, 1),
        )
        b_todos.bind(on_release=lambda *a: self._aplicar_preset_pids("todos"))

        b_nenhum = Button(
            text="DESMARCAR\nTODOS",
            font_size="10.5sp",
            bold=True,
            halign="center",
            background_normal="",
            background_color=(0.68, 0.24, 0.24, 1),
        )
        b_nenhum.bind(on_release=lambda *a: self._aplicar_preset_pids("nenhum"))

        top_btns.add_widget(b_rap)
        top_btns.add_widget(b_todos)
        top_btns.add_widget(b_nenhum)
        box.add_widget(top_btns)

        scroll = ScrollView(bar_width=dp(6))
        lista = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        lista.bind(minimum_height=lista.setter("height"))
        self.checks_pids = {}

        for p in PIDS_DB:
            pid_id = p["id"]
            linha = BoxLayout(size_hint_y=None, height=dp(42), padding=(dp(6), 0))
            chk = CheckBox(active=self.selecionados.get(pid_id, False), size_hint_x=0.14)
            chk.bind(active=lambda inst, val, k=pid_id: self._toggle_pid_painel(k, val))
            self.checks_pids[pid_id] = chk

            lbl = Label(
                text=f"{p['nome']} ({p['unidade']})",
                font_size="12sp",
                halign="left",
                valign="middle",
                size_hint_x=0.86,
            )
            lbl.bind(size=lambda inst, v: setattr(inst, "text_size", v))
            linha.add_widget(chk)
            linha.add_widget(lbl)
            lista.add_widget(linha)

        scroll.add_widget(lista)
        box.add_widget(scroll)
        scr.add_widget(box)
        return scr

    def _toggle_pid_painel(self, pid_id, ativo):
        self.selecionados[pid_id] = bool(ativo)
        self._reconstruir_cards_painel()

    def _aplicar_preset_pids(self, modo):
        for p in PIDS_DB:
            pid_id = p["id"]
            if modo == "todos":
                novo = True
            elif modo == "nenhum":
                novo = False
            else:
                novo = p["rapido"]
            self.selecionados[pid_id] = novo
            if pid_id in self.checks_pids:
                self.checks_pids[pid_id].active = novo
        self._reconstruir_cards_painel()

    def _criar_tela_grafico(self):
        scr = Screen(name="grafico")
        box = BoxLayout(orientation="vertical", spacing=dp(4))

        opcoes = [p["nome"] for p in PIDS_DB]
        self.mapa_spinner_pid = {p["nome"]: p["id"] for p in PIDS_DB}
        self.pids_graf = ["RPM", "AVANCO", "MAP"]
        self.graficos_lista = []
        cores = [
            (0.22, 0.88, 0.48, 1),
            (0.95, 0.55, 0.22, 1),
            (0.28, 0.72, 0.98, 1),
        ]

        for idx in range(3):
            pid_ini = itemgetter(idx)(self.pids_graf)
            texto_ini = next((k for k, v in self.mapa_spinner_pid.items() if v == pid_ini), itemgetter(0)(opcoes))
            sp = Spinner(
                text=texto_ini,
                values=opcoes,
                size_hint_y=None,
                height=dp(32),
                font_size="11.5sp",
                bold=True,
                background_normal="",
                background_color=(0.18, 0.24, 0.34, 1),
            )
            graf = GraficoRealtime(cor_linha=itemgetter(idx)(cores))
            sp.bind(text=lambda inst, txt, i=idx, g=graf: self._trocar_pid_grafico(i, txt, g))
            self.graficos_lista.append(graf)
            box.add_widget(sp)
            box.add_widget(graf)

        scr.add_widget(box)
        return scr
    def _trocar_pid_grafico(self, idx, texto_sel, graf_widget):
        pid_id = self.mapa_spinner_pid.get(texto_sel)
        if pid_id:
            self.pids_graf[idx] = pid_id
            self.selecionados[pid_id] = True
            if pid_id in self.checks_pids:
                self.checks_pids[pid_id].active = True
            self._reconstruir_cards_painel()
            graf_widget.limpar()

    def _criar_tela_log(self):
        scr = Screen(name="log")
        box = BoxLayout(orientation="vertical", spacing=dp(6))

        self.lbl_log_status_bar = Label(
            text="STATUS LOG: PARADO (00:00  |  0 linhas)",
            size_hint_y=None,
            height=dp(28),
            font_size="12.5sp",
            bold=True,
            color=(0.75, 0.80, 0.88, 1),
        )
        box.add_widget(self.lbl_log_status_bar)

        self.lbl_log_info = Label(
            text="Selecione os PIDs abaixo e clique em INICIAR LOG CSV.\nOs arquivos sao salvos em /sdcard/Download.",
            size_hint_y=None,
            height=dp(48),
            font_size="11.5sp",
            halign="left",
            valign="middle",
        )
        self.lbl_log_info.bind(size=lambda inst, v: setattr(inst, "text_size", v))
        box.add_widget(self.lbl_log_info)

        barra_log = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        b_ini = Button(
            text="INICIAR /\nCONTINUAR",
            font_size="11sp",
            bold=True,
            halign="center",
            background_normal="",
            background_color=(0.14, 0.62, 0.35, 1),
        )
        b_ini.bind(on_release=self.iniciar_gravacao_log)

        b_pausa = Button(
            text="PAUSAR",
            font_size="11sp",
            bold=True,
            background_normal="",
            background_color=(0.82, 0.52, 0.14, 1),
        )
        b_pausa.bind(on_release=self.pausar_gravacao_log)

        b_parar = Button(
            text="SALVAR E\nENCERRAR",
            font_size="11sp",
            bold=True,
            halign="center",
            background_normal="",
            background_color=(0.76, 0.22, 0.22, 1),
        )
        b_parar.bind(on_release=self.parar_gravacao_log)

        barra_log.add_widget(b_ini)
        barra_log.add_widget(b_pausa)
        barra_log.add_widget(b_parar)
        box.add_widget(barra_log)

        barra_sel_log = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(5))
        bl_rap = Button(
            text="PADRAO\nRAPIDO",
            font_size="10.5sp",
            bold=True,
            halign="center",
            background_normal="",
            background_color=(0.15, 0.48, 0.72, 1),
        )
        bl_rap.bind(on_release=lambda *a: self._aplicar_preset_log("rapido"))

        bl_todos = Button(
            text="MARCAR\nTODOS",
            font_size="10.5sp",
            bold=True,
            halign="center",
            background_normal="",
            background_color=(0.18, 0.55, 0.35, 1),
        )
        bl_todos.bind(on_release=lambda *a: self._aplicar_preset_log("todos"))

        bl_nenhum = Button(
            text="DESMARCAR\nTODOS",
            font_size="10.5sp",
            bold=True,
            halign="center",
            background_normal="",
            background_color=(0.68, 0.24, 0.24, 1),
        )
        bl_nenhum.bind(on_release=lambda *a: self._aplicar_preset_log("nenhum"))

        barra_sel_log.add_widget(bl_rap)
        barra_sel_log.add_widget(bl_todos)
        barra_sel_log.add_widget(bl_nenhum)
        box.add_widget(barra_sel_log)

        scroll = ScrollView(bar_width=dp(6))
        lista = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        lista.bind(minimum_height=lista.setter("height"))
        self.checks_log = {}

        for p in PIDS_DB:
            pid_id = p["id"]
            linha = BoxLayout(size_hint_y=None, height=dp(38), padding=(dp(6), 0))
            chk = CheckBox(active=self.selecionados_log.get(pid_id, False), size_hint_x=0.14)
            chk.bind(active=lambda inst, val, k=pid_id: self.selecionados_log.update({k: bool(val)}))
            self.checks_log[pid_id] = chk

            lbl = Label(
                text=f"{p['nome']} ({p['unidade']})",
                font_size="12sp",
                halign="left",
                valign="middle",
                size_hint_x=0.86,
            )
            lbl.bind(size=lambda inst, v: setattr(inst, "text_size", v))
            linha.add_widget(chk)
            linha.add_widget(lbl)
            lista.add_widget(linha)
        scroll.add_widget(lista)
        box.add_widget(scroll)
        scr.add_widget(box)
        return scr

    def _aplicar_preset_log(self, modo):
        for p in PIDS_DB:
            pid_id = p["id"]
            if modo == "todos":
                novo = True
            elif modo == "nenhum":
                novo = False
            else:
                novo = p["rapido"]
            self.selecionados_log[pid_id] = novo
            if pid_id in self.checks_log:
                self.checks_log[pid_id].active = novo

    def _criar_tela_boletim(self):
        scr = Screen(name="boletim")
        box = BoxLayout(orientation="vertical", spacing=dp(6))

        scroll = ScrollView(bar_width=dp(6))
        self.lbl_boletim = Label(
            text="Conecte ao veiculo para iniciar o monitoramento automatico.",
            font_size="13sp",
            halign="left",
            valign="top",
            size_hint_y=None,
            padding=(dp(8), dp(8)),
        )
        self.lbl_boletim.bind(width=lambda inst, w: setattr(inst, "text_size", (w, None)))
        self.lbl_boletim.bind(texture_size=lambda inst, ts: setattr(inst, "height", max(dp(260), itemgetter(1)(ts) + dp(16))))
        scroll.add_widget(self.lbl_boletim)
        box.add_widget(scroll)

        barra_bol = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        b_atu = Button(
            text="ATUALIZAR",
            font_size="12sp",
            bold=True,
            background_normal="",
            background_color=(0.15, 0.48, 0.72, 1),
        )
        b_atu.bind(on_release=lambda *a: self.atualizar_tela_boletim())

        b_zer = Button(
            text="NOVA VIAGEM",
            font_size="12sp",
            bold=True,
            background_normal="",
            background_color=(0.80, 0.48, 0.14, 1),
        )
        b_zer.bind(on_release=self.reiniciar_telemetria_viagem)

        b_sal = Button(
            text="SALVAR TXT",
            font_size="12sp",
            bold=True,
            background_normal="",
            background_color=(0.14, 0.62, 0.35, 1),
        )
        b_sal.bind(on_release=self.salvar_boletim_txt)

        barra_bol.add_widget(b_atu)
        barra_bol.add_widget(b_zer)
        barra_bol.add_widget(b_sal)
        box.add_widget(barra_bol)

        scr.add_widget(box)
        return scr

    def _criar_tela_eng(self):
        scr = Screen(name="eng")
        box = BoxLayout(orientation="vertical", spacing=dp(6))

        scroll = ScrollView(size_hint_y=0.44, bar_width=dp(6))
        self.lbl_eng = Label(
            text="Diagnostico Avancado KWP2000 - ECU IAW 4AM\n\nSelecione uma operacao abaixo:",
            font_size="13sp",
            halign="left",
            valign="top",
            size_hint_y=None,
            padding=(dp(8), dp(8)),
        )
        self.lbl_eng.bind(width=lambda inst, w: setattr(inst, "text_size", (w, None)))
        self.lbl_eng.bind(texture_size=lambda inst, ts: setattr(inst, "height", max(dp(180), itemgetter(1)(ts) + dp(16))))
        scroll.add_widget(self.lbl_eng)
        box.add_widget(scroll)

        grid_btns = GridLayout(cols=2, spacing=dp(8), size_hint_y=0.56)
        botoes_eng = [
            ("LER FALHAS (DTC)", (0.12, 0.46, 0.78, 1), self.ler_dtcs),
            ("APAGAR FALHAS", (0.82, 0.38, 0.12, 1), self.apagar_dtcs),
            ("INFO ECU E ODOMETRO", (0.42, 0.24, 0.64, 1), self.ler_info_ecu),
            ("BUSCAR MODULOS", (0.20, 0.48, 0.60, 1), self.buscar_modulos_kwp),
            ("CAPTURAR CALIBRACAO\n(4 ESTADOS + MODO 01)", (0.08, 0.62, 0.58, 1), self.capturar_calibracao_ecu),
            ("SALVAR BOLETIM TXT", (0.24, 0.42, 0.56, 1), self.salvar_boletim_txt),
            ("VARRER ECU", (0.14, 0.58, 0.36, 1), self.iniciar_varredura_ecu),
            ("PARAR VARREDURA", (0.76, 0.22, 0.22, 1), self.parar_varredura_ecu),
        ]
        for titulo, cor, callback in botoes_eng:
            btn = Button(
                text=titulo,
                font_size="12sp",
                bold=True,
                halign="center",
                background_normal="",
                background_color=cor,
            )
            btn.bind(on_release=callback)
            grid_btns.add_widget(btn)

        box.add_widget(grid_btns)
        scr.add_widget(box)
        return scr


if __name__ == "__main__":
    TR4ScannerApp().run()
