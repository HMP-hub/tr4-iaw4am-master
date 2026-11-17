# -*- coding: utf-8 -*-
"""
Aplicativo Principal Kivy - Telemetria Pajero TR4 IAW 4AM
- Tela sempre acesa (WakeLock)
- Módulos pids.py e engine.py integrados
"""

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.utils import platform

from engine import TelemetryEngine

# Configuração de WakeLock para manter a tela sempre acesa no Android
if platform == 'android':
    from jnius import autoclass
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    WindowManager = autoclass('android.view.WindowManager$LayoutParams')

def keep_screen_on():
    if platform == 'android':
        try:
            activity = PythonActivity.mActivity
            window = activity.getWindow()
            window.addFlags(WindowManager.FLAG_KEEP_SCREEN_ON)
        except Exception as e:
            print(f"Erro WakeLock: {e}")

class PajeroTelemetryApp(App):
    def build(self):
        keep_screen_on()
        
        root = BoxLayout(orientation='vertical', padding=15, spacing=12)
        
        # Título
        root.add_widget(Label(text='Pajero TR4 - Telemetria IAW 4AM', font_size=22, bold=True, size_hint_y=None, height=45))
        
        # Status
        self.lbl_status = Label(text='Status: Desconectado', font_size=15, color=(1, 0.8, 0.2, 1), size_hint_y=None, height=35)
        root.add_widget(self.lbl_status)
        
        # Display de PIDs
        self.labels = {}
        pid_labels = [
            ("RPM", "RPM: --- rpm"),
            ("TEMP_AGUA", "Temp. Água: --- °C"),
            ("MAP", "MAP (Pressão): --- kPa"),
            ("TPS", "TPS (Borboleta): --- %"),
            ("BATT", "Bateria: --- V"),
            ("PID_21A0", "PID 21A0 (Ignição): --- °BTDC"),
            ("PID_21A1", "PID 21A1 (Injeção): --- ms")
        ]
        
        for key, text in pid_labels:
            lbl = Label(text=text, font_size=18, halign='left', valign='middle')
            lbl.bind(size=lambda s, w: setattr(s, 'text_size', s.size))
            self.labels[key] = lbl
            root.add_widget(lbl)
            
        # Botões
        btn_layout = BoxLayout(size_hint_y=None, height=55, spacing=10)
        self.btn_connect = Button(text='Conectar OBD', background_color=(0.1, 0.6, 0.2, 1))
        self.btn_connect.bind(on_press=self.toggle_connection)
        btn_layout.add_widget(self.btn_connect)
        
        root.add_widget(btn_layout)
        
        # Inicializa o Motor de Telemetria
        self.engine = TelemetryEngine(self.update_ui, self.update_status)
        self.engine.start()
        
        return root

    def update_status(self, msg):
        Clock.schedule_once(lambda dt: setattr(self.lbl_status, 'text', f"Status: {msg}"))

    def update_ui(self, data):
        Clock.schedule_once(lambda dt: self._apply_ui_update(data))

    def _apply_ui_update(self, data):
        for key, val in data.items():
            if key in self.labels:
                unit_map = {
                    "RPM": "rpm",
                    "TEMP_AGUA": "°C",
                    "MAP": "kPa",
                    "TPS": "%",
                    "BATT": "V",
                    "PID_21A0": "°BTDC",
                    "PID_21A1": "ms"
                }
                name_map = {
                    "RPM": "RPM",
                    "TEMP_AGUA": "Temp. Água",
                    "MAP": "MAP (Pressão)",
                    "TPS": "TPS (Borboleta)",
                    "BATT": "Bateria",
                    "PID_21A0": "PID 21A0 (Ignição)",
                    "PID_21A1": "PID 21A1 (Injeção)"
                }
                self.labels[key].text = f"{name_map.get(key, key)}: {val} {unit_map.get(key, '')}"

    def toggle_connection(self, instance):
        if not self.engine.connected:
            success = self.engine.connect_bluetooth()
            if success:
                self.btn_connect.text = "Desconectar"
        else:
            self.engine.stop()
            self.engine = TelemetryEngine(self.update_ui, self.update_status)
            self.engine.start()
            self.btn_connect.text = "Conectar OBD"
            self.update_status("Desconectado")

    def on_stop(self):
        if self.engine:
            self.engine.stop()

if __name__ == '__main__':
    PajeroTelemetryApp().run()
