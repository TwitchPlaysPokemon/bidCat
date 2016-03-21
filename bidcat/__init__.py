"""Logic to handle multiple users making "up-to" bids collaboratively.

Each user places bids on items by telling the auction system the most they're willing to bid and
have the system automatically bid on their behalf with the intent of securing the lowest price
possible, for example, if Alice bids 100 on "Item A" and Bob bids 1 on "Item B" Alice wins and pay 2.

Multiple users able to bid on the same item with their combined bids beating an overall smaller single bid. 
When this happens, the system will compute how many tokens to deduct from each user.

All references to "money" in this module refers to an arbitrary indivisible integer unit of currency.

What is bidded on are called "items" and are referenced by strings or integers.

User IDs are strings or integers.
"""

import logging

from collections import namedtuple

Bid = namedtuple("Bid", ["user_id", "item_id", "max_bid"])
class InsufficientMoneyError(Exception): pass

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
        """Clear all stored bids. After calling this, self.get_reserved_money() will also be reset to 0 for every user"""
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
            if bid.user_id == user_id:
                total += bid.max_bid
        return total

    def place_bid(self, user_id, item_id, max_bid):
        """Place a bid for the given item_id, max_bid, and user_id.

        Will raise an InsufficientMoneyError if the user_id does not have enough bank balance to make that bid.
        """
        if max_bid <= 0:
            raise ValueError("'max_bid' must be a value above 0")
        
        available_money = self.bank.get_available_money(user_id)
        reserved_money = self.bank.get_reserved_money(user_id)

        #check if we're replacing a bid
        for bid in self.bids:
            user,item,prev_bid_amt = bid
            if (bid.user_id == user_id) and (bid.item_id == item_id):
                new_amt_needed = max_bid - bid.max_bid
                if new_amt_needed > available_money:
                    self.log.info((max_bid,available_money,reserved_money))
                    raise InsufficientMoneyError("can't afford to make bid")

                #remove the old bid; adding the replacement bid happens at the same .append() as if the bid was new
                self.bids.remove(bid)
                break
        else:
            # It's a new bid
            if max_bid > available_money:
                raise InsufficientMoneyError("can't afford to make bid")

        self.bids.append(Bid(user_id, item_id, max_bid))
        self.log.debug(str(user_id)+" placed bid for "+str(item_id)+": "+str(max_bid))

    def process_bids(self):
        """Process everyone's bids and make any changes.

        Returns:
            dict containing info about the new state of the auction and the current winner.
            {
            "winning_bid": {
                "winning_item": the item that is currently winning
                "total_cost": the sum of the bids for that item
                "bids": an array containing namedtuples of (user_id, item_id, max_bid) with item==winning item
                "amounts_owed": dict mapping user_id to the computed money they will pay
                },
            "all_bids": dict containing all (user_id, item, amt_bid) tuples for all items
            }
            If no bids have been placed, "winning_bid" will be None.
        """

        highest_bid_item = (None,-1) #item_id, total money bid on this item
        second_highest_item = (None,-1)

        bids_for_item = {}
        item_cost = {}
        for bid in self.bids:
            if bid.item_id not in bids_for_item:
                bids_for_item[bid.item_id] = []
                item_cost[bid.item_id] = 0
            item_cost[bid.item_id] += bid.max_bid
            bids_for_item[bid.item_id].append(bid)

            #Now, keep track of the highest bid and the 2nd highest bid
            if item_cost[bid.item_id] > highest_bid_item[1]:
                #The same item shouldn't be both first and 2nd highest
                if bid.item_id != highest_bid_item[0]:
                    second_highest_item = highest_bid_item
                highest_bid_item = (bid.item_id,item_cost[bid.item_id])
            elif item_cost[bid.item_id] > second_highest_item[1]:
                second_highest_item = (bid.item_id,item_cost[bid.item_id])
                
        winning_item = highest_bid_item[0]
        total_cost = second_highest_item[1]+1 #winner only bids 1 more than they must

        #well, unless there was only 1 bid, or if two bids tie (in which case the chronologically first bid wins).
        if(len(self.bids) == 1) or (highest_bid_item[1] == second_highest_item[1]): 
            total_cost = highest_bid_item[1]

        #If there aren't any bids, then there aren't any bids for the winning item, either.
        if winning_item == None:
            return {
                "winning_bid": None,
                "all_bids":self.bids,
            }

        #Now, compute who pays what using everyone-owes-equally
        sortedbids = sorted(bids_for_item[winning_item],key=lambda bid:bid[2],reverse=True)

        alloting = {}
        #start by making each person owe 0 tokens
        for bid in sortedbids:
            alloting[bid[0]] = 0

        allotted = 0
        bid_number = 0
        amt_users = len(sortedbids)
        while allotted < total_cost: #This loop is inefficient for big bids (>1000)
            user_id,item,bid_amt = sortedbids[bid_number]
            if alloting[user_id] < bid_amt:
                alloting[user_id] += 1
                allotted += 1
            bid_number = (bid_number+1)%amt_users
        

        self.log.debug("Processed bids; winning item is "+str(winning_item)+", total cost is "+str(total_cost))

        return {
        "winning_bid": {
            "winning_item":winning_item,
            "total_cost":total_cost,
            "bids":bids_for_item[winning_item],
            "amounts_owed":alloting
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
