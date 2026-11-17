# -*- coding: utf-8 -*-
"""
Motor de Comunicação Bluetooth e Thread de Telemetria (KWP2000 / IAW 4AM)
"""

import threading
import time
from kivy.utils import platform
from pids import PIDS_CONFIG, KWP_START_SESSION

class TelemetryEngine(threading.Thread):
    def __init__(self, update_callback, status_callback):
        super(TelemetryEngine, self).__init__()
        self.update_callback = update_callback
        self.status_callback = status_callback
        self.running = True
        self.connected = False
        self.socket = None
        self.stream_in = None
        self.stream_out = None

    def connect_bluetooth(self, address=""):
        try:
            if platform == 'android':
                from jnius import autoclass
                BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
                UUID = autoclass('java.util.UUID')
                
                adapter = BluetoothAdapter.getDefaultAdapter()
                if not adapter.isEnabled():
                    self.status_callback("Bluetooth desativado no aparelho.")
                    return False
                
                device = adapter.getRemoteDevice(address) if address else None
                if not device:
                    # Pega o primeiro dispositivo pareado se endereço não especificado
                    paired_devices = adapter.getBondedDevices().toArray()
                    if paired_devices:
                        device = paired_devices[0]
                    else:
                        self.status_callback("Nenhum dispositivo OBD pareado encontrado.")
                        return False

                spp_uuid = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
                self.socket = device.createRfcommSocketToServiceRecord(spp_uuid)
                adapter.cancelDiscovery()
                self.socket.connect()
                
                self.stream_in = self.socket.getInputStream()
                self.stream_out = self.socket.getOutputStream()
                
                self.connected = True
                self.status_callback("Conectado à ECU IAW 4AM via Bluetooth!")
                
                # Inicialização ELM327 / KWP2000
                self.send_elm_command("AT Z")      # Reset ELM
                self.send_elm_command("AT SP 5")    # Protocolo ISO 14230-4 KWP (Fast Init)
                self.send_elm_command(KWP_START_SESSION)
                return True
            else:
                # Modo simulação desktop
                time.sleep(1)
                self.connected = True
                self.status_callback("Modo Simulação Desktop Ativo (ECU IAW 4AM)")
                return True
        except Exception as e:
            self.status_callback(f"Erro na conexão BT: {str(e)}")
            self.connected = False
            return False

    def send_elm_command(self, cmd):
        if platform == 'android' and self.stream_out:
            try:
                full_cmd = cmd + "\r"
                self.stream_out.write(full_cmd.encode('ascii'))
                self.stream_out.flush()
                time.sleep(0.1)
            except Exception as e:
                print(f"Erro ao enviar comando ELM {cmd}: {e}")

    def read_pid_response(self, pid_key):
        cfg = PIDS_CONFIG[pid_key]
        if platform == 'android' and self.connected and self.stream_in:
            try:
                self.send_elm_command(cfg["cmd"])
                time.sleep(0.05)
                # Leitura simplificada do stream
                buffer = bytearray(64)
                bytes_read = self.stream_in.read(buffer)
                if bytes_read > 0:
                    response_str = buffer[:bytes_read].decode('ascii', errors='ignore')
                    # Parse básico de bytes da resposta OBD/KWP
                    # Exemplo de retorno: "41 0C 1A 2B" -> bytes A e B
                    lines = response_str.split('\n')
                    for line in lines:
                        cleaned = line.strip().replace(" ", "")
                        if "41" in cleaned or "61" in cleaned:
                            hex_data = cleaned[4:] # Remove eco/cabeçalho
                            if len(hex_data) >= 2:
                                a = int(hex_data[0:2], 16)
                                b = int(hex_data[2:4], 16) if len(hex_data) >= 4 else None
                                return cfg["formula"](a, b)
            except Exception as e:
                print(f"Erro ao ler PID {pid_key}: {e}")
            return 0.0
        else:
            # Modo Simulação com variações realistas para TR4
            import random
            if pid_key == "RPM":
                return int(820 + random.random() * 150)
            elif pid_key == "TEMP_AGUA":
                return int(89 + random.random() * 2)
            elif pid_key == "MAP":
                return int(34 + random.random() * 4)
            elif pid_key == "TPS":
                return round(12.5 + random.random() * 1.5, 1)
            elif pid_key == "BATT":
                return round(14.3 + random.random() * 0.2, 2)
            elif pid_key == "PID_21A0":
                return round(12.0 + random.random() * 2.0, 2)
            elif pid_key == "PID_21A1":
                return round(2.35 + random.random() * 0.1, 2)
            return 0.0

    def run(self):
        while self.running:
            if self.connected:
                data = {}
                for key in PIDS_CONFIG.keys():
                    data[key] = self.read_pid_response(key)
                self.update_callback(data)
                time.sleep(0.2)
            else:
                time.sleep(1.0)

    def stop(self):
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
