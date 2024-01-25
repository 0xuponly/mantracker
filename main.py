import pandas as pd
import requests
from dotenv import load_dotenv
import os
import json
import npyscreen
import sys
import csv
from web3 import Web3
from solana.rpc.api import Client
from cosmpy.aerial.client import LedgerClient, NetworkConfig
from oneinch_py import OneInchSwap, TransactionHelper, OneInchOracle

class PortfolioManager:
    def __init__(self, filename='addies.csv'):
        self.filename = filename
        if filename:
            try:
                self.df = pd.read_csv(filename)
            except FileNotFoundError:
                print(f"File {filename} not found. Initializing empty DataFrame.")
                self.df = pd.DataFrame({
                    "address": [],
                    "blockchain": [],
                    "balance_usd": []
                })
        else:
            self.df = pd.DataFrame({
                "address": [],
                "blockchain": [],
                "balance_usd": []
            })
            
    def add_wallet(self, address, blockchain, id, nickname, generation, status="ACTIVE"):
        if not any(self.df["address"] == address):
            new_wallet = pd.DataFrame({
                "address": [address],
                "blockchain": [blockchain],
                "id": [id],
                "nickname": [nickname],
                "status": [status],
                "generation": [generation],
                "balance_eth_WEI": [0],
                "balance_eth_ETH": [0],
                "balance_eth_USD": [0],
                "balance_alt_ETH": [0],
                "balance_alt_USD": [0],
                "balance_total_ETH": [0], 
                "balance_total_USD": [0],               
            }).astype(self.df.dtypes)
            self.df = pd.concat([self.df, new_wallet])
            self.df.to_csv('addies.csv', index=False)
        else:
            print(f"Wallet {address} already exists.")

    def delete_wallet(self, address):
        if not self.df[self.df["address"] == address].empty:
            self.df = self.df[self.df["address"] != address].copy()
        else:
            print(f"Wallet {address} does not exist.")

    def edit_wallet(self, address, new_balance):
        mask = self.df["address"] == address
        self.df = self.df.with_column(pd.col("balance").apply(lambda x: new_balance if mask.loc[x.name] else x))

    def get_wallets(self):
        return self.df

    def save_to_file(self, filename=None):
        if filename is None:
            filename = self.filename
        self.df.to_csv(filename, index=False)

    def determine_blockchain(self, address):
      # Define URLs for the blockchain APIs
      apis = {
         'bitcoin': f'https://blockchain.info/rawaddr/{address}',
         'ethereum': f'https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey=YourApiKeyToken',
         'solana': f'https://api.mainnet-beta.solana.com/api/v1/address/{address}/balance',
      }

      # Check each blockchain API
      for blockchain, api_url in apis.items():
         try:
            response = requests.get(api_url)
           
            # If the response status code is 200, the address exists on this blockchain
            if response.status_code == 200:
               mask = self.df["address"] == address
               self.df = self.df.with_columns(
                 pd.when(mask).then(blockchain).otherwise(pd.col("blockchain")).alias("blockchain")
               )
               return blockchain
         except Exception as e:
            print(f"Error querying {blockchain}: {str(e)}")

      # If no match is found, return None
      return None

    def update_balances_ethereum_eth_etherscan(self):
        load_dotenv()
        etherscan_api_key = os.getenv('ETHERSCAN_API_KEY')
        url = "https://api.etherscan.io/api"
        
        # Filter rows where blockchain is 'ethereum'
        df_ethereum = self.df[self.df["blockchain"] == "ethereum"]
        
        # Get addresses from the filtered dataframe
        addresses = ','.join(df_ethereum['address'].to_list())
        
        params = {
            'module': 'account',
            'action': 'balancemulti',
            'address': addresses,
            'tag': 'latest',
            'apikey': etherscan_api_key
        }
        
        response_etherscan = requests.get(url, params=params)
        data = response_etherscan.json()['result']
        df = pd.DataFrame(data)
        df['balance_eth_ETH'] = df['balance'].astype(float) / 1e18
        response = requests.get('https://min-api.cryptocompare.com/data/price?fsym=ETH&tsyms=USD')
        eth_price_usd = response.json()['USD']
        df['balance_eth_USD'] = df['balance_eth_ETH'] * eth_price_usd
        df = df.rename(columns={'balance': 'balance_eth_WEI'})
        df = df.rename(columns={'account': 'address'})
        if 'balance_eth_WEI' in self.df.columns:
            self.df['balance_eth_WEI'] = df['balance_eth_WEI']
        else:
            self.df = pd.merge(self.df, df[['address', 'balance_eth_WEI']], on='address', how='left')
        if 'balance_eth_ETH' in self.df.columns:
            self.df['balance_eth_ETH'] = df['balance_eth_ETH']
        else:
            self.df = pd.merge(self.df, df[['address', 'balance_eth_ETH']], on='address', how='left')
        if 'balance_eth_USD' in self.df.columns:
            self.df['balance_eth_USD'] = df['balance_eth_USD']
        else:
            self.df = pd.merge(self.df, df[['address', 'balance_eth_USD']], on='address', how='left')

    def update_balances_ethereum_eth_alchemy(self):
        load_dotenv()
        alchemy_api_key = os.getenv('ALCHEMY_API_KEY')
        alchemy_url = "https://eth-mainnet.g.alchemy.com/v2/{}".format(alchemy_api_key)
                    
        # Filter rows where blockchain is 'ethereum'
        df_ethereum = self.df[self.df["blockchain"] == "ethereum"]
        
        # Get addresses from the filtered dataframe
        addresses = df_ethereum['address'].tolist()
        #print(addresses)
        df = pd.DataFrame()
        for address in addresses:
            payload = {
                "id": 1,
                "jsonrpc": "2.0",
                "params": [address, "latest"],
                "method": "eth_getBalance"
            }
            headers = {
                "accept": "application/json",
                "content-type": "application/json"
            }

            response = requests.post(alchemy_url, json=payload, headers=headers)

            data = json.loads(response.text)
            balance = int(data['result'],16)
            df = pd.concat([df, pd.DataFrame([{'Address': address, 'Balance': balance}])], ignore_index=True)
        df['balance_eth_ETH'] = df['Balance'].astype(float) / 1e18
        response = requests.get('https://min-api.cryptocompare.com/data/price?fsym=ETH&tsyms=USD')
        eth_price_usd = response.json()['USD']
        df['balance_eth_USD'] = df['balance_eth_ETH'] * eth_price_usd
        df = df.rename(columns={'Balance': 'balance_eth_WEI'})
        df = df.rename(columns={'Address': 'address'})
        if 'balance_eth_WEI' in self.df.columns:
            self.df['balance_eth_WEI'] = df['balance_eth_WEI']
        else:
            self.df = pd.merge(self.df, df[['address', 'balance_eth_WEI']], on='address', how='left')
        if 'balance_eth_ETH' in self.df.columns:
            self.df['balance_eth_ETH'] = df['balance_eth_ETH']
        else:
            self.df = pd.merge(self.df, df[['address', 'balance_eth_ETH']], on='address', how='left')
        if 'balance_eth_USD' in self.df.columns:
            self.df['balance_eth_USD'] = df['balance_eth_USD']
        else:
            self.df = pd.merge(self.df, df[['address', 'balance_eth_USD']], on='address', how='left')

    def update_balances_ethereum_erc20_alchemy(self):
        load_dotenv()
        alchemy_api_key = os.getenv('ALCHEMY_API_KEY')
        alchemy_url = "https://eth-mainnet.g.alchemy.com/v2/{}".format(alchemy_api_key)

        # Filter rows where blockchain is 'ethereum'
        df_ethereum = self.df[self.df["blockchain"] == "ethereum"]
        
        # Get addresses from the filtered dataframe
        addresses = df_ethereum['address'].tolist()
        #print(addresses)
        with open('erc20_ignore_list.csv', 'r') as f:
            reader = csv.reader(f)
            erc20_ignore_list = [item[0] for item in reader]
        df = pd.DataFrame()
        for address in addresses:
            payload = {
                "id": 1,
                "jsonrpc": "2.0",
                "params": [address, "erc20"],
                "method": "alchemy_getTokenBalances"
            }
            headers = {
                "accept": "application/json",
                "content-type": "application/json"
            }

            response = requests.post(alchemy_url, json=payload, headers=headers)

            data = json.loads(response.text)
            for item in data:
                # If 'data' is a list of dictionaries
                if isinstance(data, list):
                    for item in data:
                        if 'result' in item and 'tokenBalances' in item['result']:
                            item['result']['tokenBalances'] = [pair for pair in item['result']['tokenBalances'] if int(pair['tokenBalance'], 16) != 0]

                # If 'data' is a single dictionary
                elif isinstance(data, dict):
                    if 'result' in data and 'tokenBalances' in data['result']:
                        data['result']['tokenBalances'] = [pair for pair in data['result']['tokenBalances'] if int(pair['tokenBalance'], 16) != 0]
            balance_alt_ETH = 0
            for i in data['result']['tokenBalances']:
                rpc_url = "https://eth.llamarpc.com"
                oracle = OneInchOracle(rpc_url, chain='ethereum')
                contract_address = i['contractAddress']
                token_balance = int(i['tokenBalance'],16)/(1e18)
                token_price_in_ETH = 0 if i['contractAddress'] in erc20_ignore_list else oracle.get_rate_to_ETH(src_token=i['contractAddress'], src_token_decimal=18)
                value_in_ETH = token_balance * token_price_in_ETH
                balance_alt_ETH += value_in_ETH
            df = pd.concat([df, pd.DataFrame([{'address': address, 'balance_alt_ETH': balance_alt_ETH}])], ignore_index=True)
        df = df[df['balance_alt_ETH'] != 0]
        response = requests.get('https://min-api.cryptocompare.com/data/price?fsym=ETH&tsyms=USD')
        eth_price_usd = response.json()['USD']
        df['balance_alt_USD'] = df['balance_alt_ETH'] * eth_price_usd
        if 'balance_alt_ETH' in self.df.columns:
            self.df['balance_alt_ETH'] = df['balance_alt_ETH']
        else:
            self.df = pd.merge(self.df, df[['address', 'balance_alt_ETH']], on='address', how='left')
        if 'balance_alt_USD' in self.df.columns:
            self.df['balance_alt_USD'] = df['balance_alt_USD']
        else:
            self.df = pd.merge(self.df, df[['address', 'balance_alt_USD']], on='address', how='left')

    def show_wallets(self):
        print(self.df.drop(['generation', 'balance_eth_WEI'], axis=1))

    def reload_dataframe(self):
        self.df = pd.read_csv(self.filename)

    def clean_dataframe(self):
        self.df.fillna(0, inplace=True)
        pd.options.display.float_format = '{:.3f}'.format
        if 'balance_total_ETH' in self.df.columns:
            # Recalculate and update the sum
            self.df['balance_total_ETH'] = self.df['balance_eth_ETH'] + self.df['balance_alt_ETH']
        else:
            # Create the column and calculate the sum
            self.df['balance_total_ETH'] = self.df['balance_eth_ETH'] + self.df['balance_alt_ETH']
        if 'balance_total_USD' in self.df.columns:
            # Recalculate and update the sum
            self.df['balance_total_USD'] = self.df['balance_eth_USD'] + self.df['balance_alt_USD']
        else:
            # Create the column and calculate the sum
            self.df['balance_total_USD'] = self.df['balance_eth_USD'] + self.df['balance_alt_USD']
        self.save_to_file(self.filename)

