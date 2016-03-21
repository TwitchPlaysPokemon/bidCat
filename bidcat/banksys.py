import logging
from datetime import datetime
from collections import namedtuple, defaultdict


class InsufficientMoneyError(Exception): pass
class AccountNotFound(Exception): pass


class BaseBank(object):
    def __init__(self):
        self.log = logging.getLogger("bank")
        # a list of functions that take a user and return reserved money
        self.reserved_money_checker_functions = set()

    def get_reserved_money(self, user):
        """Determine the total amount of reserved money.

        Reserved money is money that is reserved "in-memory" and not
        represented in storage.

        Calls all functions registered as reserved money checkers and returns
        the total.

        Arguments:
            user:
                id of the user to determine the amount of reserved money for.

            Returns:
                positive integer of reserved money, will be 0 if no money reserved.
        """
        reserved_money = 0
        for reserved_money_checking_function in self.reserved_money_checker_functions:
            reserved_money += reserved_money_checking_function(user)
        return reserved_money

    def get_total_money(self, user):
        """Get the amount of all a user's money, including reserved.

        Arguments:
            user:
                id of the user to get the total money for.

        Returns:
            total amount of money the specified user has.
        """
        return self._get_stored_money_value(user)

    def get_available_money(self, user):
        """Get the amount of money available to a user.

        Available money is the amount of money that the user has minus money
        that is reserved. Just the money that is available for use right now.

        This is likely the method you were looking for.

        If a user is increasing an amount of money put on something you'll need to
        check how much is already reserved and use that to determine what the user
        actually has access to.

        Arguments:
            user:
                id of the user to get the available money for.

            Returns:
                the amount of money the user has available, will be 0 in the case of no money.
        """
        return self.get_total_money(user) - self.get_reserved_money(user)

    def _get_stored_money_value(self, user):
        raise NotImplementedError("storage not implemented")

    def _adjust_stored_money_value(self, user, change):
        raise NotImplementedError("storage not implemented")

    def _record_transaction(self, user, change):
        raise NotImplementedError("storage not implemented")

    def make_transaction(self, user, change, extra):
        """Adjust a user's balance and make a record of it.

        Arguments:
            user:
                id of the user whose account is being affected.
            change:
                 the amount to adjust the balance by.
        """
        self.log.info("adjusting %s's balance by %+d", user, change)
        old_balance = self._get_stored_money_value(user)
        self._adjust_stored_money_value(user, change)
        new_balance = self._get_stored_money_value(user)
        transaction = dict(
            user=user,
            change=change,
            timestamp=datetime.utcnow(),
            old_balance=old_balance,
            new_balance=new_balance,
            **extra)
        self.log.debug("recording transaction: %r", transaction)
        self._record_transaction(transaction)
        return transaction


class DummyBank(BaseBank):
    """In-memory bank with no persistence, great for debugging."""
    def __init__(self):
        super(DummyBank, self).__init__()
        self._storage = {}
        self._starting_amount = 50000

    def _get_stored_money_value(self, user):
        if user not in self._storage:
            self._storage[user] = self._starting_amount
        return self._storage[user]

    def _adjust_stored_money_value(self, user, change):
        if user not in self._storage:
            self._storage[user] = self._starting_amount
        self._storage[user] += change
        self.log.debug("dummy storage: %r", self._storage)

    def debug(self):
        for user in self._storage.keys():
            print("%10s %d" % (user, self.get_available_money(user)))


class MongoBank(BaseBank):
    def __init__(self, db, users_collection_name="users", transactions_collection_name="transactions", field_name="money"):
        super(MongoBank, self).__init__()
        self.db = db
        self.users_collection_name = users_collection_name
        self.transactions_collection_name = transactions_collection_name
        self.users_collection = self.db[self.users_collection_name]
        self.transactions_collection = self.db[self.transactions_collection_name]
        self.field_name = field_name

    def _get_stored_money_value(self, user):
        doc = self.users_collection.find_one({"_id": user})
        if not doc:
            raise AccountNotFound("no account for: %s", user)
        return doc[self.field_name]

    def _adjust_stored_money_value(self, user, change):
        self.users_collection.update({"_id": user}, {"$inc": {self.field_name: change}})

    def _record_transaction(self, transaction):
        self.transactions_collection.insert(transaction)


def main():
    bank = DummyBank()
    print(bank.get_available_money("bob"))


if __name__ == "__main__":
    main()
