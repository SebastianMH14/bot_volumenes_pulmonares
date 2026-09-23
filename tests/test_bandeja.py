import tempfile
import unittest
from datetime import date
from pathlib import Path

from modules.bandeja import Registro, hash_archivo, listar_pdfs, mover


class TestBandeja(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_listar_solo_pdfs_de_la_raiz(self):
        (self.dir / "a.pdf").write_bytes(b"a")
        (self.dir / "B.PDF").write_bytes(b"b")
        (self.dir / "nota.txt").write_text("x")
        (self.dir / "procesados").mkdir()
        (self.dir / "procesados" / "c.pdf").write_bytes(b"c")
        self.assertEqual({p.name for p in listar_pdfs(self.dir)}, {"a.pdf", "B.PDF"})

    def test_mover_no_sobrescribe(self):
        destino = self.dir / "procesados"
        f = date(2026, 9, 22)
        for contenido in (b"1", b"2"):
            (self.dir / "x.pdf").write_bytes(contenido)
            mover(self.dir / "x.pdf", destino, f)
        nombres = sorted(p.name for p in (destino / "2026-09-22").iterdir())
        self.assertEqual(nombres, ["x.pdf", "x_1.pdf"])

    def test_registro_intentos_y_estado_final(self):
        ruta = self.dir / "registro.json"
        reg = Registro(ruta)
        reg.registrar("h1", "x.pdf", "pendiente", motivo="FILA_NO_ENCONTRADA")
        reg.registrar("h1", "x.pdf", "pendiente", motivo="FILA_NO_ENCONTRADA")
        self.assertEqual(reg.intentos("h1"), 2)
        self.assertFalse(reg.ya_finalizado("h1"))

        reg.registrar("h1", "x.pdf", "subido", cedula="123")
        self.assertTrue(Registro(ruta).ya_finalizado("h1"))  # persiste en disco

    def test_registro_corrupto_se_respalda(self):
        ruta = self.dir / "registro.json"
        ruta.write_text("{no es json", encoding="utf-8")
        reg = Registro(ruta)
        self.assertIsNone(reg.get("h1"))
        self.assertEqual(len(list(self.dir.glob("registro.corrupto_*.json"))), 1)

    def test_hash_cambia_con_contenido(self):
        a, b = self.dir / "a.pdf", self.dir / "b.pdf"
        a.write_bytes(b"uno")
        b.write_bytes(b"dos")
        self.assertNotEqual(hash_archivo(a), hash_archivo(b))


if __name__ == "__main__":
    unittest.main()
