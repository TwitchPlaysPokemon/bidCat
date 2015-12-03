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
		#self.log.debug(str(user_id)+" placed bid for "+str(item_id)+": "+str(max_bid))

	def process_bids(self):
		"""Process everyone's bids and make any changes.

		Returns:
			dict containing information about what happened and the new state of the auction.
		"""

		winningItem = None
		maxCost = -1
		#todo: perhaps store self.bids indexed by item_id?

		itemInfo = {}
		for bid in self.bids:
			user,item_id,bidamt = bid
			if item_id not in itemInfo:
				itemInfo[item_id] = [0,[]]
			itemInfo[item_id][0] += bidamt #add to total
			itemInfo[item_id][1].append(bid)
			#see if the total is the highest, for collaborative bidding
			if itemInfo[item_id][0] > maxCost:
				maxCost = itemInfo[item_id][0]
				winningItem = item_id
				

		return {
		"winningBid": {
			"winningItem":winningItem,
			"totalCost":maxCost,
			"bids":[]
			},
		"allBids":self.bids,
		"allEvents":[]
		}


def main():
	global auction
	from banksys import DummyBank
	logging.basicConfig(level=logging.DEBUG)
	bank = DummyBank()
	auction = Auction(bank=bank)
	auction.register_reserved_money_checker()
	unittest.main()
	auction.deregister_reserved_money_checker()

class Auctionsys_tester(unittest.TestCase):
	def test_bids(self):
		auction.clear()
		auction.place_bid("bob", "pepsiman", 1)
		bids = auction.process_bids()["allBids"]
		self.assertEqual(bids,[("bob","pepsiman",1)])

		auction.place_bid("alice", "katamari", 2)
		bids = auction.process_bids()["allBids"]
		self.assertEqual(bids,[("bob","pepsiman",1),("alice","katamari",2)])

		#if another bid has the same user_id and item_id as previously seen, remove the old bid
		auction.place_bid("bob", "pepsiman", 2)
		bids = auction.process_bids()["allBids"]
		self.assertEqual(bids,[("alice","katamari",2),("bob","pepsiman",2)])

	def test_incremental_bidding(self):
		auction.clear()
		auction.place_bid("bob", "pepsiman", 100)
		auction.place_bid("alice", "katamari", 2)

		result = auction.process_bids()
		#Bob should pay 1 more than the next-lowest bid of 2
		self.assertEqual(result["winningBid"]["totalCost"],3)

		#now, test it with collaboration
		auction.clear()
		auction.place_bid("bob", "pepsiman", 4)
		auction.place_bid("alice", "katamari", 5)
		auction.place_bid("cirno", "pepsiman", 4) #sorry; couldn't think of a good c-name

		result = auction.process_bids()
		self.assertEqual(result["winningBid"]["totalCost"],6)
		self.assertEqual(result["winningBid"]["winningItem"],"pepsiman")


	def test_winning(self):
		auction.clear()
		auction.place_bid("bob", "pepsiman", 3)
		auction.place_bid("alice", "katamari", 2)
		result = auction.process_bids()
		self.assertEqual(result["winningBid"]["winningItem"],"pepsiman")

		#new bids for the same item should override previous wins
		auction.place_bid("cirno", "unfinished_battle", 5)
		auction.place_bid("alice", "katamari", 4)
		result = auction.process_bids()
		self.assertEqual(result["winningBid"]["winningItem"],"unfinished_battle")

		#if a new bid is equal to the winner, the winning item shouldn't change
		auction.place_bid("alice", "katamari", 5)
		result = auction.process_bids()
		self.assertEqual(result["winningBid"]["winningItem"],"unfinished_battle")

		

	def test_collaborative(self):
		auction.clear()
		auction.place_bid("bob", "pepsiman", 1)
		auction.place_bid("alice", "katamari", 3)
		auction.place_bid("cirno", "unfinished_battle", 1)

		result = auction.process_bids()
		self.assertEqual(result["winningBid"]["winningItem"],"katamari")
		
		#ties shouldn't change the winner
		auction.place_bid("deku", "unfinished_battle", 2)
		result = auction.process_bids()
		self.assertEqual(result["winningBid"]["winningItem"],"katamari")

		#cirno's 1 + deku's 3=4, so the winner should change
		auction.place_bid("deku", "unfinished_battle", 3)
		result = auction.process_bids()
		print(result["allBids"])
		self.assertEqual(result["winningBid"]["winningItem"],"unfinished_battle")
		self.assertEqual(result["winningBid"]["totalCost"],4)

		#todo: test result["winningBid"]["bids"], which should be a list of all bids for the winning item

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
		
		#todo: test result["winningBid"]["bids"], which should be a list of all bids for the winning item
if __name__ == "__main__":
	main()
