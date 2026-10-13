"""Запуск из папки проекта: python -m unittest discover -s tests -v"""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model import (Simulation, calculate, inspired_air, inspired_air_rate,
                   lung_expansion, validate_oxygen)
from svg_canvas import (SVGScene, flatten_path, parse_transform, transform_point)


class ModelTests(unittest.TestCase):
    def test_input(self):
        for value, expected in [(21,21), ("20,9",20.9), (0,0), (100,100), (" 15.5 ",15.5)]:
            self.assertEqual(validate_oxygen(value), expected)
        for value in ["", "abc", -1, 100.01, True, None, math.nan, math.inf, "-inf"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_oxygen(value)

    def test_volume_and_phases(self):
        for t, volume in [(0,0), (1,.5), (2,1), (3.5,.5), (5,0)]:
            self.assertAlmostEqual(lung_expansion(t),volume)
        self.assertEqual(calculate(1,21)["phase"],"inhale")
        self.assertEqual(calculate(3,21)["phase"],"exhale")
        self.assertEqual(calculate(5,21)["completed_breaths"],1)

    def test_one_breath_at_21_percent(self):
        self.assertAlmostEqual(calculate(2,21)["inspired_total_ml"],105)
        self.assertAlmostEqual(calculate(2.6,21)["blood_total_ml"],21)
        self.assertAlmostEqual(calculate(5.6,21)["tissues_total_ml"],21)

    def test_percentages(self):
        for oxygen in (0,15,21,30,100):
            s=calculate(2.6,oxygen)
            self.assertAlmostEqual(s["inspired_total_ml"],oxygen*5)
            self.assertAlmostEqual(s["blood_total_ml"],oxygen)
        for t in [0,1,2,7,60,999]:
            s=calculate(t,0)
            self.assertEqual((s["inspired_total_ml"],s["blood_total_ml"],s["tissues_total_ml"]),(0,0,0))

    def test_cumulative_air_does_not_decrease_on_exhale(self):
        self.assertEqual(inspired_air(-5),0)
        self.assertEqual(inspired_air(2),500)
        self.assertEqual(inspired_air(4.9),500)
        self.assertEqual(inspired_air(60),6000)
        self.assertEqual(inspired_air_rate(3),0)

    def test_mass_balance_and_monotonicity(self):
        previous=(0,0,0)
        for i in range(3001):
            s=calculate(i/25,20.9)
            current=(s["inspired_total_ml"],s["blood_total_ml"],s["tissues_total_ml"])
            for before,after in zip(previous,current):
                self.assertGreaterEqual(after+1e-9,before)
            self.assertLessEqual(s["tissues_total_ml"],s["blood_total_ml"]+1e-9)
            self.assertLessEqual(s["blood_total_ml"],.2*s["inspired_total_ml"]+1e-9)
            self.assertAlmostEqual(s["in_transit_ml"],s["blood_total_ml"]-s["tissues_total_ml"])
            previous=current

    def test_delays(self):
        self.assertEqual(calculate(.5,21)["blood_total_ml"],0)
        self.assertEqual(calculate(3.5,21)["tissues_total_ml"],0)
        self.assertGreater(calculate(.7,21)["blood_total_ml"],0)
        self.assertGreater(calculate(3.7,21)["tissues_total_ml"],0)

    def test_frame_rate_independence(self):
        sim_a=Simulation(clock=lambda:100)
        sim_b=Simulation(clock=lambda:100)
        sim_a.start(21);sim_b.start(21)
        # Промежуточные обращения не влияют на итоговый расчёт.
        for i in range(100):
            sim_a.clock=lambda i=i:100+i*.08
            sim_a.snapshot()
        sim_a.clock=lambda:109.33;sim_b.clock=lambda:109.33
        for key in ["elapsed_s","inspired_total_ml","blood_total_ml","tissues_total_ml"]:
            self.assertAlmostEqual(sim_a.snapshot()[key],sim_b.snapshot()[key])

    def test_pause_resume_reset(self):
        now=[100.]
        sim=Simulation(clock=lambda:now[0])
        self.assertEqual(sim.snapshot()["phase"],"idle")
        sim.start("20,9")
        now[0]=102.5
        paused=sim.pause()
        now[0]=199.
        self.assertEqual(sim.snapshot(),paused)
        sim.resume()
        now[0]=200.
        self.assertAlmostEqual(sim.elapsed(),3.5)
        reset=sim.reset()
        self.assertEqual(reset["status"],"idle")
        self.assertEqual(reset["inspired_total_ml"],0)
        self.assertEqual(reset["cycle_number"],0)
        self.assertEqual(reset["oxygen_percent"],20.9)

    def test_start_validation_is_atomic(self):
        sim=Simulation(clock=lambda:0)
        with self.assertRaises(ValueError):sim.start(101)
        self.assertEqual(sim.status,"idle")
        sim.start(21)
        with self.assertRaises(ValueError):sim.start(15)
        self.assertEqual(sim.oxygen_percent,21)

    def test_csv_includes_final_state(self):
        now=[0.]
        sim=Simulation(clock=lambda:now[0]);sim.start(21)
        now[0]=5.6;sim.pause()
        rows=sim.report_rows()
        self.assertEqual(len(rows[0]),7)
        self.assertEqual(rows[-1][0],"5,600")
        self.assertEqual(rows[-1][-1],"21,000")
        self.assertEqual(rows[-1][5],"21,000")


class GraphicsTests(unittest.TestCase):
    def test_geometry_loads(self):
        scene=SVGScene(Path(__file__).resolve().parents[1]/"interface.html")
        for node in scene.root.iter():
            if node.tag=="path":self.assertTrue(flatten_path(node.get("d")))
        for t in (0,.5,2,3.7,60):
            s=calculate(t,21);s["status"]="running"
            scene.update(s)
        self.assertGreater(scene.paths["blood-loop"].length,1000)

    def test_matrix(self):
        m=parse_transform("translate(10 20) scale(2) translate(-3 -4)")
        self.assertEqual(transform_point(m,3,4),(10,20))
        rotation=parse_transform("rotate(90 1 1)")
        x,y=transform_point(rotation,2,1)
        self.assertAlmostEqual(x,1);self.assertAlmostEqual(y,2)

    def test_polyline(self):
        from svg_canvas import Polyline
        path=Polyline("M0 0 L10 0 L10 10")
        self.assertEqual(path.length,20)
        self.assertEqual(path.at(5),(5,0))
        self.assertEqual(path.at(15),(10,5))
        self.assertEqual(path.at(30),(10,10))


if __name__=="__main__":
    unittest.main()
