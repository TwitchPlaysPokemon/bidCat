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
from collections import OrderedDict
from math import ceil
from operator import itemgetter


class BiddingError(Exception):
    """Base Exception for all bidding errors."""
    pass

class InsufficientMoneyError(BiddingError):
    """Is raised when a bid fails due to not enough available money."""
    pass

class AlreadyBidError(BiddingError):
    """Is raised when a bid fails due to a previous bid on that item
    already existing."""
    pass

class NoExistingBidError(BiddingError):
    """Is raised when replacing or increasing a bid failed because there
    was no previous bid."""
    pass


class VisiblyLoweredError(BiddingError):
    """Is raised when replacing a bid would cause the bid to be visibly
    lowered."""
    pass


class Auction:
    """Handles multiple users bidding on multiple items, only one item can win.
    All provided items and users must be hashable."""
    def __init__(self, bank):
        """Arguments:
            bank: the bank object the auction checks and reserves users' money in."""
        self.bank = bank
        self.bank.reserved_money_checker_functions.add(self.get_reserved_money)
        # item -> user -> amount
        self._itembids = {}
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

    def _handle_bid(self, user, item, amount, replace=False, allow_visible_lowering=True):
        """For that user, bids the given amount on the given item.
        If add is True, adds the amount onto the bet instead of replacing."""
        if amount < 1:
            raise ValueError("amount must be a number above 0.")
        previous_bid = None
        if item in self._itembids:
            previous_bid = self._itembids[item].get(user)
        already_bid = previous_bid is not None
        if not replace and already_bid:
            raise AlreadyBidError("There already is a bid from that user on that item.")
        elif replace and not already_bid:
            raise NoExistingBidError("There is no bid from that user on that item which could be replaced.")
        if replace and previous_bid == amount:
            # no change
            return
        needed_money = amount
        if replace:
            needed_money -= previous_bid
        available_money = self.bank.get_available_money(user)
        if needed_money > available_money:
            raise InsufficientMoneyError("Can't affort to bid {}, only {} available."
                                         .format(needed_money, available_money))
        if replace and amount < previous_bid and not allow_visible_lowering:
            # check if replacement lowers the visible bid
            winner = self.get_winner()
            if winner["item"] != item:
                # not first place, therefore lowering is never possible
                raise VisiblyLoweredError
            headroom = winner["total_bid"] - winner["total_charge"]
            decrease = previous_bid - amount
            if decrease > headroom:
                raise VisiblyLoweredError
        self._update_last_change(item)
        if item not in self._itembids:
            self._itembids[item] = OrderedDict()
        self._itembids[item][user] = amount
        self._itembids[item].move_to_end(user)

    def place_bid(self, user, item, amount):
        """For that user, bids the given amount on the given item.
        Throws AlreadyBidError if there already is a bid from that user on that item.
        """
        self._handle_bid(user, item, amount, replace=False)

    def replace_bid(self, user, item, amount, allow_visible_lowering=True):
        """For that user, bids the given amount on the given item, replacing an old bid.
        Throws NoExistingBidError if there was no bid from that user on that item to replace.
        """
        self._handle_bid(user, item, amount, replace=True, allow_visible_lowering=allow_visible_lowering)

    def increase_bid(self, user, item, amount):
        """Does the same as replace_bid, but instead adds the new amount onto the old one.
        """
        # Checking for existence is done by replace_bid()
        previous_bid = self._itembids.get(item, {}).get(user, 0)
        self.replace_bid(user, item, amount+previous_bid)

    def remove_bid(self, user, item):
        """For that user, removes his bid on that item.
        Returns True if a bid was removed, or False if there was no bid."""
        if item not in self._itembids or user not in self._itembids[item]:
            return False
        del self._itembids[item][user]
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

    def get_all_bids_ordered(self):
        """Returns all bids as [tuple(item, dict(user:amount))...], ordered by
        ranking (first=winner)"""
        # get items sorted by total money first, and then by least recently updated
        # (~= first bid wins if tied)
        def by_amount_and_last_update(dictitem):
            item, bids = dictitem
            # smaller = first, therefore sum is negated.
            # but index of recent updates is not, because smaller = ealier, as desired
            return -sum(bids.values()), self._changes_tracker.index(item)
        return sorted(self._itembids.items(), key=by_amount_and_last_update)

    def get_winner(self, discount_latter=False):
        """Calculated the item currently winning.
        Returns None if no bids, or a dict structured like this:
        {
            "item": identifier of the item that won
            "total_bid": total max sum of money from bids on this item.
            "total_charge": actual sum of money that would currently be paid.
                This can be less than total_bid if there is a gap to the 2nd highest bid.
            "money_owed": dict(user:money) containing the amount of money to pay
                allotted between all bidders. It's sum is total_charge
        }"""
        bids = self.get_all_bids_ordered()
        if not bids:
            # no bids
            return None
        # extract the winner, save the rest
        (winning_item, winning_bids), *rest = bids
        # determine the second highest bet amount
        second_bid = 0
        if rest:
            _, second_item_bids = rest[0]
            second_bid = sum(second_item_bids.values())
        # determine what will actually be paid.
        # e.g. if the 2nd highest bid was 5, only pay 6
        total_bid = sum(winning_bids.values())
        overpaid = max(0, total_bid-second_bid-1)
        total_charge = total_bid - overpaid
        # allot the actual price between the bidders
        # Step 1: calculate the paid price based on the percentage of the full price, ceiled!
        money_owed = OrderedDict()
        for user, amount in sorted(winning_bids.items(), key=itemgetter(1), reverse=True):
            percentage = amount / total_bid
            money_owed[user] = ceil(total_charge * percentage)
        # Note the above iteration order: highest bidders first, then ordered of winning_bids,
        # which is a OrderedDict too, and therefore insertion order.
        # This ensures earlier bids are visited first, and favored for following price discounts:
        # Step 2: because of ceiling the prices, the sum might be too high.
        # => calculate how much was overpaid, and discount the higher, and if tied the earlier bidders
        overpaid = sum(money_owed.values()) - total_charge
        # if discount_latter is True, actually discounts the later bidders, the oppisite as described above
        if discount_latter:
            user_iter = iter(reversed(money_owed))
        else:
            user_iter = iter(money_owed)
        for _ in range(overpaid):
            money_owed[next(user_iter)] -= 1
        # return all results as dict
        return {
            "item": winning_item,
            "total_bid": total_bid,
            "total_charge": total_charge,
            "money_owed": money_owed,
        }