class ViewPortfolioForm(npyscreen.ActionForm):
    def create(self):
        # Split the DataFrame into separate lines
        df_no_index = self.parentApp.pm.df.reset_index(drop=True)
        df_no_index = df_no_index.fillna("")
        df_lines = df_no_index.to_string(index=False).split('\n')
        # Create a mask for rows where status is not "INACTIVE"
        mask = df_no_index['status'] != 'INACTIVE'
        # Apply the mask to the DataFrame
        df_active = df_no_index[mask]
        # Drop the 'status' column
        df_active = df_active.drop('status', axis=1)
        df_active = df_active.drop('generation', axis=1)
        df_active = df_active.drop('balance_eth_WEI', axis=1)
        df_active = df_active.drop('balance_eth_USD', axis=1)
        df_active = df_active.drop('balance_alt_USD', axis=1)
        # Truncate the 'address' column
        df_active['address'] = df_active['address'].apply(lambda x: str(x)[:6] + '....' + str(x)[-6:] if len(str(x)) > 16 else str(x))
        # Convert the filtered DataFrame to string and split into lines
        df_active_lines = df_active.to_string(index=False).split('\n')
        # Create a TitleText widget for each line
        for i, line in enumerate(df_active_lines):
            self.add(npyscreen.TitleText, name=f"{i}", value=line)
    
    def afterEditing(self):
        self.parentApp.switchFormPrevious()

    def on_press_cancel(self):
        self.parentApp.switchForm('MAIN')

