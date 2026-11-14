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
        self.selecionados_log = {p["id"]: p["rapido"] for p in PIDS_DB}
        self.valores_atuais = {p["id"]: "--" for p in PIDS_DB}
        self.valores_min = {}
        self.valores_max = {}
        self.gravando_log = False
        self.arquivo_log = None
        self.writer_log = None
        self.inicio_log_ts = 0.0
        self.pids_graf = ["STFT", "SONDA_PRE", "MAP_KPA"]
        self.cards_ui = {}
        self.nav_botoes = {}
        self.aba_atual = "PAINEL"

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
        Window.bind(size=self._ao_girar_tela)
        self._trocar_aba("PAINEL", self.mostrar_aba_painel)
        return root

    def _ao_girar_tela(self, *args):
        if getattr(self, "aba_atual", "") == "PAINEL":
            self.mostrar_aba_painel()

    def _trocar_aba(self, nome_ativa, fn):
        self.aba_atual = nome_ativa
        for nome, btn in self.nav_botoes.items():
            btn.background_color = (0.12, 0.55, 0.75, 1) if nome == nome_ativa else (0.24, 0.30, 0.38, 1)
        fn()
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
        box = BoxLayout(orientation="vertical", spacing=6)
        barra_mm = BoxLayout(size_hint_y=0.07, spacing=6)
        btn_zerar = Button(text="ZERAR MIN / MAX", font_size="11sp", bold=True, background_normal="", background_color=(0.25, 0.32, 0.42, 1))
        btn_zerar.bind(on_release=self.zerar_min_max)
        barra_mm.add_widget(btn_zerar)
        box.add_widget(barra_mm)

        scroll = ScrollView(size_hint_y=0.93)
        colunas = 3 if Window.width > Window.height else 2
        grid = GridLayout(cols=colunas, spacing=10, size_hint_y=None, padding=(4, 6))
        grid.bind(minimum_height=grid.setter("height"))
        for pid in PIDS_DB:
            if not self.selecionados.get(pid["id"], False):
                continue
            card = BoxLayout(orientation="vertical", size_hint_y=None, height=118, padding=(8, 6), spacing=2)
            with card.canvas.before:
                Color(0.13, 0.16, 0.21, 1)
                rect = Rectangle(pos=card.pos, size=card.size)
            card.bind(pos=lambda inst, v, r=rect: setattr(r, "pos", v), size=lambda inst, v, r=rect: setattr(r, "size", v))
            lbl_nome = Label(text=pid["nome"], font_size="12sp", bold=True, color=(0.78, 0.84, 0.92, 1), size_hint_y=0.28)
            lbl_val = Label(text=f"{self.valores_atuais.get(pid['id'], '--')} {pid['unidade']}", font_size="19sp", bold=True, color=(0.15, 0.92, 0.52, 1), size_hint_y=0.44)
            vmin = self.valores_min.get(pid["id"], "--")
            vmax = self.valores_max.get(pid["id"], "--")
            lbl_mm = Label(text=f"MIN: {vmin}   |   MAX: {vmax}", font_size="11sp", color=(0.60, 0.78, 0.98, 1), size_hint_y=0.28)
            card.add_widget(lbl_nome)
            card.add_widget(lbl_val)
            card.add_widget(lbl_mm)
            grid.add_widget(card)
            self.cards_ui[pid["id"]] = (lbl_val, lbl_mm, pid["unidade"])
        scroll.add_widget(grid)
        box.add_widget(scroll)
        self.area_central.add_widget(box)

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
        lista = GridLayout(cols=1, spacing=8, size_hint_y=None, padding=(2, 4))
        lista.bind(minimum_height=lista.setter("height"))
        self.btns_pid_ui = {}
        for pid in PIDS_DB:
            btn = Button(size_hint_y=None, height=62, font_size="13sp", bold=True, background_normal="", halign="left", valign="middle", padding=(14, 0))
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
        lista = GridLayout(cols=1, spacing=8, size_hint_y=None, padding=(2, 4))
        lista.bind(minimum_height=lista.setter("height"))
        self.btns_log_ui = {}
        for pid in PIDS_DB:
            btn = Button(size_hint_y=None, height=60, font_size="13sp", bold=True, background_normal="", halign="left", valign="middle", padding=(14, 0))
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
        self.lbl_eng = Label(text="Modulo de Engenharia IAW 4AM.AR (SW 4AMMS)\nSessao Estendida KWP2000 (10 81)", font_size="12sp", size_hint_y=0.45, halign="left", valign="middle")
        self.lbl_eng.bind(size=self.lbl_eng.setter("text_size"))
        box.add_widget(self.lbl_eng)
        botoes1 = BoxLayout(size_hint_y=0.17, spacing=8)
        b_dtc = Button(text="LER FALHAS (DTC)", background_normal="", background_color=(0.15, 0.50, 0.80, 1), bold=True)
        b_dtc.bind(on_release=self.ler_dtcs)
        b_clear = Button(text="APAGAR FALHAS", background_normal="", background_color=(0.80, 0.40, 0.12, 1), bold=True)
        b_clear.bind(on_release=self.apagar_dtcs)
        botoes1.add_widget(b_dtc)
        botoes1.add_widget(b_clear)
        box.add_widget(botoes1)
        b_info = Button(text="INFO ECU & ODOMETRO REAL (2180 / 2171)", size_hint_y=0.17, background_normal="", background_color=(0.38, 0.30, 0.72, 1), bold=True)
        b_info.bind(on_release=self.ler_info_ecu)
        box.add_widget(b_info)
        b_scan = Button(text="VARRER ECU (2100 - 21FF) E SALVAR MAPA", size_hint_y=0.17, background_normal="", background_color=(0.20, 0.62, 0.45, 1), bold=True)
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
