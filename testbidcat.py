import unittest
import logging
from bidcat import Auction, InsufficientMoneyError, AlreadyBidError, NoExistingBidError


class AuctionsysTester(unittest.TestCase):
    def setUp(self):
        from banksys import DummyBank
        self.max_money = 1000
        self.bank = DummyBank()
        self.bank._starting_amount = self.max_money  # TODO don't fiddle with other's privates
        self.auction = Auction(bank=self.bank)
        self.auction.register_reserved_money_checker()

    def tearDown(self):
        self.auction.deregister_reserved_money_checker()

    def test_single_bid(self):
        self.auction.place_bid("alice", "pepsiman", 1)
        winner = self.auction.get_winner()
        self.assertEqual(winner["item"], "pepsiman")
        self.assertEqual(winner["money_owed"], {"alice": 1})
        self.assertEqual(winner["total_bid"], 1)
        self.assertEqual(winner["total_charge"], 1)

    def test_bid_registering(self):
        self.auction.place_bid("alice", "pepsiman", 1)
        bids = self.auction.get_all_bids()
        self.assertEqual(bids, {"pepsiman": {"alice": 1}})
        bids = self.auction.get_bids_for_item("pepsiman")
        self.assertEqual(bids, {"alice": 1})
        bids = self.auction.get_bids_for_user("alice")
        self.assertEqual(bids, {"pepsiman": 1})

    def test_more_bids_registering(self):
        self.auction.place_bid("alice", "pepsiman", 5)
        self.auction.place_bid("bob", "pepsiman", 10)
        self.auction.place_bid("charlie", "katamari", 42)
        bids = self.auction.get_all_bids()
        self.assertEqual(bids, {
            "pepsiman": {"alice": 5, "bob": 10},
            "katamari": {"charlie": 42},
        })

    def test_two_bids(self):
        self.auction.place_bid("alice", "pepsiman", 1)
        self.auction.place_bid("bob", "katamari", 10)
        winner = self.auction.get_winner()
        self.assertEqual(winner["item"], "katamari")
        self.assertEqual(winner["money_owed"], {"bob": 2})
        self.assertEqual(winner["total_bid"], 10)
        self.assertEqual(winner["total_charge"], 2)

    def test_collaboration(self):
        self.auction.place_bid("alice", "pepsiman", 1)
        self.auction.place_bid("bob", "pepsiman", 1)
        self.auction.place_bid("charlie", "katamari", 1)
        # pepsiman should win with 2 money
        winner = self.auction.get_winner()
        self.assertEqual(winner["item"], "pepsiman")
        self.assertEqual(winner["money_owed"], {"alice": 1, "bob": 1})
        self.assertEqual(winner["total_bid"], 2)
        self.assertEqual(winner["total_charge"], 2)

    def test_one_overpaid(self):
        self.auction.place_bid("alice", "pepsiman", 10)
        # pepsiman should win with 1 money
        winner = self.auction.get_winner()
        self.assertEqual(winner["item"], "pepsiman")
        self.assertEqual(winner["money_owed"], {"alice": 1})
        self.assertEqual(winner["total_bid"], 10)
        self.assertEqual(winner["total_charge"], 1)

    def test_multi_overpaid(self):
        self.auction.place_bid("alice", "pepsiman", 10)
        self.auction.place_bid("bob", "katamari", 5)
        # pepsiman should win with 6 money
        winner = self.auction.get_winner()
        self.assertEqual(winner["item"], "pepsiman")
        self.assertEqual(winner["money_owed"], {"alice": 6})
        self.assertEqual(winner["total_bid"], 10)
        self.assertEqual(winner["total_charge"], 6)

    def test_favor_first_item(self):
        self.auction.place_bid("alice", "pepsiman", 3)
        self.auction.place_bid("bob", "katamari", 3)
        # pepsiman should win with 3 money
        winner = self.auction.get_winner()
        self.assertEqual(winner["item"], "pepsiman")
        self.assertEqual(winner["money_owed"], {"alice": 3})
        self.assertEqual(winner["total_bid"], 3)
        self.assertEqual(winner["total_charge"], 3)

    def test_favor_first_bidder(self):
        self.auction.place_bid("alice", "pepsiman", 1)
        self.auction.place_bid("bob", "pepsiman", 1)
        # pepsiman should win with 1 money, and bob should pay
        winner = self.auction.get_winner()
        self.assertEqual(winner["item"], "pepsiman")
        self.assertEqual(winner["money_owed"], {"alice": 0, "bob": 1})
        self.assertEqual(winner["total_bid"], 2)
        self.assertEqual(winner["total_charge"], 1)

    def test_distribute_cost(self):
        self.auction.place_bid("alice", "pepsiman", 5)
        self.auction.place_bid("bob", "pepsiman", 10)
        self.auction.place_bid("charlie", "katamari", 5)
        # pepsiman should win with 6 money
        # alice should pay 2, and bob 4
        winner = self.auction.get_winner()
        self.assertEqual(winner["item"], "pepsiman")
        self.assertEqual(winner["money_owed"], {"alice": 2, "bob": 4})
        self.assertEqual(winner["total_bid"], 15)
        self.assertEqual(winner["total_charge"], 6)

    def test_odd_distribution(self):
        self.auction.place_bid("alice", "pepsiman", 2)
        self.auction.place_bid("bob", "pepsiman", 2)
        self.auction.place_bid("charlie", "pepsiman", 2)
        self.auction.place_bid("deku", "pepsiman", 2)
        self.auction.place_bid("ennopp", "katamari", 5)
        # pepsiman should win with 6 money
        # alice and bob should pay 1
        # charlie and deku should pay 2
        winner = self.auction.get_winner()
        self.assertEqual(winner["item"], "pepsiman")
        self.assertEqual(winner["money_owed"], {
            "alice": 1,
            "bob": 1,
            "charlie": 2,
            "deku": 2,
        })
        self.assertEqual(winner["total_bid"], 8)
        self.assertEqual(winner["total_charge"], 6)

    def test_not_enough_money(self):
        self.assertRaises(
            InsufficientMoneyError,
            self.auction.place_bid,
            "alice",
            "pepsiman",
            self.max_money + 1,
        )

    def test_enough_money_for_replace(self):
        self.auction.place_bid("alice", "pepsiman", self.max_money - 1)
        self.auction.replace_bid("alice", "pepsiman", self.max_money)

    def test_enough_money_for_increase(self):
        self.auction.place_bid("alice", "pepsiman", self.max_money - 1)
        self.auction.increase_bid("alice", "pepsiman", 1)
        self.assertRaises(
            InsufficientMoneyError,
            self.auction.increase_bid,
            "alice",
            "pepsiman",
            1,
        )

    def test_increase_bet(self):
        self.auction.place_bid("alice", "pepsiman", 1)
        self.auction.increase_bid("alice", "pepsiman", 1)
        bids = self.auction.get_all_bids()
        self.assertEqual(bids, {"pepsiman": {"alice": 2}})

    def test_replace_bet(self):
        self.auction.place_bid("alice", "pepsiman", 2)
        self.auction.replace_bid("alice", "pepsiman", 1)
        bids = self.auction.get_all_bids()
        self.assertEqual(bids, {"pepsiman": {"alice": 1}})

    def test_decrease_to_tie(self):
        self.auction.place_bid("alice", "pepsiman", 2)
        self.auction.place_bid("bob", "katamari", 1)
        self.auction.replace_bid("alice", "pepsiman", 1)
        # katamari should win this!
        winner = self.auction.get_winner()
        self.assertEqual(winner["item"], "katamari")

    def test_increase_to_tie(self):
        self.auction.place_bid("alice", "pepsiman", 1)
        self.auction.place_bid("bob", "katamari", 2)
        self.auction.increase_bid("alice", "pepsiman", 1)
        # katamari should win this!
        winner = self.auction.get_winner()
        self.assertEqual(winner["item"], "katamari")

    def test_overtake(self):
        self.auction.place_bid("alice", "pepsiman", 1)
        self.auction.place_bid("bob", "katamari", 2)
        self.auction.increase_bid("alice", "pepsiman", 2)
        # pepsiman should win this!
        winner = self.auction.get_winner()
        self.assertEqual(winner["item"], "pepsiman")

    def test_no_winner(self):
        winner = self.auction.get_winner()
        self.assertEqual(winner, None)

    def test_remove(self):
        self.auction.place_bid("alice", "pepsiman", 1)
        self.auction.place_bid("bob", "katamari", 1)
        removed = self.auction.remove_bid("alice", "pepsiman")
        self.assertTrue(removed)
        bids = self.auction.get_all_bids()
        self.assertEqual(bids, {"katamari": {"bob": 1}})

    def test_remove_from_empty_auction(self):
        bids = self.auction.get_all_bids()
        self.assertEqual(bids, {})

        # empty remove should do nothing
        removed = self.auction.remove_bid("alice", "pepsiman")
        self.assertFalse(removed)

        bids = self.auction.get_all_bids()
        self.assertEqual(bids, {})

        # removing with an existing user should also do nothing
        self.auction.place_bid("alice", "pepsiman", 1)
        removed = self.auction.remove_bid("alice", "katamari")
        self.assertFalse(removed)

        # the old bid should still be around
        bids = self.auction.get_all_bids()
        self.assertEqual(bids["pepsiman"], {"alice": 1})

        # removing all bids means no bids exist
        removed = self.auction.remove_bid("alice", "pepsiman")
        self.assertTrue(removed)
        bids = self.auction.get_all_bids()
        self.assertEqual(bids, {})

    def test_clear(self):
        self.auction.place_bid("alice", "pepsiman", 1)
        self.auction.place_bid("bob", "katamari", 1)
        self.auction.clear()
        bids = self.auction.get_all_bids()
        self.assertEqual(bids, {})
        winner = self.auction.get_winner()
        self.assertEqual(winner, None)

    def test_bid_twice(self):
        self.auction.place_bid("alice", "pepsiman", 1)
        self.assertRaises(
            AlreadyBidError,
            self.auction.place_bid,
            "alice",
            "pepsiman",
            1,
        )

    def test_replace_nonexistent(self):
        self.assertRaises(
            NoExistingBidError,
            self.auction.replace_bid,
            "alice",
            "pepsiman",
            1,
        )

    def test_increase_nonexistent(self):
        self.assertRaises(
            NoExistingBidError,
            self.auction.increase_bid,
            "alice",
            "pepsiman",
            1,
        )

    def test_manual_replace(self):
        self.auction.place_bid("alice", "pepsiman", 1)
        self.auction.remove_bid("alice", "pepsiman")
        self.auction.place_bid("alice", "pepsiman", 1)

    # no exception

    def test_get_all_bids_ordered(self):
        self.auction.place_bid("alice", "pepsiman", 1)
        self.auction.place_bid("bob", "katamari", 2)
        self.auction.place_bid("charlie", "catz", 2)
        bids = self.auction.get_all_bids_ordered()
        self.assertEqual(bids, [
            ("katamari", {"bob": 2}),
            ("catz", {"charlie": 2}),
            ("pepsiman", {"alice": 1}),
        ])

    def test_favor_earlier_after_replace(self):
        self.auction.place_bid("alice", "pepsiman", 3)
        self.auction.place_bid("bob", "pepsiman", 2)
        self.auction.replace_bid("alice", "pepsiman", 2)
        self.auction.place_bid("charlie", "katamari", 2)
        # alice decreased to 2, so her bet is "newer".
        # should favor bob, so bob should pay 1 and alice 2
        money_owed = self.auction.get_winner()["money_owed"]
        self.assertEqual(money_owed, {
            "alice": 2,
            "bob": 1,
        })

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    unittest.main()
