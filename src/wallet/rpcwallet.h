// Copyright (c) 2016 The Bitcoin Core developers
// Copyright (c) 2018-2023 The Zcash developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://www.opensource.org/licenses/mit-license.php .

#ifndef BITCOIN_WALLET_RPCWALLET_H
#define BITCOIN_WALLET_RPCWALLET_H

#include "policy/fees.h"  // for DEFAULT_FEE

class CRPCTable;

void RegisterWalletRPCCommands(CRPCTable &tableRPC);

#endif //BITCOIN_WALLET_RPCWALLET_H
