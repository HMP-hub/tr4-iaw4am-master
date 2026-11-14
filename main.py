# coding: utf-8
import traceback
from kivy.app import App
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, Line
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.checkbox import CheckBox
from kivy.uix.widget import Widget

from pids import PIDS_DB
from engine import TR4EngineMixin

Window.clearcolor = (0.07, 0.08, 0.10, 1)


class GraficoTempoReal(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.dados = []
        self.bind(pos=self.redesenhar, size=self.redesenhar)

    def adicionar_ponto(self, valor):
        if isinstance(valor, (int, float)):
            self.dados.append(float(valor))
            if len(self.dados) > 80:
                self.dados.pop(0)
            self.redesenhar()

    def redesenhar(self, *args):
        self.canvas.clear()
        with self.canvas:
            Color(0.11, 0.13, 0.17, 1)
            Rectangle(pos=self.pos, size=self.size)
            Color(0.22, 0.25, 0.30, 1)
            meio_y = self.y + self.height / 2.0
            Line(points=[self.x, meio_y, self.x + self.width, meio_y], width=1)
            if len(self.dados) < 2:
                return
            v_min, v_max = min(self.dados), max(self.dados)
            amplitude = (v_max - v_min) if (v_max - v_min) > 0.1 else 1.0
            pontos = []
            passo_x = self.width / float(max(1, len(self.dados) - 1))
            for i, val in enumerate(self.dados):
                px = self.x + i * passo_x
                norm_y = (val - v_min) / amplitude
                py = self.y + 10 + norm_y * (self.height - 20)
                pontos.extend([px, py])
            Color(0.10, 0.85, 0.45, 1)
            Line(points=pontos, width=2.2)


class TR4MonitorApp(App, TR4EngineMixin):
    def build(self):
        self.title = "TR4 IAW4AM Master"
        self.rodando = False
        self.modo_simulacao = False
        self.bt_socket = None
        self.bt_in = None
        self.bt_out = None
        self.selecionados = {p["id"]: p["rapido"] for p in PIDS_DB}
        self.valores_atuais = {p["id"]: "--" for p in PIDS_DB}
        self.gravando_log = False
        self.arquivo_log = None
        self.writer_log = None
        self.inicio_log_ts = 0.0
        self.pids_graf = ["STFT", "SONDA_PRE", "MAP_KPA"]
        self.cards_ui = {}
        self.nav_botoes = {}

        root = BoxLayout(orientation="vertical", padding=6, spacing=6)
        self.lbl_status = Label(text="DESCONECTADO | ECU: IAW 4AM.AR (4AMMS)", bold=True, font_size="13sp", color=(1, 0.78, 0.2, 1), size_hint_y=0.05)
        root.add_widget(self.lbl_status)

        top_bar = BoxLayout(size_hint_y=0.08, spacing=6)
        for txt, cor, fn in [("CONECTAR MX+", (0.10, 0.50, 0.82, 1), self.iniciar_bluetooth), ("SIMULACAO", (0.18, 0.62, 0.34, 1), self.iniciar_simulacao), ("PARAR", (0.78, 0.22, 0.22, 1), self.parar_conexao)]:
            b = Button(text=txt, font_size="12sp", background_normal="", background_color=cor, bold=True)
            b.bind(on_release=fn)
            top_bar.add_widget(b)
        root.add_widget(top_bar)

        nav_bar = BoxLayout(size_hint_y=0.07, spacing=5)
        for nome_aba, fn in [("PAINEL", self.mostrar_aba_painel), ("PIDS", self.mostrar_aba_seletor), ("GRAFICO", self.mostrar_aba_grafico), ("LOG CSV", self.mostrar_aba_log), ("ENG/DTC", self.mostrar_aba_engenharia)]:
            b = Button(text=nome_aba, font_size="11sp", bold=True, background_normal="", background_color=(0.24, 0.30, 0.38, 1))
            b.bind(on_release=lambda inst, f=fn, n=nome_aba: self._trocar_aba(n, f))
            nav_bar.add_widget(b)
            self.nav_botoes[nome_aba] = b
        root.add_widget(nav_bar)

        self.area_central = BoxLayout(orientation="vertical", size_hint_y=0.80)
        root.add_widget(self.area_central)
        self._trocar_aba("PAINEL", self.mostrar_aba_painel)
        return root

    def _trocar_aba(self, nome_ativa, fn):
        for nome, btn in self.nav_botoes.items():
            btn.background_color = (0.12, 0.55, 0.75, 1) if nome == nome_ativa else (0.24, 0.30, 0.38, 1)
        fn()
    def limpar_area_central(self):
        self.area_central.clear_widgets()
        self.cards_ui = {}

    def mostrar_aba_painel(self, *args):
        self.limpar_area_central()
        scroll = ScrollView()
        grid = GridLayout(cols=2, spacing=6, size_hint_y=None, padding=(2, 4))
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
        self.checkboxes_ui = {}
        for pid in PIDS_DB:
            linha = BoxLayout(size_hint_y=None, height=58, padding=(6, 4))
            cb = CheckBox(active=self.selecionados.get(pid["id"], False), size_hint_x=0.14)
            cb.bind(active=lambda inst, val, pid_id=pid["id"]: self.selecionados.update({pid_id: val}))
            lbl = Label(text=f"[{pid['categoria']}]\n{pid['nome']} ({pid['cmd']})", font_size="13sp", halign="left", valign="middle", size_hint_x=0.86)
            lbl.bind(size=lbl.setter("text_size"))
            linha.add_widget(cb)
            linha.add_widget(lbl)
            lista.add_widget(linha)
            self.checkboxes_ui[pid["id"]] = cb
        scroll.add_widget(lista)
        box.add_widget(scroll)
        self.area_central.add_widget(box)

    def definir_todos_pids(self, modo):
        for pid in PIDS_DB:
            estado = True if modo == "TODOS" else (pid["rapido"] if modo == "RAPIDO" else False)
            self.selecionados[pid["id"]] = estado
            if pid["id"] in self.checkboxes_ui:
                self.checkboxes_ui[pid["id"]].active = estado

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
        box = BoxLayout(orientation="vertical", spacing=10, padding=10)
        self.lbl_log_info = Label(text="Gravacao de Telemetria CSV\nSalva na pasta Download", font_size="14sp", size_hint_y=0.45)
        box.add_widget(self.lbl_log_info)
        botoes = BoxLayout(size_hint_y=0.20, spacing=8)
        b_ini = Button(text="INICIAR LOG", background_normal="", background_color=(0.18, 0.62, 0.34, 1), bold=True)
        b_ini.bind(on_release=self.iniciar_gravacao_log)
        b_parar = Button(text="FECHAR LOG", background_normal="", background_color=(0.78, 0.22, 0.22, 1), bold=True)
        b_parar.bind(on_release=self.parar_gravacao_log)
        botoes.add_widget(b_ini)
        botoes.add_widget(b_parar)
        box.add_widget(botoes)
        self.area_central.add_widget(box)

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
