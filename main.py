# coding: utf-8
import os
import threading
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
from kivy.clock import Clock

from pids import PIDS_DB
from engine import TR4EngineMixin

Window.clearcolor = (0.08, 0.09, 0.11, 1)

class GraficoRealtime(Widget):
    def __init__(self, cor_linha=(0.2, 0.85, 0.45, 1), max_pontos=90, **kwargs):
        super().__init__(**kwargs)
        self.cor_linha = cor_linha
        self.max_pontos = max_pontos
        self.pontos = []
        self.lbl_info = Label(text="--", font_size="12sp", bold=True, color=(0.95, 0.95, 0.95, 1), halign="left", valign="top")
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
        if len(self.pontos) > self.max_pontos: self.pontos.pop(0)
        vmin, vmax = min(self.pontos), max(self.pontos)
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
                vmin, vmax = min(self.pontos), max(self.pontos)
                if vmax - vmin < 1e-6: vmax = vmin + 1.0
                pad_y, altura_util = dp(10), max(dp(10), self.height - dp(32))
                passo_x = self.width / max(1, self.max_pontos - 1)
                coords = []
                for idx, v in enumerate(self.pontos):
                    px = self.x + idx * passo_x
                    norm = (v - vmin) / (vmax - vmin)
                    py = self.y + pad_y + norm * altura_util
                    coords.extend([px, py])
                Color(*self.cor_linha)
                Line(points=coords, width=dp(1.8))

