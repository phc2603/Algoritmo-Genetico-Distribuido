# ──────────────────────────────────────────────────────────────────────────────
# relogio_lamport.py — Relógio Lógico de Lamport
#
# Regra:
#   - Evento local:          tempo += 1
#   - Antes de enviar:       tempo += 1  (inclui o valor na mensagem)
#   - Ao receber mensagem T: tempo = max(tempo, T) + 1
# ──────────────────────────────────────────────────────────────────────────────

import threading


class RelogioLamport:

    def __init__(self):
        self._tempo = 0
        self._lock  = threading.Lock() #tratativa de lock para evitar adição de eventos concorrentes

    @property
    def tempo(self) -> int:
        with self._lock:
            return self._tempo

    def evento_local(self) -> int:
        """Incrementa o relógio para qualquer evento local relevante."""
        with self._lock:
            self._tempo += 1
            return self._tempo

    def antes_de_enviar(self) -> int:
        """
        Chama imediatamente antes de enviar uma mensagem.
        Retorna o timestamp a ser incluído na mensagem.
        """
        return self.evento_local()

    def ao_receber(self, timestamp_recebido: int) -> int:
        """
        Chama ao receber uma mensagem com timestamp T.
        Atualiza: tempo = max(tempo_local, T) + 1
        """
        with self._lock:
            self._tempo = max(self._tempo, timestamp_recebido) + 1
            return self._tempo
