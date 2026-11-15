# coding: utf-8
import threading
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.togglebutton import ToggleButton
from kivy.graphics import Color, Line, Rectangle
from kivy.core.window import Window

from pids import PIDS_DB
from engine import TR4EngineMixin

Window.clearcolor = (0.07, 0.08, 0.10, 1)


class GraficoTempoReal(BoxLayout):
    def __init__(self, titulo, unidade, cor_linha, min_v, max_v, **kwargs):
        super().__init__(orientation="vertical", padding=6, spacing=2, **kwargs)
        self.titulo = titulo
        self.unidade = unidade
        self.cor_linha = cor_linha
        self.min_v = min_v
        self.max_v = max_v
        self.historico = []
        self.max_pontos = 80

        self.lbl_topo = Label(
            text=f"{titulo}: -- {unidade}",
            size_hint_y=0.22,
            bold=True,
            color=cor_linha,
            font_size="14sp",
        )
        self.add_widget(self.lbl_topo)

        self.area = BoxLayout(size_hint_y=0.78)
        self.add_widget(self.area)
        self.area.bind(pos=self.desenhar, size=self.desenhar)

    def adicionar_ponto(self, valor):
        self.historico.append(valor)
        if len(self.historico) > self.max_pontos:
            self.historico.pop(0)
        self.lbl_topo.text = f"{self.titulo}: {valor} {self.unidade}"
        self.desenhar()

    def desenhar(self, *args):
        self.area.canvas.clear()
        x0, y0 = self.area.pos
        w, h = self.area.size
        if w <= 10 or h <= 10:
            return
        with self.area.canvas:
            Color(0.12, 0.14, 0.18, 1)
            Rectangle(pos=(x0, y0), size=(w, h))
            Color(0.25, 0.28, 0.34, 1)
            Line(rectangle=(x0, y0, w, h), width=1)
            Line(points=[x0, y0 + h * 0.5, x0 + w, y0 + h * 0.5], width=1)

            if len(self.historico) >= 2:
                vmin = min(self.min_v, min(self.historico))
                vmax = max(self.max_v, max(self.historico))
                if vmax == vmin:
                    vmax = vmin + 1
                pontos = []
                passo_x = w / float(self.max_pontos - 1)
                for i, val in enumerate(self.historico):
                    px = x0 + i * passo_x
                    norm = (val - vmin) / float(vmax - vmin)
                    py = y0 + norm * (h - 8) + 4
                    pontos.extend([px, py])
                Color(*self.cor_linha)
                Line(points=pontos, width=1.8)


