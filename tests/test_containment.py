import unittest
from containment import ContainmentError, ContainmentKernel, Phase


class ContainmentBeforePlasmaTests(unittest.TestCase):
    def establish(self, system: str):
        k = ContainmentKernel.for_system(system)
        count = k.profile.min_boundary_nodes
        k.define_containment([f"b{i}" for i in range(count)])
        k.witness("w0", True)
        k.witness("w1", True)
        k.witness("w2", False)
        self.assertEqual(k.phase, Phase.CONTAINMENT_VERIFIED)
        return k

    def test_plasma_cannot_arm_before_containment(self):
        for system in ("ACI", "CUBIS"):
            with self.subTest(system=system):
                k = ContainmentKernel.for_system(system)
                with self.assertRaises(ContainmentError):
                    k.arm_plasma()

    def test_requires_full_three_witness_quorum(self):
        k = ContainmentKernel.for_system("ACI")
        k.define_containment(["n", "s", "e", "w"])
        k.witness("w0", True)
        k.witness("w1", True)
        self.assertEqual(k.phase, Phase.CONTAINMENT_DEFINED)
        with self.assertRaises(ContainmentError):
            k.arm_plasma()
        k.witness("w2", False)
        self.assertEqual(k.phase, Phase.CONTAINMENT_VERIFIED)

    def test_aci_happy_path(self):
        k = self.establish("ACI")
        k.arm_plasma(); k.ignite_plasma()
        self.assertTrue(k.guard())
        self.assertEqual(k.phase, Phase.PLASMA_ACTIVE)
        self.assertTrue(k.verify_ledger())

    def test_cubis_happy_path(self):
        k = self.establish("CUBIS")
        k.arm_plasma(); k.ignite_plasma()
        self.assertTrue(k.guard())
        self.assertEqual(k.phase, Phase.PLASMA_ACTIVE)
        self.assertEqual(len(k.boundary), 6)

    def test_mutation_after_arm_fault_locks(self):
        k = self.establish("ACI")
        k.arm_plasma()
        with self.assertRaises(ContainmentError):
            k.define_containment(["a", "b", "c", "d"])
        self.assertEqual(k.phase, Phase.FAULT_LOCKED)

    def test_runtime_tamper_quenches(self):
        k = self.establish("CUBIS")
        k.arm_plasma(); k.ignite_plasma()
        k.witnesses["w0"] = False
        self.assertFalse(k.guard())
        self.assertEqual(k.phase, Phase.QUENCHED)

    def test_ledger_tamper_detected(self):
        k = self.establish("ACI")
        self.assertTrue(k.verify_ledger())
        k.ledger[0].payload["nodes"].append("tamper")
        self.assertFalse(k.verify_ledger())


if __name__ == "__main__":
    unittest.main(verbosity=2)