class AddWalletForm(npyscreen.ActionForm):
    def create(self):
        self.address = self.add(npyscreen.TitleText, name="Address:")
        self.blockchain = self.add(npyscreen.TitleText, name="Blockchain:")
        self.id = self.add(npyscreen.TitleText, name="ID:")
        self.nickname = self.add(npyscreen.TitleText, name="Nickname:")
        self.generation = self.add(npyscreen.TitleText, name="Generation:")

    def afterEditing(self):
        address = self.address.value
        blockchain = self.blockchain.value
        id = self.id.value
        nickname = self.nickname.value
        generation = self.generation.value
        self.parentApp.getForm('MAIN').pm.add_wallet(address, blockchain, id, nickname, generation)
        self.parentApp.getForm('MAIN').pm.reload_dataframe()
        #self.parentApp.getForm('VIEW_PORTFOLIO').create()
        self.parentApp.getForm('EDIT_WALLET').beforeEditing()
        self.parentApp.getForm('DELETE_WALLET').beforeEditing()
        self.parentApp.switchFormPrevious()

    def on_press_cancel(self):
        self.parentApp.switchForm('MAIN')

class EditWalletForm(npyscreen.ActionForm):
    def create(self):
        self.wallets = self.add(npyscreen.TitleMultiSelect, max_height=35, value=[], values=self.parentApp.pm.df['nickname'].tolist(), name="Select Wallet:")
        self.add(npyscreen.ButtonPress, name="Confirm Edit", when_pressed_function=self.when_pressed_confirm_edit)

    def beforeEditing(self):
        self.wallets.update(self.parentApp.pm.df['nickname'].tolist())

    def afterEditing(self):
        self.parentApp.getForm('MAIN').pm.reload_dataframe()
        self.parentApp.getForm('EDIT_WALLET').beforeEditing()
        self.parentApp.getForm('DELETE_WALLET').beforeEditing()
        self.parentApp.switchFormPrevious()

    def when_pressed_confirm_edit(self):
        selected_wallets = self.wallets.value
        if selected_wallets:
            for wallet in selected_wallets:
                self.parentApp.pm.df = self.parentApp.pm.df[self.parentApp.pm.df['nickname'] != wallet]
            self.parentApp.pm.save_to_file()
        self.parentApp.switchFormPrevious()

    def on_press_cancel(self):
        self.parentApp.switchForm('MAIN')

