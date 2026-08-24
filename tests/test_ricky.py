import unittest

from stargate import MandelbrotWanderer, RickyKey, mandelbrot_escape


class RickyKeyTests(unittest.TestCase):
    def test_source_shape_and_name(self):
        key = RickyKey()
        self.assertEqual(key.name, "Ricky")
        self.assertEqual(key.compact, "..||..|..")
        self.assertEqual(len(key.walls), 3)
        self.assertEqual(len(key.openings), 5)
        self.assertEqual(key.cells[1][1], ".")

    def test_four_rolls_return_home(self):
        key = RickyKey()
        rolled = key.roll().roll().roll().roll()
        self.assertEqual(rolled.cells, key.cells)
        self.assertEqual(rolled.quarter_turns, 0)
        self.assertEqual(rolled.seal, key.seal)

    def test_roll_changes_orientation(self):
        key = RickyKey()
        rolled = key.roll()
        self.assertNotEqual(rolled.compact, key.compact)
        self.assertEqual(rolled.quarter_turns, 1)
        self.assertEqual(len(rolled.walls), 3)

    def test_mandelbrot_escape_known_points(self):
        self.assertEqual(mandelbrot_escape(0j, 32), 32)
        self.assertLess(mandelbrot_escape(2 + 2j, 32), 32)

    def test_wander_is_deterministic_and_rolls(self):
        a = MandelbrotWanderer()
        b = MandelbrotWanderer()
        pa = a.walk(12)
        pb = b.walk(12)
        self.assertEqual(pa, pb)
        self.assertEqual([s.roll for s in pa[:5]], [0, 1, 2, 3, 0])
        self.assertEqual(a.key.quarter_turns, 0)

    def test_wander_moves_and_prefers_unvisited(self):
        w = MandelbrotWanderer(step_size=0.005)
        path = w.walk(16)
        points = [(round(s.position.real, 12), round(s.position.imag, 12)) for s in path]
        self.assertGreater(len(set(points)), 12)

    def test_admission_requires_verified_containment(self):
        from containment import ContainmentKernel
        key = RickyKey()
        k = ContainmentKernel.for_system("ACI")
        with self.assertRaises(RuntimeError):
            key.admission_token(k)
        k.define_containment(["n", "s", "e", "w"])
        k.witness("w0", True)
        k.witness("w1", True)
        k.witness("w2", False)
        token = key.admission_token(k)
        self.assertEqual(len(token), 64)


if __name__ == "__main__":
    unittest.main(verbosity=2)
