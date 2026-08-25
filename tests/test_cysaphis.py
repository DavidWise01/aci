import unittest
from dataclasses import replace

from containment import ContainmentError, ContainmentKernel, Phase
from stargate import issue_ricky_key, issue_cysaphis, CYCLE_LENGTH


class CysaphisRollTests(unittest.TestCase):
    def contained(self):
        k = ContainmentKernel.for_system("ACI")
        k.define_containment(["north", "south", "east", "west"])
        k.witness("w0", True)
        k.witness("w1", True)
        k.witness("w2", False)
        self.assertEqual(k.phase, Phase.CONTAINMENT_VERIFIED)
        return k

    def test_full_bounded_cycle_returns_home(self):
        k = self.contained()
        r = issue_ricky_key(k, 0j, roll=0)
        c = issue_cysaphis(k, r)
        self.assertEqual([b.roll for b in c.bricks], [1,2,3,4,5,6,7,8,0])
        self.assertEqual(len(c.bricks), 9)
        self.assertEqual(c.total_hops, 81)
        self.assertTrue(c.home_returned)
        self.assertFalse(c.escaped)
        self.assertTrue(c.verify())

    def test_continues_from_ricky_final_z(self):
        k = self.contained()
        r = issue_ricky_key(k, -0.1 + 0.2j, roll=2)
        c = issue_cysaphis(k, r, rolls=1)
        self.assertEqual(c.bricks[0].start_z, r.route[-1].z)
        self.assertEqual(c.bricks[0].roll, 3)

    def test_each_brick_hash_links_parent(self):
        k = self.contained()
        r = issue_ricky_key(k, 0j)
        c = issue_cysaphis(k, r, rolls=4)
        parent = r.key_sha256
        for brick in c.bricks:
            self.assertEqual(brick.parent_sha256, parent)
            parent = brick.brick_sha256

    def test_tamper_breaks_chain(self):
        k = self.contained()
        r = issue_ricky_key(k, 0j)
        c = issue_cysaphis(k, r, rolls=2)
        bad0 = replace(c.bricks[0], parent_sha256="0" * 64)
        self.assertFalse(replace(c, bricks=(bad0,) + c.bricks[1:]).verify())

    def test_containment_redefinition_invalidates_chain(self):
        k = self.contained()
        r = issue_ricky_key(k, 0j)
        c = issue_cysaphis(k, r, rolls=2)
        k.define_containment(["a", "b", "c", "d"])
        self.assertFalse(c.valid_for(k))

    def test_escape_stops_rolling(self):
        k = self.contained()
        r = issue_ricky_key(k, -0.75 + 0.1j)
        c = issue_cysaphis(k, r)
        self.assertTrue(c.escaped)
        self.assertLess(len(c.bricks), CYCLE_LENGTH)
        self.assertFalse(c.home_returned)

    def test_escaped_ricky_cannot_roll(self):
        k = self.contained()
        r = issue_ricky_key(k, 2 + 0j)
        self.assertTrue(r.escaped)
        with self.assertRaises(ContainmentError):
            issue_cysaphis(k, r)

    def test_reverse_roll_returns_home(self):
        k = self.contained()
        r = issue_ricky_key(k, 0j, roll=4)
        c = issue_cysaphis(k, r, direction=-1)
        self.assertEqual([b.roll for b in c.bricks], [3,2,1,0,8,7,6,5,4])
        self.assertTrue(c.home_returned)

    def test_must_issue_before_plasma(self):
        k = self.contained()
        r = issue_ricky_key(k, 0j)
        k.arm_plasma()
        with self.assertRaises(ContainmentError):
            issue_cysaphis(k, r)

    def test_chain_stays_valid_through_plasma(self):
        k = self.contained()
        r = issue_ricky_key(k, 0j)
        c = issue_cysaphis(k, r, rolls=3)
        k.arm_plasma()
        self.assertTrue(c.valid_for(k))
        k.ignite_plasma()
        self.assertTrue(c.valid_for(k))


if __name__ == "__main__":
    unittest.main(verbosity=2)
