#!/usr/bin/env python3
# Copyright (c) 2019 The Zcash developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or https://www.opensource.org/licenses/mit-license.php .

from decimal import Decimal
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import assert_equal, assert_true, \
    start_nodes, \
    wait_and_assert_operationid_status_result, DEFAULT_FEE

SAPLING_ADDR = 'zregtestsapling1ssqj3f3majnl270985gqcdqedd9t4nlttjqskccwevj2v20sc25deqspv3masufnwcdy67cydyy'
SAPLING_KEY = 'secret-extended-key-regtest1qv62zt2fqyqqpqrh2qzc08h7gncf4447jh9kvnnnhjg959fkwt7mhw9j8e9at7attx8z6u3953u86vcnsujdc2ckdlcmztjt44x3uxpah5mxtncxd0mqcnz9eq8rghh5m4j44ep5d9702sdvvwawqassulktfegrcp4twxgqdxx4eww3lau0mywuaeztpla2cmvagr5nj98elt45zh6fjznadl6wz52n2uyhdwcm2wlsu8fnxstrk6s4t55t8dy6jkgx5g0cwpchh5qffp8x5'

DISABLED_NO_FUNDS = 0
ENABLED_NO_FUNDS = 1
DISABLED_BEFORE_MIGRATION = 2
ENABLED_BEFORE_MIGRATION = 3
DURING_MIGRATION = 4
AFTER_MIGRATION = 5
ALL_MIGRATION_STATES = [DISABLED_NO_FUNDS, ENABLED_NO_FUNDS, DISABLED_BEFORE_MIGRATION, ENABLED_BEFORE_MIGRATION, DURING_MIGRATION, AFTER_MIGRATION]


def check_migration_status(node, destination_address, migration_state):
    status = node.z_getmigrationstatus()
    assert_equal(destination_address, status['destination_address'], "Migration destination address; status=%r" % status)
    assert_true(migration_state in ALL_MIGRATION_STATES, "Unexpected migration state %r" % migration_state)

    expected_enabled = migration_state not in [DISABLED_NO_FUNDS, DISABLED_BEFORE_MIGRATION]
    expected_sprout_funds = migration_state in [DISABLED_BEFORE_MIGRATION, ENABLED_BEFORE_MIGRATION]
    positive_unfinalized_amount = migration_state == DURING_MIGRATION
    positive_finalized_amount = migration_state == AFTER_MIGRATION
    num_migration_txids = 1 if migration_state in [DURING_MIGRATION, AFTER_MIGRATION] else 0
    num_finalized_migration_transactions = 1 if migration_state == AFTER_MIGRATION else 0

    assert_equal(expected_enabled, status['enabled'], "Expected enabled: %s" % expected_enabled)
    # During and after the migration there may be no remaining sprout funds if
    # we have randomly picked to migrate them all at once, so we only check
    # this field in the one case.
    if expected_sprout_funds:
        assert_true(Decimal(status['unmigrated_amount']) > Decimal('0.00'), "Expected sprout funds; status=%r" % (status,))
    # For the other two amount fields we know whether or not they will be positive
    unfinalized_msg = "Positive unfinalized amount: %s; status=%r " % (positive_unfinalized_amount, status)
    assert_equal(positive_unfinalized_amount, Decimal(status['unfinalized_migrated_amount']) > Decimal('0'), unfinalized_msg)
    finalized_msg = "Positive finalized amount: %s; status=%r " % (positive_finalized_amount, status)
    assert_equal(positive_finalized_amount, Decimal(status['finalized_migrated_amount']) > Decimal('0'), finalized_msg)
    assert_equal(num_finalized_migration_transactions, status['finalized_migration_transactions'], "Num finalized transactions; status=%r" % (status,))
    assert_equal(num_migration_txids, len(status['migration_txids']), "Num migration txids; status=%r" % (status,))


