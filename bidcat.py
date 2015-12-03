"""Logic to handle multiple users making "up-to" bids collaboratively.

Each user places bids on items by telling the auction system the most they're willing to bid and
have the system automatically bid on their behalf with the intent of securing the lowest price
possible, for example, if Alice bids 100 on "Item A" and Bob bids 1 on "Item B" Alice should win and pay 2.

Multiple users able to bid on the same item with their combined bids beating an overall smaller single bid.

All references to "money" in this module refers to an arbitrary indivisible integer unit of currency.

What is bidded on are called "items" and are referenced by strings or integers.

User IDs are strings or integers.
"""

import logging
import unittest

from banksys import InsufficientMoneyError


class Auction(object):
	"""Handles multiple users bidding on multiple items, only one item can win.

	All provided item IDs and user IDs are assumed to be valid.
	"""
	def __init__(self, bank):
		"""
		Arguments:
			bank: bank object to access to reserve currency
		"""
		# track bank
		self.bank = bank
		# set up logging
		self.log = logging.getLogger("auctionsys")
		#list to keep track of bids
		self.bids = []

	def clear(self):
		self.bids = []

	def register_reserved_money_checker(self):
		"""Adds the reserved money checker function at the bank.

		If this is used the function MUST be removed before the auction object is deleted!
		"""
		self.log.info("registering reserved money checker")
		self.bank.reserved_money_checker_functions.add(self.get_reserved_money)

	def deregister_reserved_money_checker(self):
		"""Removes the reserved money checker function from the bank.

		This MUST be called when the auction has been finished and fulfilled.
		"""
		self.log.info("deregistering reserved money checker")
		self.bank.reserved_money_checker_functions.remove(self.get_reserved_money)

	def get_reserved_money(self, user_id):
		"""Calculate the amount of money a user has tied up in the auction system.

		It is guaranteed that no more than this amount will be taken from the
		user's account without further action from this user.
		"""
		total=0
		for bid in self.bids:
			user,item,maxamt = bid
			if user == user_id:
				total += maxamt
		return total

	def place_bid(self, user_id, item_id, max_bid):
		if max_bid <= 0:
			raise ValueError("'max_bid' must be a value above 0")
		# ensure the user can afford it
		available_money = self.bank.get_available_money(user_id)
		reserved_money = self.bank.get_reserved_money(user_id)
		# TODO: consider how much is reserved by previous bids existence' on this item
		# determine amount of money spent on this
		if max_bid > available_money + reserved_money:
			raise InsufficientMoneyError("can't afford to make bid")

		#check that we're not replacing a bid
		for bid in self.bids:
			user,item,maxamt = bid
			if (user == user_id) and (item == item_id):
				#remove the old bid; adding the replacement bid happens at the same .append() as if the bid was new
				self.bids.remove(bid)
				break

		self.bids.append((user_id,item_id,max_bid))
		self.log.debug(str(user_id)+" placed bid for "+str(item_id)+": "+str(max_bid))

	def process_bids(self):
		"""Process everyone's bids and make any changes.

		Returns:
			dict containing information about what happened and the new state of the auction.
		"""

		highest_bid_item = (None,-1) #item_id, total money bid on this item
		second_highest_item = (None,-1)
		#todo: perhaps store self.bids indexed by item_id?

		bids_for_item = {}
		item_cost = {}
		for bid in self.bids:
			user,item_id,bidamt = bid
			if item_id not in bids_for_item:
				bids_for_item[item_id] = []
				item_cost[item_id] = 0
			item_cost[item_id] += bidamt
			bids_for_item[item_id].append(bid)

			#Now, keep track of the highest bid and the 2nd highest bid; the cost will be the 2nd highest bid amt + 1
			if item_cost[item_id] > highest_bid_item[1]:
				second_highest_item = highest_bid_item
				highest_bid_item = (item_id,item_cost[item_id])
			elif item_cost[item_id] > second_highest_item[1]:
				second_highest_item = (item_id,item_cost[item_id])
				
		winning_item = highest_bid_item[0]
		total_cost = second_highest_item[1]+1 #winner only bids 1 more than they must

		#well, unless there was only 1 bid, or if two bids tie (in which case the chronologically first bid wins).
		if(len(self.bids) == 1) or (highest_bid_item[1] == second_highest_item[1]): 
			total_cost = highest_bid_item[1]
		

		self.log.debug("Processed bids; winning item is "+str(winning_item)+", total cost is "+str(total_cost))

		return {
		"winning_bid": {
			"winning_item":winning_item,
			"total_cost":total_cost,
			"bids":bids_for_item[winning_item]
			},
		"all_bids":self.bids,
		}


def main():
	global auction
	from banksys import DummyBank
	logging.basicConfig(level=logging.INFO)
	bank = DummyBank()
	auction = Auction(bank=bank)
	auction.register_reserved_money_checker()
	unittest.main()
	auction.deregister_reserved_money_checker()

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


if __name__ == "__main__":
	main()