class TR4MainApp(App, TR4EngineMixin):
    def build(self):
        self.title = "TR4 IAW4AM Master"
        self.bt_lock = threading.Lock()
        self.bt_socket = self.bt_in = self.bt_out = None
        self.bt_salvo_addr = self.bt_salvo_nome = ""
        self.estado_conexao = "DESCONECTADO"
        self.cancelar_conexao = self.rodando = self.varrendo = self.modo_simulacao = False
        self.gravando_log = self.log_pausado = False
        self.arquivo_log = self.writer_log = None

        self.valores_atuais = {p["id"]: "--" for p in PIDS_DB}
        self.valores_min = self.valores_max = {}
        self.selecionados = {p["id"]: p["rapido"] for p in PIDS_DB}
        self.selecionados_log = {p["id"]: p["rapido"] for p in PIDS_DB}
        self.cards_ui = {}

        self._carregar_bt_salvo()
        self._init_telemetria_viagem()

        root = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(6))

        self.lbl_status = Label(text="DESCONECTADO | ECU: IAW 4AM.AR", size_hint_y=None, height=dp(28), font_size="12sp", bold=True, color=(1, 0.78, 0.2, 1))
        root.add_widget(self.lbl_status)

        barra_con = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        self.btn_bt_lista = Button(text="ESCOLHER\nBLUETOOTH", font_size="12sp", bold=True, halign="center", background_normal="", background_color=(0.12, 0.45, 0.78, 1))
        self.btn_bt_lista.bind(on_release=self.conectar_bluetooth)

        self.btn_acao_con = Button(text="CONECTAR", font_size="13sp", bold=True, halign="center", background_normal="", background_color=(0.14, 0.62, 0.35, 1))
        self.btn_acao_con.bind(on_release=self.acao_botao_conexao)

        btn_sim = Button(text="SIMULACAO", font_size="12sp", bold=True, background_normal="", background_color=(0.45, 0.25, 0.68, 1))
        btn_sim.bind(on_release=self.iniciar_simulacao)

        barra_con.add_widget(self.btn_bt_lista)
        barra_con.add_widget(self.btn_acao_con)
        barra_con.add_widget(btn_sim)
        root.add_widget(barra_con)

        barra_abas = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(4))
        self.sm = ScreenManager(transition=NoTransition())
        self.btns_abas = {}
        for nome_scr, rotulo in [("painel", "PAINEL"), ("pids", "PIDS"), ("grafico", "GRAFICO"), ("log", "LOG CSV"), ("boletim", "BOLETIM"), ("eng", "ENG/DTC")]:
            b = Button(text=rotulo, font_size="11sp", bold=True, background_normal="", background_color=(0.18, 0.21, 0.27, 1))
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
        if nome_scr == "boletim": self.atualizar_tela_boletim()

    def _criar_tela_painel(self):
        scr = Screen(name="painel")
        box = BoxLayout(orientation="vertical", spacing=dp(6))
        btn_zerar = Button(text="ZERAR MIN / MAX", size_hint_y=None, height=dp(36), font_size="12sp", bold=True, background_normal="", background_color=(0.24, 0.28, 0.36, 1))
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
            if not self.selecionados.get(pid_id, False): continue
            card = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(106), padding=(dp(6), dp(6)), spacing=dp(2))
            with card.canvas.before:
                Color(0.13, 0.15, 0.20, 1)
                bg = Rectangle(pos=card.pos, size=card.size)
            card.bind(pos=lambda inst, v, r=bg: setattr(r, "pos", v), size=lambda inst, v, r=bg: setattr(r, "size", v))
            lbl_nome = Label(text=p["nome"], font_size="13sp", bold=True, color=(0.82, 0.87, 0.94, 1), halign="center", valign="middle", size_hint_y=0.36)
            lbl_nome.bind(size=lambda inst, v: setattr(inst, "text_size", v))
            lbl_val = Label(text="--", font_size="21sp", bold=True, color=(0.25, 0.92, 0.55, 1), halign="center", valign="middle", size_hint_y=0.40)
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
        for t, m, c in [("PADRAO\nRAPIDO", "rapido", (0.15, 0.48, 0.72, 1)), ("MARCAR\nTODOS", "todos", (0.18, 0.55, 0.35, 1)), ("DESMARCAR\nTODOS", "nenhum", (0.68, 0.24, 0.24, 1))]:
            b = Button(text=t, font_size="10.5sp", bold=True, halign="center", background_normal="", background_color=c)
            b.bind(on_release=lambda inst, modo=m: self._aplicar_preset_pids(modo))
            top_btns.add_widget(b)
        box.add_widget(top_btns)
        scroll = ScrollView(bar_width=dp(6))
        lista = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        lista.bind(minimum_height=lista.setter("height"))
        self.checks_pids = {}
        for p in PIDS_DB:
            pid_id = p["id"]
            linha = BoxLayout(size_hint_y=None, height=dp(42), padding=(dp(6), 0))
            chk = CheckBox(active=self.selecionados.get(pid_id, False), size_hint_x=0.14)
            chk.bind(active=lambda inst, val, k=pid_id: (self.selecionados.update({k: bool(val)}), self._reconstruir_cards_painel()))
            self.checks_pids[pid_id] = chk
            lbl = Label(text=f"{p['nome']} ({p['unidade']})", font_size="12.5sp", halign="left", valign="middle", size_hint_x=0.86)
            lbl.bind(size=lambda inst, v: setattr(inst, "text_size", v))
            linha.add_widget(chk); linha.add_widget(lbl)
            lista.add_widget(linha)
        scroll.add_widget(lista)
        box.add_widget(scroll)
        scr.add_widget(box)
        return scr

    def _aplicar_preset_pids(self, modo):
        for p in PIDS_DB:
            pid_id = p["id"]
            novo = True if modo == "todos" else (False if modo == "nenhum" else p["rapido"])
            self.selecionados[pid_id] = novo
            if pid_id in self.checks_pids: self.checks_pids[pid_id].active = novo
        self._reconstruir_cards_painel()

    def _criar_tela_grafico(self):
        scr = Screen(name="grafico")
        box = BoxLayout(orientation="vertical", spacing=dp(6))
        opcoes = [f"{p['nome']} ({p['unidade']})" for p in PIDS_DB]
        self.mapa_spinner_pid = {f"{p['nome']} ({p['unidade']})": p["id"] for p in PIDS_DB}
        self.pids_graf = ["RPM", "KNOCK_SENSOR"]
        self.graficos_lista = []
        for idx, pid_ini in enumerate(self.pids_graf):
            sp = Spinner(text=next((k for k, v in self.mapa_spinner_pid.items() if v == pid_ini), opcoes[0]), values=opcoes, size_hint_y=None, height=dp(38), font_size="12sp", bold=True, background_normal="", background_color=(0.18, 0.24, 0.34, 1))
            graf = GraficoRealtime(cor_linha=(0.22, 0.88, 0.48, 1) if idx == 0 else (0.95, 0.55, 0.22, 1))
            sp.bind(text=lambda inst, txt, i=idx, g=graf: (self.pids_graf.update({i: self.mapa_spinner_pid.get(txt)}), g.limpar()))
            self.graficos_lista.append(graf)
            box.add_widget(sp); box.add_widget(graf)
        scr.add_widget(box)
        return scr

    def _criar_tela_log(self):
        scr = Screen(name="log")
        box = BoxLayout(orientation="vertical", spacing=dp(6))
        self.lbl_log_info = Label(text="Selecione os PIDs e clique em INICIAR LOG CSV.\nSalvo em /sdcard/Download.", size_hint_y=None, height=dp(52), font_size="12sp", halign="left", valign="middle")
        self.lbl_log_info.bind(size=lambda inst, v: setattr(inst, "text_size", v))
        box.add_widget(self.lbl_log_info)

        barra_log = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        for t, cb, c in [("INICIAR", self.iniciar_gravacao_log, (0.14, 0.62, 0.35, 1)), ("PAUSAR", self.pausar_gravacao_log, (0.82, 0.52, 0.14, 1)), ("PARAR", self.parar_gravacao_log, (0.76, 0.22, 0.22, 1))]:
            b = Button(text=t, font_size="11sp", bold=True, background_normal="", background_color=c)
            b.bind(on_release=cb)
            barra_log.add_widget(b)
        box.add_widget(barra_log)
        scr.add_widget(box)
        return scr

    def _criar_tela_boletim(self):
        scr = Screen(name="boletim")
        box = BoxLayout(orientation="vertical", spacing=dp(6))
        scroll = ScrollView(bar_width=dp(6))
        self.lbl_boletim = Label(text="Monitoramento preditivo automatico ativo.", markup=True, font_size="13sp", halign="left", valign="top", size_hint_y=None, padding=(dp(8), dp(8)))
        self.lbl_boletim.bind(width=lambda inst, w: setattr(inst, "text_size", (w, None)), texture_size=lambda inst, ts: setattr(inst, "height", max(dp(260), ts[1] + dp(16))))
        scroll.add_widget(self.lbl_boletim)
        box.add_widget(scroll)
        barra_bol = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        for t, cb, c in [("ATUALIZAR", lambda *a: self.atualizar_tela_boletim(), (0.15, 0.48, 0.72, 1)), ("NOVA VIAGEM", self.reiniciar_telemetria_viagem, (0.80, 0.48, 0.14, 1)), ("SALVAR TXT", self.salvar_boletim_txt, (0.14, 0.62, 0.35, 1))]:
            b = Button(text=t, font_size="12sp", bold=True, background_normal="", background_color=c)
            b.bind(on_release=cb)
            barra_bol.add_widget(b)
        box.add_widget(barra_bol)
        scr.add_widget(box)
        return scr

    def _criar_tela_eng(self):
        scr = Screen(name="eng")
        box = BoxLayout(orientation="vertical", spacing=dp(6))
        scroll = ScrollView(size_hint_y=0.44, bar_width=dp(6))
        self.lbl_eng = Label(text="Diagnostico KWP2000 - IAW 4AM", font_size="13sp", halign="left", valign="top", size_hint_y=None, padding=(dp(8), dp(8)))
        scroll.add_widget(self.lbl_eng)
        box.add_widget(scroll)
        scr.add_widget(box)
        return scr

if __name__ == "__main__":
    TR4MainApp().run()
