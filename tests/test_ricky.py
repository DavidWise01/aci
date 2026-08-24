import unittest

from containment import ContainmentError, ContainmentKernel, Phase
from stargate import RICKY_PATTERN, RICKY_PATTERN_TEXT, issue_ricky_key, roll_pattern


class RickyMandelbrotWandererTests(unittest.TestCase):
    def contained(self):
        k = ContainmentKernel.for_system("ACI")
        k.define_containment(["north", "south", "east", "west"])
        k.witness("w0", True)
        k.witness("w1", True)
        k.witness("w2", False)
        self.assertEqual(k.phase, Phase.CONTAINMENT_VERIFIED)
        return k

    def test_brick_is_exact_nine_symbol_key(self):
        self.assertEqual(RICKY_PATTERN_TEXT, "{. . | | . . | . .}")
        self.assertEqual(len(RICKY_PATTERN), 9)
        self.assertEqual(RICKY_PATTERN.count("|"), 3)

    def test_roll_is_cyclic_and_reversible(self):
        self.assertEqual(roll_pattern(0), RICKY_PATTERN)
        self.assertEqual(roll_pattern(9), RICKY_PATTERN)
        self.assertEqual(roll_pattern(1)[0], RICKY_PATTERN[-1])
        self.assertEqual(roll_pattern(-1)[-1], RICKY_PATTERN[0])

    def test_c_zero_wanders_all_nine_hops(self):
        k = self.contained()
        key = issue_ricky_key(k, 0j)
        self.assertFalse(key.escaped)
        self.assertEqual(len(key.route), 9)
        self.assertEqual(key.checkpoint_hops, (3, 4, 7))
        self.assertTrue(all(step.z == 0j for step in key.route))
        self.assertTrue(key.verify())
        self.assertTrue(key.valid_for(k))

    def test_escape_terminates_route(self):
        k = self.contained()
        key = issue_ricky_key(k, 2 + 0j)
        self.assertTrue(key.escaped)
        self.assertEqual(len(key.route), 2)
        self.assertTrue(key.route[-1].escaped)

    def test_key_cannot_issue_before_containment(self):
        k = ContainmentKernel.for_system("ACI")
        with self.assertRaises(ContainmentError):
            issue_ricky_key(k, -0.75 + 0.1j)

    def test_key_binds_to_containment_seal(self):
        k = self.contained()
        key = issue_ricky_key(k, -0.75 + 0.1j, roll=3)
        old_seal = key.containment_seal
        k.define_containment(["a", "b", "c", "d"])
        self.assertNotEqual(k.boundary_seal, old_seal)
        self.assertFalse(key.valid_for(k))

    def test_key_survives_arm_if_seal_is_unchanged(self):
        k = self.contained()
        key = issue_ricky_key(k, -0.1 + 0.65j, roll=1)
        k.arm_plasma()
        self.assertTrue(key.valid_for(k))
        k.ignite_plasma()
        self.assertTrue(key.valid_for(k))

    def test_same_inputs_produce_same_key(self):
        k = self.contained()
        a = issue_ricky_key(k, -0.8 + 0.156j, roll=4)
        b = issue_ricky_key(k, -0.8 + 0.156j, roll=4)
        self.assertEqual(a.key_sha256, b.key_sha256)
        self.assertEqual(a.route, b.route)


if __name__ == "__main__":
    unittest.main(verbosity=2)