class DeleteWalletForm(npyscreen.ActionForm):
    def create(self):
        self.wallets = self.add(npyscreen.TitleMultiSelect, max_height=35, value=[], values=self.parentApp.pm.df['nickname'].tolist(), name="Select Wallet:")
        self.add(npyscreen.ButtonPress, name="Confirm Deletion", when_pressed_function=self.when_pressed_confirm_deletion)

    def beforeEditing(self):
        self.wallets.update(self.parentApp.pm.df['nickname'].tolist())

    def afterEditing(self):
        self.parentApp.getForm('MAIN').pm.reload_dataframe()
        self.parentApp.getForm('EDIT_WALLET').beforeEditing()
        self.parentApp.getForm('DELETE_WALLET').beforeEditing()
        self.parentApp.switchFormPrevious()

    def when_pressed_confirm_deletion(self):
        selected_wallets = self.wallets.value
        if selected_wallets:
            wallet_names = [self.wallets.values[i] for i in selected_wallets]
            confirmation = npyscreen.notify_yes_no(f"You're about to permanently delete {', '.join(wallet_names)}. Are you sure you want to delete them?")
            if confirmation:
                try:
                    for wallet in wallet_names:
                        matching_wallets = self.parentApp.pm.df[self.parentApp.pm.df['nickname'] == wallet]
                        if not matching_wallets.empty:
                            address = matching_wallets['address'].values[0]
                            self.parentApp.pm.delete_wallet(address)
                        else:
                            print(f"No wallet found with nickname {wallet}")
                    self.parentApp.pm.save_to_file()
                except Exception as e:
                    print("An error occurred: ", str(e))
                self.parentApp.switchForm('MAIN')

    def on_press_cancel(self):
        self.parentApp.switchForm('MAIN')

