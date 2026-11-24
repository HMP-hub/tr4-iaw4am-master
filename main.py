# coding: utf-8
import threading
from operator import itemgetter
from kivy.app import App
from kivy.clock import Clock
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


class CardPID(BoxLayout):
    def __init__(self, pid_id, app_ref, **kwargs):
        super().__init__(**kwargs)
        self.pid_id = pid_id
        self.app_ref = app_ref
        self._lp_event = None
        self._touch_ini = (0, 0)
        self._arrastando = False
        self._ghost = None
        self._offset = (0, 0)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._touch_ini = touch.pos
            self._lp_event = Clock.schedule_once(lambda dt: self._iniciar_drag(touch), 0.35)
        return super().on_touch_down(touch)

    def _iniciar_drag(self, touch):
        self._lp_event = None
        if self.app_ref.sm.current != "painel":
            return
        self._arrastando = True
        touch.grab(self)
        self.app_ref.scroll_painel.do_scroll_y = False
        win_x, win_y = self.to_window(*self.pos)
        self._offset = (touch.x - win_x, touch.y - win_y)

        self._ghost = BoxLayout(size_hint=(None, None), size=self.size, pos=(win_x, win_y))
        with self._ghost.canvas.before:
            Color(0.16, 0.48, 0.82, 0.90)
            Rectangle(pos=self._ghost.pos, size=self._ghost.size)
        self._ghost.bind(
            pos=lambda inst, v: self._atualizar_ghost_canvas(),
            size=lambda inst, v: self._atualizar_ghost_canvas(),
        )
        lbl_g = Label(text=self.children[-1].text, font_size="14sp", bold=True, color=(1, 1, 1, 1))
        self._ghost.add_widget(lbl_g)
        Window.add_widget(self._ghost)
        self.opacity = 0.25

    def _atualizar_ghost_canvas(self):
        if self._ghost:
            self._ghost.canvas.before.clear()
            with self._ghost.canvas.before:
                Color(0.16, 0.48, 0.82, 0.90)
                Rectangle(pos=self._ghost.pos, size=self._ghost.size)

    def on_touch_move(self, touch):
        if self._arrastando and touch.grab_current is self:
            if self._ghost:
                ox, oy = self._offset
                self._ghost.pos = (touch.x - ox, touch.y - oy)
            self.app_ref._processar_movimento_drag(self.pid_id, touch.pos)
            return True
        if self._lp_event:
            ix, iy = self._touch_ini
            dx = abs(touch.x - ix)
            dy = abs(touch.y - iy)
            if dx > dp(12) or dy > dp(12):
                self._lp_event.cancel()
                self._lp_event = None
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if self._lp_event:
            self._lp_event.cancel()
            self._lp_event = None
        if self._arrastando and touch.grab_current is self:
            touch.ungrab(self)
            self._arrastando = False
            self.opacity = 1.0
            if self._ghost:
                Window.remove_widget(self._ghost)
                self._ghost = None
            self.app_ref.scroll_painel.do_scroll_y = True
            self.app_ref._salvar_ordem_pids()
            self.app_ref._reconstruir_cards_painel()
            return True
        return super().on_touch_up(touch)

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
        self.ordem_pids = [p["id"] for p in PIDS_DB]
        self.cards_ui = {}

        self._carregar_bt_salvo()
        self._carregar_ordem_pids()
        self._init_telemetria_viagem()

        root = BoxLayout(orientation="vertical", padding=dp(7), spacing=dp(6))
        self.root_box = root

        with root.canvas.after:
            self._cor_borda_alerta = Color(1.0, 0.12, 0.12, 0.0)
            self._linha_borda_alerta = Line(rectangle=(0, 0, 100, 100), width=dp(4.5))
        root.bind(pos=self._atualizar_retangulo_borda, size=self._atualizar_retangulo_borda)

        self.lbl_status = Label(
            text="DESCONECTADO | ECU: IAW 4AM.AR (4AMMS)",
            size_hint_y=None,
            height=dp(28),
            font_size="12sp",
            bold=True,
            color=(1, 0.78, 0.2, 1),
        )
        root.add_widget(self.lbl_status)

        self.lbl_banner_alerta = Label(
            text="",
            size_hint_y=None,
            height=0,
            opacity=0,
            font_size="13sp",
            bold=True,
            color=(1, 1, 1, 1),
            halign="center",
            valign="middle",
        )
        with self.lbl_banner_alerta.canvas.before:
            Color(0.85, 0.10, 0.10, 1)
            self._bg_banner_alerta = Rectangle(pos=self.lbl_banner_alerta.pos, size=self.lbl_banner_alerta.size)
        self.lbl_banner_alerta.bind(
            pos=lambda inst, v: setattr(self._bg_banner_alerta, "pos", v),
            size=lambda inst, v: (
                setattr(self._bg_banner_alerta, "size", v),
                setattr(inst, "text_size", v),
            ),
        )
        root.add_widget(self.lbl_banner_alerta)

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

    def _atualizar_retangulo_borda(self, inst, *args):
        if hasattr(self, "_linha_borda_alerta"):
            pad = dp(2.5)
            self._linha_borda_alerta.rectangle = (
                inst.x + pad,
                inst.y + pad,
                max(10, inst.width - pad * 2),
                max(10, inst.height - pad * 2),
            )

    def trocar_aba(self, nome_scr):
        self.sm.current = nome_scr
        for k, btn in self.btns_abas.items():
            btn.background_color = (0.16, 0.52, 0.78, 1) if k == nome_scr else (0.18, 0.21, 0.27, 1)
        if nome_scr == "boletim":
            self.atualizar_tela_boletim()

    def _criar_tela_painel(self):
        scr = Screen(name="painel")
        box = BoxLayout(orientation="vertical", spacing=dp(6))

        barra_p = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        btn_zerar = Button(
            text="ZERAR MIN / MAX",
            font_size="11.5sp",
            bold=True,
            background_normal="",
            background_color=(0.24, 0.28, 0.36, 1),
        )
        btn_zerar.bind(on_release=self.zerar_min_max)

        btn_ord_pad = Button(
            text="ORDEM PADRAO",
            font_size="11.5sp",
            bold=True,
            background_normal="",
            background_color=(0.20, 0.34, 0.46, 1),
        )
        btn_ord_pad.bind(on_release=self.restaurar_ordem_padrao)

        barra_p.add_widget(btn_zerar)
        barra_p.add_widget(btn_ord_pad)
        box.add_widget(barra_p)

        self.scroll_painel = ScrollView(bar_width=dp(5))
        self.grid_painel = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, padding=(dp(2), dp(2)))
        self.grid_painel.bind(minimum_height=self.grid_painel.setter("height"))
        self.scroll_painel.add_widget(self.grid_painel)
        box.add_widget(self.scroll_painel)

        self._reconstruir_cards_painel()
        scr.add_widget(box)
        return scr

    def _processar_movimento_drag(self, pid_origem, win_pos):
        sc = self.scroll_painel
        _, sc_y = sc.to_window(*sc.pos)
        sc_top = sc_y + sc.height
        _, wy = win_pos
        if wy > sc_top - dp(40) and sc.scroll_y < 1.0:
            sc.scroll_y = min(1.0, sc.scroll_y + 0.04)
        elif wy < sc_y + dp(40) and sc.scroll_y > 0.0:
            sc.scroll_y = max(0.0, sc.scroll_y - 0.04)

        local_pos = self.grid_painel.to_widget(*win_pos)
        alvo_id = None
        for child in self.grid_painel.children:
            if isinstance(child, CardPID) and child.pid_id != pid_origem:
                if child.collide_point(*local_pos):
                    alvo_id = child.pid_id
                    break
        if alvo_id:
            self.reordenar_card_drag(pid_origem, alvo_id)

    def _reconstruir_cards_painel(self, pid_arrastando=None):
        self.grid_painel.clear_widgets()
        self.cards_ui = {}
        mapa_pids = {p["id"]: p for p in PIDS_DB}
        ids_ordenados = [pid_id for pid_id in self.ordem_pids if pid_id in mapa_pids]
        for p in PIDS_DB:
            if p["id"] not in ids_ordenados:
                ids_ordenados.append(p["id"])

        for pid_id in ids_ordenados:
            if not self.selecionados.get(pid_id, False):
                continue
            p = mapa_pids[pid_id]
            card = CardPID(
                pid_id=pid_id,
                app_ref=self,
                orientation="vertical",
                size_hint_y=None,
                height=dp(106),
                padding=(dp(6), dp(6)),
                spacing=dp(2),
            )
            if pid_id == pid_arrastando:
                card.opacity = 0.25
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

            val_atual = self.valores_atuais.get(pid_id, "--")
            txt_val = f"{val_atual} {p['unidade']}" if val_atual != "--" else "--"
            lbl_val = Label(
                text=txt_val,
                font_size="21sp",
                bold=True,
                color=(0.25, 0.92, 0.55, 1),
                halign="center",
                valign="middle",
                size_hint_y=0.40,
            )
            lbl_val.bind(size=lambda inst, v: setattr(inst, "text_size", v))

            rodape = BoxLayout(size_hint_y=0.24)
            vmin = self.valores_min.get(pid_id, "--")
            vmax = self.valores_max.get(pid_id, "--")
            lbl_min = Label(text=f"MIN: {vmin}", font_size="10sp", color=(0.55, 0.75, 0.95, 1), halign="left")
            lbl_max = Label(text=f"MAX: {vmax}", font_size="10sp", color=(0.95, 0.65, 0.45, 1), halign="right")
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

        opcoes = ["Nenhum"] + [p["nome"] for p in PIDS_DB]
        self.mapa_spinner_pid = {"Nenhum": None}
        for p in PIDS_DB:
            self.mapa_spinner_pid[p["nome"]] = p["id"]

        self.pids_graf = ["LAMBDA_1", None, None]
        self.graficos_lista = []
        cores = [
            (0.22, 0.88, 0.48, 1),
            (0.95, 0.55, 0.22, 1),
            (0.28, 0.72, 0.98, 1),
        ]

        for idx in range(3):
            pid_ini = itemgetter(idx)(self.pids_graf)
            if pid_ini is None:
                texto_ini = "Nenhum"
            else:
                texto_ini = next((k for k, v in self.mapa_spinner_pid.items() if v == pid_ini), "Nenhum")
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
            if pid_ini is None:
                graf.lbl_info.text = "Grafico desativado (selecione um PID acima)"
            sp.bind(text=lambda inst, txt, i=idx, g=graf: self._trocar_pid_grafico(i, txt, g))
            self.graficos_lista.append(graf)
            box.add_widget(sp)
            box.add_widget(graf)

        scr.add_widget(box)
        return scr

    def _trocar_pid_grafico(self, idx, texto_sel, graf_widget):
        pid_id = self.mapa_spinner_pid.get(texto_sel)
        self.pids_graf[idx] = pid_id
        graf_widget.limpar()
        if pid_id is None:
            graf_widget.lbl_info.text = "Grafico desativado (selecione um PID acima)"
            return
        self.selecionados[pid_id] = True
        if pid_id in self.checks_pids:
            self.checks_pids[pid_id].active = True
        self._reconstruir_cards_painel()

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

        scroll = ScrollView(size_hint_y=0.40, bar_width=dp(6))
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

        grid_btns = GridLayout(cols=2, spacing=dp(7), size_hint_y=0.60)
        botoes_eng = [
            ("LER FALHAS (DTC)", (0.12, 0.46, 0.78, 1), self.ler_dtcs),
            ("APAGAR FALHAS +\nRESET ADAPTATIVO", (0.82, 0.38, 0.12, 1), self.apagar_dtcs),
            ("RESET PROFUNDO\nSFS / EEPROM", (0.72, 0.18, 0.42, 1), self.reset_profundo_sfs),
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
                font_size="11.5sp",
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

