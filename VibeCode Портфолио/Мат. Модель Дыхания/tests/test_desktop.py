"""Проверка Tkinter пропускается, если нет графического дисплея."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


class DesktopTests(unittest.TestCase):
    def setUp(self):
        try:
            import tkinter as tk
            self.root=tk.Tk()
        except (ImportError, Exception) as error:
            self.skipTest(f"Графический дисплей/Tkinter недоступен: {error}")
        from desktop import DesktopApp
        self.app=DesktopApp(self.root)
        self.root.update_idletasks()
        self.root.update()

    def tearDown(self):
        if hasattr(self,"app") and self.app.alive:self.app.close()

    def test_controls(self):
        self.app.oxygen.set("20,9")
        self.app.toggle()
        self.root.update()
        self.assertEqual(self.app.sim.status,"running")
        self.assertEqual(self.app.sim.oxygen_percent,20.9)
        self.assertEqual(self.app.entry.cget("state"),"disabled")
        self.app.toggle()
        before=self.app.sim.elapsed()
        self.root.update()
        self.assertEqual(self.app.sim.status,"paused")
        self.assertEqual(self.app.sim.elapsed(),before)
        self.app.toggle()
        self.assertEqual(self.app.sim.status,"running")
        self.app.reset()
        self.root.update()
        self.assertEqual(self.app.sim.status,"idle")
        self.assertEqual(self.app.sim.snapshot()["blood_total_ml"],0)
        self.assertEqual(self.app.entry.cget("state"),"normal")

    def test_canvas_and_zero_oxygen(self):
        self.app.oxygen.set("0")
        self.app.toggle()
        self.app.scene.draw(self.app.canvas,self.app.sim.snapshot())
        self.assertGreater(len(self.app.canvas.find_all()),100)
        snapshot=self.app.sim.snapshot()
        self.assertEqual(snapshot["inspired_total_ml"],0)
        self.assertEqual(snapshot["blood_total_ml"],0)
        self.assertEqual(snapshot["tissues_total_ml"],0)


if __name__=="__main__":unittest.main()