class MainForm(npyscreen.ActionForm):
    def create(self):
        self.pm = self.parentApp.pm
        self.add(npyscreen.ButtonPress, name="Portfolio", when_pressed_function=self.when_pressed_view_portfolio)
        self.add(npyscreen.ButtonPress, name="Add Wallet", when_pressed_function=self.when_pressed_add_wallet)
        self.add(npyscreen.ButtonPress, name="Edit Wallet", when_pressed_function=self.when_pressed_edit_wallet)
        self.add(npyscreen.ButtonPress, name="Delete Wallet", when_pressed_function=self.when_pressed_delete_wallet)
        self.add(npyscreen.ButtonPress, name="Exit", when_pressed_function=self.when_pressed_exit)

    def beforeEditing(self):
        self.parentApp.pm.reload_dataframe()

    def when_pressed_view_portfolio(self):
        self.parentApp.switchForm('VIEW_PORTFOLIO')

    def when_pressed_add_wallet(self):
        self.parentApp.switchForm('ADD_WALLET')

    def when_pressed_edit_wallet(self):
        self.parentApp.switchForm('EDIT_WALLET')

    def when_pressed_delete_wallet(self):
        self.parentApp.switchForm('DELETE_WALLET')

    def when_pressed_exit(self):
        self.parentApp.setNextForm(None)

    def on_press_cancel(self):
        self.parentApp.switchForm('MAIN')

class TestApp(npyscreen.NPSAppManaged):
    def onStart(self):
        self.pm = PortfolioManager('addies.csv')
        self.addForm('MAIN', MainForm, name="Mantracker", pm=self.pm)
        self.pm.update_balances_ethereum_eth_alchemy()
        self.pm.update_balances_ethereum_erc20_alchemy()
        self.pm.clean_dataframe()
        self.addForm('VIEW_PORTFOLIO', ViewPortfolioForm, name="Portfolio")
        self.addForm('ADD_WALLET', AddWalletForm, name="Add Wallet")
        self.addForm('EDIT_WALLET', EditWalletForm, name="Edit Wallet")
        self.addForm('DELETE_WALLET', DeleteWalletForm, name="Delete Wallet")

if __name__ == "__main__":
    TestApp().run()
    #pm = PortfolioManager('addies.csv')
    #pm.update_balances_ethereum_erc20_alchemy()
    #pm.clean_dataframe()