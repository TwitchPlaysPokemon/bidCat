"""Logic to handle multiple users making "up-to" bids collaboratively.

Each user places bids on items by telling the auction system the most they're willing to bid and
have the system automatically bid on their behalf with the intent of securing the lowest price
possible, for example, if Alice bids 100 on "Item A" and Bob bids 1 on "Item B" Alice wins and pay 2.

Multiple users able to bid on the same item with their combined bids beating an overall smaller single bid. 
When this happens, the system will compute how many tokens to deduct from each user.

All references to "money" in this module refers to an arbitrary indivisible integer unit of currency.

What is bidded on are called "items" and are any hashable objects.
The bidding entities called "users" are any hashable objects.
"""

from contextlib import suppress
from collections import defaultdict, OrderedDict
from math import ceil
from operator import itemgetter


class InsufficientMoneyError(Exception): pass

class Auction:
    """Handles multiple users bidding on multiple items, only one item can win.
    All provided items and users must be hashable."""
    def __init__(self, bank):
        """Arguments:
            bank: the bank object the auction checks and reserves users' money in."""
        self.bank = bank
        self.bank.reserved_money_checker_functions.add(self.get_reserved_money)
        # item -> user -> amount
        self._itembids = defaultdict(OrderedDict)
        # keep an order of when items got updated.
        # if 2 items tie in price, the one least recently updates wins.
        self._changes_tracker = []

    def register_reserved_money_checker(self):
        """Adds the reserved money checker function to the bank.
        If this is used the function MUST be removed before the auction object is deleted!
        """
        self.bank.reserved_money_checker_functions.add(self.get_reserved_money)

    def deregister_reserved_money_checker(self):
        """Removes the reserved money checker function from the bank.
        This MUST be called when the auction has been finished and fulfilled.
        To just reset and reuse the auction, use reset()
        """
        self.bank.reserved_money_checker_functions.remove(self.get_reserved_money)

    def get_reserved_money(self, user):
        """Returns the amount of money the user has reserved in this auction."""
        return sum(self.get_bids_for_user(user).values())

    def clear(self):
        """Removes all bids."""
        self._itembids.clear()

    def _update_last_change(self, item):
        """Call when the money bid on an item changed.
        Moves that item to the end of the change tracker list."""
        with suppress(ValueError):
            self._changes_tracker.remove(item)
        self._changes_tracker.append(item)

    def place_bid(self, user, item, amount, add=False):
        """For that user, bids the given amount on the given item.
        If add is True, adds the amount onto the bet instead of replacing."""
        if amount < 1:
            raise ValueError("amount must be a number above 0.")
        previous_amount = self._itembids[item].pop(user, 0)
        if add:
            amount += previous_amount
        elif previous_amount == amount:
            # no change
            return
        available_money = self.bank.get_available_money(user)
        if amount > available_money:
            raise InsufficientMoneyError("Can't affort to bid {}, only {} available."
                                         .format(amount, available_money))
        self._update_last_change(item)
        self._itembids[item][user] = amount

    def remove_bid(self, user, item):
        """For that user, removes his bid on that item.
        Returns True if a bid was removed, or False if there was no bid."""
        try:
            del self._itembids[item][user]
        except KeyError:
            return False
        # remove if now empty
        if self._itembids[item]: 
            self._update_last_change(item)
        else:
            del self._itembids[item]
            self._changes_tracker.remove(item)
        return True

    def get_bids_for_user(self, user):
        """Returns a dict(item:amount) of that user's bids."""
        bids = {}
        for item, userbids in self._itembids.items():
            with suppress(KeyError):
                bids[item] = userbids[user]
        return bids

    def get_bids_for_item(self, item):
        """Returns a dict(user:amount) of bids on that item."""
        return self._itembids.get(item, {})

    def get_all_bids(self):
        """Returns all bids as dict(item:dict(user:amount))"""
        return self._itembids

    def get_winner(self):
        """Calculated the item currently winning.
        Returns None if no bids, or a dict structured like this:
        {
            "item": identifier of the item that won
            "money_max": total max sum of money from bids on this item.
            "money_actual": actual sum of money that would currently be paid.
                This can be less than money_max if there is a gap to the 2nd highest bid.
            "money_owed": dict(user:money) containing the amount of money to pay
                allotted between all bidders. It's sum is money_actual
        }"""
        # get items sorted by total money first, and then by least recently updated
        # (~= first bid wins if tied)
        def by_amount_and_last_update(dictitem):
            item, bids = dictitem
            # smaller = first, therefore sum is negated.
            # but index of recent updates is not, because smaller = ealier, as desired
            return (-sum(bids.values()), self._changes_tracker.index(item))
        ordered = sorted(self._itembids.items(), key=by_amount_and_last_update)
        if not ordered:
            # no bids
            return None
        # extract the winner, save the rest
        (winning_item, winning_bids), *rest = ordered
        # determine the second highest bet amount
        second_bid = 0
        if rest:
            _, second_item_bids = rest[0]
            second_bid = sum(second_item_bids.values())
        # determine what will actually be paid.
        # e.g. if the 2nd highest bid was 5, only pay 6
        money_max = sum(winning_bids.values())
        overpaid = max(0, money_max-second_bid-1)
        money_actual = money_max - overpaid
        # allot the actual price between the bidders
        # Step 1: calculate the paid price based on the percentage of the full price, ceiled!
        money_owed = OrderedDict()
        for user, amount in sorted(winning_bids.items(), key=itemgetter(1), reverse=True):
            percentage = amount / money_max
            money_owed[user] = ceil(money_actual * percentage)
        # Note the above iteration order: highest bidders first, then ordered of winning_bids,
        # which is a OrderedDict too, and therefore insertion order.
        # This ensures earlier bids are visited first, and favored for following price discounts:
        # Step 2: because of ceiling the prices, the sum might be too high.
        # => calculate how much was overpaid, and discount the higher, and if tied the earlier bidders
        overpaid = sum(money_owed.values()) - money_actual
        user_iter = iter(money_owed)
        for _ in range(overpaid):
            money_owed[next(user_iter)] -= 1
        # return all results as dict
        return {
            "item": winning_item,
            "money_max": money_max,
            "money_actual": money_actual,
            "money_owed": money_owed,
        }
