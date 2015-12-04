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
	from banksys import DummyBank
	logging.basicConfig(level=logging.DEBUG)
	bank = DummyBank()
	auction = Auction(bank=bank)
	auction.register_reserved_money_checker()
	auction.place_bid("bob", "pepsiman", 1)
	print(auction.process_bids())
	auction.place_bid("alice", "katamari", 2)
	print(auction.process_bids())
	auction.place_bid("bob", "pepsiman", 2)
	print(auction.process_bids())
	auction.deregister_reserved_money_checker()

if __name__ == "__main__":
	main()
