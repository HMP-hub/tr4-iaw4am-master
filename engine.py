else:
                    cmd = pid["cmd"]
                    if cmd not in cache_comandos:
                        raw = self.enviar_comando_raw(cmd, timeout=1.0)
                        parsed = self.parse_bytes_kwp(raw, cmd)
                        if not parsed:
                            time.sleep(0.03)
                            raw = self.enviar_comando_raw(cmd, timeout=1.0)
                            parsed = self.parse_bytes_kwp(raw, cmd)
                        cache_comandos[cmd] = parsed
                    bytes_resp = cache_comandos[cmd]
                    if not bytes_resp:
                        continue
                    try:
                        valor = pid["calc"](bytes_resp)
                    except Exception:
                        valor = None
                if valor is not None:
                    self._registrar_valor(pid["id"], valor)