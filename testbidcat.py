import unittest
from bidcat import Auction

class AuctionsysTester(unittest.TestCase):
	def test_bids(self):
		auction.clear()
		auction.place_bid("bob", "pepsiman", 1)
		bids = auction.process_bids()["all_bids"]
		self.assertEqual(bids,[("bob","pepsiman",1)])

		auction.place_bid("alice", "katamari", 2)
		bids = auction.process_bids()["all_bids"]
		self.assertEqual(bids,[("bob","pepsiman",1),("alice","katamari",2)])

		#if another bid has the same user_id and item_id as previously seen, remove the old bid
		auction.place_bid("bob", "pepsiman", 2)
		bids = auction.process_bids()["all_bids"]
		self.assertEqual(bids,[("alice","katamari",2),("bob","pepsiman",2)])

	def test_incremental_bidding(self):
		auction.clear()
		auction.place_bid("bob", "pepsiman", 100)
		auction.place_bid("alice", "katamari", 2)

		result = auction.process_bids()
		#Bob should pay 1 more than the next-lowest bid of 2
		self.assertEqual(result["winning_bid"]["total_cost"],3)

		#now, test it with collaboration
		auction.clear()
		auction.place_bid("bob", "pepsiman", 4)
		auction.place_bid("alice", "katamari", 5)
		auction.place_bid("cirno", "pepsiman", 4) #sorry; couldn't think of a good c-name

		result = auction.process_bids()
		self.assertEqual(result["winning_bid"]["total_cost"],6)
		self.assertEqual(result["winning_bid"]["winning_item"],"pepsiman")

		#If there's only 1 bid, they should pay the amt they bid
		auction.clear()
		auction.place_bid("bob", "pepsiman", 100)
		result = auction.process_bids()
		self.assertEqual(result["winning_bid"]["total_cost"],100)
		self.assertEqual(result["winning_bid"]["winning_item"],"pepsiman")

		#ties shouldn't change the winner
		auction.place_bid("deku", "unfinished_battle", 100)
		result = auction.process_bids()
		self.assertEqual(result["winning_bid"]["winning_item"],"pepsiman")
		self.assertEqual(result["winning_bid"]["total_cost"],100)


	def test_winning(self):
		auction.clear()
		auction.place_bid("bob", "pepsiman", 3)
		auction.place_bid("alice", "katamari", 2)
		result = auction.process_bids()
		self.assertEqual(result["winning_bid"]["winning_item"],"pepsiman")

		#new bids for the same item should override previous wins
		auction.place_bid("cirno", "unfinished_battle", 5)
		auction.place_bid("alice", "katamari", 4)
		result = auction.process_bids()
		self.assertEqual(result["winning_bid"]["winning_item"],"unfinished_battle")

		#if a new bid is equal to the winner, the winning item shouldn't change
		auction.place_bid("alice", "katamari", 5)
		result = auction.process_bids()
		self.assertEqual(result["winning_bid"]["winning_item"],"unfinished_battle")

		

	def test_collaborative(self):
		auction.clear()
		auction.place_bid("bob", "pepsiman", 1)
		auction.place_bid("alice", "katamari", 3)
		auction.place_bid("cirno", "unfinished_battle", 1)

		result = auction.process_bids()
		self.assertEqual(result["winning_bid"]["winning_item"],"katamari")
		
		#ties shouldn't change the winner
		auction.place_bid("deku", "unfinished_battle", 2)
		result = auction.process_bids()
		self.assertEqual(result["winning_bid"]["winning_item"],"katamari")

		#cirno's 1 + deku's 3=4, so the winner should change
		auction.place_bid("deku", "unfinished_battle", 3)
		result = auction.process_bids()
		self.assertEqual(result["winning_bid"]["winning_item"],"unfinished_battle")
		self.assertEqual(result["winning_bid"]["total_cost"],4)

		#todo: test result["winning_bid"]["bids"], which should be a list of all bids for the winning item

	def test_reserved(self):
		auction.clear()
		auction.place_bid("bob", "peach", 4)
		auction.place_bid("cirno", "peach", 9)
		auction.place_bid("alice", "yoshi", 3)

		self.assertEqual(auction.get_reserved_money("alice"),3)
		self.assertEqual(auction.get_reserved_money("bob"),4)
		self.assertEqual(auction.get_reserved_money("cirno"),9)
		#If not in the system yet, there should be no money reserved
		self.assertEqual(auction.get_reserved_money("deku"),0)

	def test_winning_bids(self):
		auction.clear()
		auction.place_bid("cirno", "pepsiman", 2)
		auction.place_bid("alice", "katamari", 2)
		auction.place_bid("bob", "pepsiman", 4)
		auction.place_bid("deku", "unfinished_battle", 3)
		#some bids get upgraded
		auction.place_bid("alice", "katamari", 5)
		auction.place_bid("cirno", "pepsiman", 4)

		result = auction.process_bids()
		self.assertEqual(result["winning_bid"]["winning_item"],"pepsiman")

		for bid in result["winning_bid"]["bids"]:
			self.assertEqual(bid[1], result["winning_bid"]["winning_item"])

	def test_insufficient_money(self):
		self.assertEqual(1,0) #todo: implement

	def test_collaborative_owing(self):
		self.assertEqual(1,0) #todo: implement

if __name__ == "__main__":
	global auction
	from banksys import DummyBank
	logging.basicConfig(level=logging.INFO)
	bank = DummyBank()
	auction = Auction(bank=bank)
	auction.register_reserved_money_checker()
	unittest.main()
	auction.deregister_reserved_money_checker()