class SproutSaplingMigration(BitcoinTestFramework):
    def __init__(self):
        super().__init__()
        self.num_nodes = 4
        self.cache_behavior = 'sprout'

    def setup_nodes(self):
        extra_args = [[
            '-allowdeprecated=z_getnewaddress',
            '-allowdeprecated=z_getbalance',
        ]] * self.num_nodes
        # Add migration parameters to nodes[0]
        extra_args[0] = extra_args[0] + [
            '-migration',
            '-migrationdestaddress=' + SAPLING_ADDR,
            '-debug=zrpcunsafe'
        ]
        assert_equal(5, len(extra_args[0]))
        assert_equal(2, len(extra_args[1]))
        return start_nodes(self.num_nodes, self.options.tmpdir, extra_args)

    def run_migration_test(self, node, sproutAddr, saplingAddr, target_height, sprout_initial_balance):
        # Make sure we are in a good state to run the test
        assert_equal(200, node.getblockcount() % 500, "Should be at block 200 % 500")
        assert_equal(node.z_getbalance(sproutAddr), sprout_initial_balance)
        assert_equal(node.z_getbalance(saplingAddr), Decimal('0'))
        check_migration_status(node, saplingAddr, DISABLED_BEFORE_MIGRATION)

        # Migrate
        node.z_setmigration(True)
        print("Mining to block 494 % 500...")
        node.generate(294) # 200 % 500 -> 494 % 500
        self.sync_all()

        # At 494 % 500 we should have no async operations
        assert_equal(0, len(node.z_getoperationstatus()), "num async operations at 494 % 500")
        check_migration_status(node, saplingAddr, ENABLED_BEFORE_MIGRATION)

        node.generate(1)
        self.sync_all()

        # At 495 % 500 we should have an async operation
        operationstatus = node.z_getoperationstatus()
        print("migration operation: {}".format(operationstatus))
        assert_equal(1, len(operationstatus), "num async operations at 495 % 500")
        assert_equal('saplingmigration', operationstatus[0]['method'])
        assert_equal(target_height, operationstatus[0]['target_height'])

        result = wait_and_assert_operationid_status_result(node, operationstatus[0]['id'])
        print("result: {}".format(result))
        assert_equal('saplingmigration', result['method'])
        assert_equal(target_height, result['target_height'])
        assert_equal(1, result['result']['num_tx_created'])
        assert_equal(1, len(result['result']['migration_txids']))
        assert_true(Decimal(result['result']['amount_migrated']) > Decimal('0'))

        assert_equal(0, len(node.getrawmempool()), "mempool size at 495 % 500")

        node.generate(3)
        self.sync_all()

        # At 498 % 500 the mempool will be empty and no funds will have moved
        assert_equal(0, len(node.getrawmempool()), "mempool size at 498 % 500")
        assert_equal(node.z_getbalance(sproutAddr), sprout_initial_balance)
        assert_equal(node.z_getbalance(saplingAddr), Decimal('0'))

        node.generate(1)
        self.sync_all()

        # At 499 % 500 there will be a transaction in the mempool and the note will be locked
        mempool = node.getrawmempool()
        print("mempool: {}".format(mempool))
        assert_equal(1, len(mempool), "mempool size at 499 % 500")
        assert_equal(node.z_getbalance(sproutAddr), Decimal('0'))
        assert_equal(node.z_getbalance(saplingAddr), Decimal('0'))
        assert_true(node.z_getbalance(saplingAddr, 0) > Decimal('0'), "Unconfirmed sapling balance at 499 % 500")
        # Check that unmigrated amount + unfinalized = starting balance - fee
        status = node.z_getmigrationstatus()
        print("status: {}".format(status))
        assert_equal(sprout_initial_balance - DEFAULT_FEE, Decimal(status['unmigrated_amount']) + Decimal(status['unfinalized_migrated_amount']))

        # The transaction in the mempool should be the one listed in migration_txids,
        # and it should expire at the next 450 % 500.
        assert_equal(1, len(status['migration_txids']))
        txid = status['migration_txids'][0]
        assert_equal(txid, mempool[0])
        tx = node.getrawtransaction(txid, 1)
        assert_equal(target_height + 450, tx['expiryheight'])

        node.generate(1)
        self.sync_all()

        # At 0 % 500 funds will have moved
        sprout_balance = node.z_getbalance(sproutAddr)
        sapling_balance = node.z_getbalance(saplingAddr)
        print("sprout balance: {}, sapling balance: {}".format(sprout_balance, sapling_balance))
        assert_true(sprout_balance < sprout_initial_balance, "Should have less Sprout funds")
        assert_true(sapling_balance > Decimal('0'), "Should have more Sapling funds")
        assert_true(sprout_balance + sapling_balance, sprout_initial_balance - DEFAULT_FEE)

        check_migration_status(node, saplingAddr, DURING_MIGRATION)
        # At 10 % 500 the transactions will be considered 'finalized'
        node.generate(10)
        self.sync_all()
        check_migration_status(node, saplingAddr, AFTER_MIGRATION)
        # Check exact migration status amounts to make sure we account for fee
        status = node.z_getmigrationstatus()
        assert_equal(sprout_balance, Decimal(status['unmigrated_amount']))
        assert_equal(sapling_balance, Decimal(status['finalized_migrated_amount']))

    def run_test(self):
        # Check enabling via '-migration' and disabling via rpc
        check_migration_status(self.nodes[0], SAPLING_ADDR, ENABLED_BEFORE_MIGRATION)
        self.nodes[0].z_setmigration(False)
        check_migration_status(self.nodes[0], SAPLING_ADDR, DISABLED_BEFORE_MIGRATION)

        print("Running test using '-migrationdestaddress'...")

        # 1. Test using self.nodes[0] which has the parameter
        # Import a previously generated key to test '-migrationdestaddress'
        self.nodes[0].z_importkey(SAPLING_KEY)
        sproutAddr0 = self.nodes[0].listaddresses()[0]['sprout']['addresses'][0]

        self.run_migration_test(self.nodes[0], sproutAddr0, SAPLING_ADDR, 500, Decimal('50'))
        # Disable migration so only self.nodes[1] has a transaction in the mempool at block 999
        self.nodes[0].z_setmigration(False)

        # 2. Test using self.nodes[1] which will use the default Sapling address
        print("Running test using default Sapling address...")
        # Mine more blocks so we start at 200 % 500
        print("Mining blocks...")
        self.nodes[1].generate(190)  # 510 -> 700
        self.sync_all()

        sproutAddr1 = self.nodes[1].listaddresses()[0]['sprout']['addresses'][0]
        saplingAddr1 = self.nodes[1].z_getnewaddress('sapling')

        self.run_migration_test(self.nodes[1], sproutAddr1, saplingAddr1, 1000, Decimal('50'))


if __name__ == '__main__':
    SproutSaplingMigration().main()