class TR4ScannerApp(TR4EngineMixin, App):
    def build(self):
        self.title = "TR4 IAW4AM Master"
        self.rodando = False
        self.varrendo = False
        self.modo_simulacao = False
        self.gravando_log = False
        self.log_pausado = False
        self.linhas_gravadas_log = 0
        self.caminho_log_atual = ""
        self.arquivo_log = None
        self.writer_log = None
        self.bt_lock = threading.Lock()
        self.bt_socket = None
        self.bt_in = None
        self.bt_out = None

        self.valores_atuais = {p["id"]: "--" for p in PIDS_DB}
        self.valores_min = {}
        self.valores_max = {}
        self.selecionados = {p["id"]: p["rapido"] for p in PIDS_DB}
        self.selecionados_log = {p["id"]: p["rapido"] for p in PIDS_DB}
        self.cards_ui = {}
        self.checks_pids_ui = {}
        self.checks_log_ui = {}

        raiz = BoxLayout(orientation="vertical", padding=6, spacing=6)

        self.lbl_status = Label(
            text="DESCONECTADO | ECU: IAW 4AM.AR (4AMMS)",
            size_hint_y=0.055,
            bold=True,
            color=(1, 0.78, 0.2, 1),
            font_size="13sp",
        )
        raiz.add_widget(self.lbl_status)

        barra_con = BoxLayout(size_hint_y=0.075, spacing=5)
        btn_bt = Button(text="CONEXAO\nBLUETOOTH", background_normal="", background_color=(0.12, 0.45, 0.80, 1), font_size="11sp", bold=True, halign="center")
        btn_bt.bind(on_release=self.conectar_bluetooth)

        btn_ecu = Button(text="CONECTAR\nECU", background_normal="", background_color=(0.14, 0.62, 0.35, 1), font_size="11sp", bold=True, halign="center")
        btn_ecu.bind(on_release=self.conectar_ecu)

        btn_desc = Button(text="DESCONECTAR\nECU", background_normal="", background_color=(0.75, 0.22, 0.22, 1), font_size="11sp", bold=True, halign="center")
        btn_desc.bind(on_release=self.desconectar_ecu)

        btn_sim = Button(text="SIMULACAO", background_normal="", background_color=(0.45, 0.30, 0.72, 1), font_size="11sp", bold=True)
        btn_sim.bind(on_release=self.iniciar_simulacao)

        barra_con.add_widget(btn_bt)
        barra_con.add_widget(btn_ecu)
        barra_con.add_widget(btn_desc)
        barra_con.add_widget(btn_sim)
        raiz.add_widget(barra_con)
        barra_abas = BoxLayout(size_hint_y=0.065, spacing=4)
        self.botoes_aba = {}
        for aba_id, aba_nome in [
            ("PAINEL", "PAINEL"),
            ("SELETOR", "PIDS"),
            ("GRAFICOS", "GRAFICO"),
            ("LOG", "LOG CSV"),
            ("ENGENHARIA", "ENG/DTC"),
        ]:
            b = Button(text=aba_nome, background_normal="", background_color=(0.18, 0.21, 0.27, 1), font_size="12sp", bold=True)
            b.bind(on_release=lambda inst, x=aba_id: self.trocar_aba(x))
            self.botoes_aba[aba_id] = b
            barra_abas.add_widget(b)
        raiz.add_widget(barra_abas)

        self.area_conteudo = BoxLayout(size_hint_y=0.805)
        raiz.add_widget(self.area_conteudo)

        self.telas = {
            "PAINEL": self._criar_tela_painel(),
            "SELETOR": self._criar_tela_seletor(),
            "GRAFICOS": self._criar_tela_graficos(),
            "LOG": self._criar_tela_log(),
            "ENGENHARIA": self._criar_tela_engenharia(),
        }

        self.trocar_aba("PAINEL")
        return raiz

    def trocar_aba(self, aba_id):
        self.area_conteudo.clear_widgets()
        self.area_conteudo.add_widget(self.telas[aba_id])
        for k, btn in self.botoes_aba.items():
            btn.background_color = (0.15, 0.55, 0.75, 1) if k == aba_id else (0.18, 0.21, 0.27, 1)
        if aba_id == "PAINEL":
            self._reconstruir_cards_painel()

    def _criar_tela_painel(self):
        box = BoxLayout(orientation="vertical", spacing=6)
        btn_zerar = Button(
            text="ZERAR MIN / MAX",
            size_hint_y=0.075,
            background_normal="",
            background_color=(0.24, 0.28, 0.36, 1),
            bold=True,
            font_size="13sp",
        )
        btn_zerar.bind(on_release=self.zerar_min_max)
        box.add_widget(btn_zerar)

        scroll = ScrollView(size_hint_y=0.925)
        self.grid_painel = GridLayout(cols=2, spacing=6, size_hint_y=None, padding=2)
        self.grid_painel.bind(minimum_height=self.grid_painel.setter("height"))
        scroll.add_widget(self.grid_painel)
        box.add_widget(scroll)
        return box

    def _reconstruir_cards_painel(self):
        self.grid_painel.clear_widgets()
        self.cards_ui = {}
        for pid in PIDS_DB:
            if not self.selecionados.get(pid["id"], False):
                continue
            card = BoxLayout(orientation="vertical", size_hint_y=None, height=96, padding=6)
            with card.canvas.before:
                Color(0.13, 0.15, 0.20, 1)
                rect = Rectangle(pos=card.pos, size=card.size)
            card.bind(pos=lambda inst, val, r=rect: setattr(r, "pos", val))
            card.bind(size=lambda inst, val, r=rect: setattr(r, "size", val))

            lbl_nome = Label(text=pid["nome"], size_hint_y=0.28, font_size="12sp", color=(0.75, 0.80, 0.88, 1), bold=True)
            val_atual = self.valores_atuais.get(pid["id"], "--")
            txt_val = f"{val_atual} {pid['unidade']}" if val_atual != "--" else "--"
            lbl_val = Label(text=txt_val, size_hint_y=0.46, font_size="22sp", bold=True, color=(0.30, 0.92, 0.55, 1))
            vmin = self.valores_min.get(pid["id"], "--")
            vmax = self.valores_max.get(pid["id"], "--")
            lbl_mm = Label(text=f"MIN: {vmin}   |   MAX: {vmax}", size_hint_y=0.26, font_size="11sp", color=(0.60, 0.68, 0.78, 1))

            card.add_widget(lbl_nome)
            card.add_widget(lbl_val)
            card.add_widget(lbl_mm)
            self.grid_painel.add_widget(card)
            self.cards_ui[pid["id"]] = (lbl_val, lbl_mm, pid["unidade"])

    def _criar_tela_seletor(self):
        box = BoxLayout(orientation="vertical", spacing=6)
        barra_presets = BoxLayout(size_hint_y=0.08, spacing=5)
        b_rap = Button(text="PRESET RAPIDO", background_normal="", background_color=(0.15, 0.52, 0.70, 1), font_size="12sp", bold=True)
        b_rap.bind(on_release=lambda x: self._aplicar_preset("RAPIDO"))
        b_todos = Button(text="MARCAR TODOS", background_normal="", background_color=(0.20, 0.58, 0.35, 1), font_size="12sp", bold=True)
        b_todos.bind(on_release=lambda x: self._aplicar_preset("TODOS"))
        b_limpar = Button(text="DESMARCAR", background_normal="", background_color=(0.65, 0.25, 0.25, 1), font_size="12sp", bold=True)
        b_limpar.bind(on_release=lambda x: self._aplicar_preset("NENHUM"))
        barra_presets.add_widget(b_rap)
        barra_presets.add_widget(b_todos)
        barra_presets.add_widget(b_limpar)
        box.add_widget(barra_presets)

        scroll = ScrollView(size_hint_y=0.92)
        grid = GridLayout(cols=1, spacing=4, size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))
        for pid in PIDS_DB:
            tb = ToggleButton(
                text=f"  {pid['nome']} ({pid['unidade']})",
                size_hint_y=None,
                height=48,
                state="down" if self.selecionados[pid["id"]] else "normal",
                font_size="14sp",
                halign="left",
                valign="middle",
                padding=(14, 0),
            )
            tb.bind(size=tb.setter("text_size"))
            tb.bind(state=lambda inst, st, pid_id=pid["id"]: self._toggle_pid(pid_id, st))
            self.checks_pids_ui[pid["id"]] = tb
            grid.add_widget(tb)
        scroll.add_widget(grid)
        box.add_widget(scroll)
        return box

    def _toggle_pid(self, pid_id, state):
        self.selecionados[pid_id] = (state == "down")

    def _aplicar_preset(self, tipo):
        for pid in PIDS_DB:
            pid_id = pid["id"]
            if tipo == "RAPIDO":
                ativo = pid["rapido"]
            elif tipo == "TODOS":
                ativo = True
            else:
                ativo = False
            self.selecionados[pid_id] = ativo
            self.checks_pids_ui[pid_id].state = "down" if ativo else "normal"
    def _criar_tela_graficos(self):
        box = BoxLayout(orientation="vertical", spacing=6)
        self.graficos_lista = [
            GraficoTempoReal("Rotacao (RPM)", "rpm", (0.25, 0.85, 1.0, 1), 0, 6000),
            GraficoTempoReal("Sonda Lambda Pre-Cat", "mV", (0.30, 0.95, 0.45, 1), 0, 1000),
            GraficoTempoReal("Integrador Lambda (STFT)", "%", (1.0, 0.75, 0.20, 1), -25, 25),
            GraficoTempoReal("Tempo Injecao Consolidado", "ms", (0.95, 0.40, 0.55, 1), 0, 16),
        ]
        self.pids_graf = ["RPM", "LAMBDA_1", "STFT", "TI_EFETIVO"]
        for g in self.graficos_lista:
            box.add_widget(g)
        return box

    def _criar_tela_log(self):
        box = BoxLayout(orientation="vertical", spacing=6, padding=4)
        self.lbl_log_info = Label(
            text="Selecione abaixo os PIDs para gravar no CSV:\n(Pasta de destino: /sdcard/Download/)",
            size_hint_y=0.14,
            font_size="12sp",
            color=(0.85, 0.90, 0.96, 1),
            halign="center",
        )
        box.add_widget(self.lbl_log_info)

        barra_sel_log = BoxLayout(size_hint_y=0.075, spacing=5)
        b_log_rap = Button(text="PIDS ESSENCIAIS", background_normal="", background_color=(0.15, 0.52, 0.70, 1), font_size="12sp", bold=True)
        b_log_rap.bind(on_release=lambda x: self._preset_log("RAPIDO"))
        b_log_all = Button(text="TODOS OS PIDS", background_normal="", background_color=(0.20, 0.58, 0.35, 1), font_size="12sp", bold=True)
        b_log_all.bind(on_release=lambda x: self._preset_log("TODOS"))
        b_log_clr = Button(text="LIMPAR SELECAO", background_normal="", background_color=(0.45, 0.30, 0.30, 1), font_size="12sp", bold=True)
        b_log_clr.bind(on_release=lambda x: self._preset_log("NENHUM"))
        barra_sel_log.add_widget(b_log_rap)
        barra_sel_log.add_widget(b_log_all)
        barra_sel_log.add_widget(b_log_clr)
        box.add_widget(barra_sel_log)

        scroll = ScrollView(size_hint_y=0.675)
        grid = GridLayout(cols=1, spacing=4, size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))
        for pid in PIDS_DB:
            tb = ToggleButton(
                text=f"  {pid['nome']} ({pid['unidade']})",
                size_hint_y=None,
                height=44,
                state="down" if self.selecionados_log[pid["id"]] else "normal",
                font_size="13sp",
                halign="left",
                valign="middle",
                padding=(14, 0),
            )
            tb.bind(size=tb.setter("text_size"))
            tb.bind(state=lambda inst, st, pid_id=pid["id"]: self._toggle_pid_log(pid_id, st))
            self.checks_log_ui[pid["id"]] = tb
            grid.add_widget(tb)
        scroll.add_widget(grid)
        box.add_widget(scroll)

        barra_grav = BoxLayout(size_hint_y=0.11, spacing=6)
        btn_ini = Button(text="INICIAR /\nCONTINUAR", background_normal="", background_color=(0.15, 0.65, 0.35, 1), bold=True, font_size="12sp", halign="center")
        btn_ini.bind(on_release=self.iniciar_gravacao_log)
        btn_pausar = Button(text="PAUSAR\nLOG", background_normal="", background_color=(0.82, 0.55, 0.12, 1), bold=True, font_size="12sp", halign="center")
        btn_pausar.bind(on_release=self.pausar_gravacao_log)
        btn_parar = Button(text="ENCERRAR\nE SALVAR", background_normal="", background_color=(0.78, 0.22, 0.22, 1), bold=True, font_size="12sp", halign="center")
        btn_parar.bind(on_release=self.parar_gravacao_log)
        barra_grav.add_widget(btn_ini)
        barra_grav.add_widget(btn_pausar)
        barra_grav.add_widget(btn_parar)
        box.add_widget(barra_grav)
        return box

    def _toggle_pid_log(self, pid_id, state):
        self.selecionados_log[pid_id] = (state == "down")

    def _preset_log(self, tipo):
        for pid in PIDS_DB:
            pid_id = pid["id"]
            if tipo == "RAPIDO":
                ativo = pid["rapido"]
            elif tipo == "TODOS":
                ativo = True
            else:
                ativo = False
            self.selecionados_log[pid_id] = ativo
            self.checks_log_ui[pid_id].state = "down" if ativo else "normal"

    def _criar_tela_engenharia(self):
        box = BoxLayout(orientation="vertical", spacing=8, padding=6)
        self.lbl_eng = Label(
            text="Diagnostico Avancado KWP2000 - ECU IAW 4AM\n\nSelecione uma operacao abaixo:",
            size_hint_y=0.50,
            font_size="14sp",
            halign="left",
            valign="top",
            color=(0.85, 0.90, 0.96, 1),
        )
        self.lbl_eng.bind(size=self.lbl_eng.setter("text_size"))
        box.add_widget(self.lbl_eng)

        linha_dtc = BoxLayout(size_hint_y=0.16, spacing=6)
        b_ler_dtc = Button(text="LER FALHAS (DTC)", background_normal="", background_color=(0.14, 0.45, 0.78, 1), bold=True, font_size="13sp")
        b_ler_dtc.bind(on_release=self.ler_dtcs)
        b_apg_dtc = Button(text="APAGAR FALHAS", background_normal="", background_color=(0.80, 0.35, 0.12, 1), bold=True, font_size="13sp")
        b_apg_dtc.bind(on_release=self.apagar_dtcs)
        linha_dtc.add_widget(b_ler_dtc)
        linha_dtc.add_widget(b_apg_dtc)
        box.add_widget(linha_dtc)

        linha_info = BoxLayout(size_hint_y=0.16, spacing=6)
        b_info = Button(text="INFO ECU E ODOMETRO", background_normal="", background_color=(0.35, 0.25, 0.65, 1), bold=True, font_size="12sp")
        b_info.bind(on_release=self.ler_info_ecu)
        b_modulos = Button(text="BUSCAR MODULOS", background_normal="", background_color=(0.20, 0.48, 0.62, 1), bold=True, font_size="12sp")
        b_modulos.bind(on_release=self.buscar_modulos_kwp)
        linha_info.add_widget(b_info)
        linha_info.add_widget(b_modulos)
        box.add_widget(linha_info)

        linha_varrer = BoxLayout(size_hint_y=0.16, spacing=6)
        b_varrer = Button(text="VARRER ECU", background_normal="", background_color=(0.15, 0.55, 0.40, 1), bold=True, font_size="13sp")
        b_varrer.bind(on_release=self.iniciar_varredura_ecu)
        b_parar_varrer = Button(text="PARAR VARREDURA", background_normal="", background_color=(0.75, 0.22, 0.22, 1), bold=True, font_size="13sp")
        b_parar_varrer.bind(on_release=self.parar_varredura_ecu)
        linha_varrer.add_widget(b_varrer)
        linha_varrer.add_widget(b_parar_varrer)
        box.add_widget(linha_varrer)
        return box


if __name__ == "__main__":
    TR4ScannerApp().run()
