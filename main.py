import pandas as pd
import requests
from dotenv import load_dotenv
import os
import json
import npyscreen
import sys
from web3 import Web3
from solana.rpc.api import Client
from cosmpy.aerial.client import LedgerClient, NetworkConfig
from blockscan import Blockscan

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
                "balance_eth_USD": [0]
            }).astype(self.df.dtypes)
            self.df = pd.concat([self.df, new_wallet])
            self.df.to_csv('addies.csv', index=False)
        else:
            print(f"Wallet {address} already exists.")

    def delete_wallet(self, address):
        if not self.df[self.df["address"] == address].empty:
            self.df = self.df[self.df["address"] != address]
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

    def update_ethereum_balances_etherscan(self):
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

    def update_ethereum_balances_alchemy(self):
        load_dotenv()
        alchemy_api_key = os.getenv('ALCHEMY_API_KEY')
        alchemy_url = "https://eth-mainnet.g.alchemy.com/v2/{}".format(alchemy_api_key)
        #w3 = Web3(Web3.HTTPProvider(alchemy_url))
        #print(w3.is_connected())
                    
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

    def show_wallets(self):
        print(self.df.drop(['generation', 'balance_eth_WEI'], axis=1))

    def reload_dataframe(self):
        self.df = pd.read_csv(self.filename)

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
        self.parentApp.switchFormPrevious()

class EditWalletForm(npyscreen.ActionForm):
    def create(self):
        self.wallets = self.add(npyscreen.TitleMultiSelect, max_height=5, value=[], values=self.parentApp.pm.df['nickname'].tolist(), name="Select Wallet:")
        self.add(npyscreen.ButtonPress, name="Confirm Deletion", when_pressed_function=self.when_pressed_confirm_deletion)

    def beforeEditing(self):
        self.wallets.update(self.parentApp.pm.df['nickname'].tolist())

    def when_pressed_confirm_deletion(self):
        selected_wallets = self.wallets.value
        if selected_wallets:
            for wallet in selected_wallets:
                self.parentApp.pm.df = self.parentApp.pm.df[self.parentApp.pm.df['nickname'] != wallet]
            self.parentApp.pm.save_to_file()
        self.parentApp.switchFormPrevious()

class DeleteWalletForm(npyscreen.ActionForm):
    def create(self):
        self.wallets = self.add(npyscreen.TitleMultiSelect, max_height=35, value=[], values=self.parentApp.pm.df['nickname'].tolist(), name="Select Wallet:")
        self.add(npyscreen.ButtonPress, name="Confirm Deletion", when_pressed_function=self.when_pressed_confirm_deletion)

    def beforeEditing(self):
        self.wallets.update(self.parentApp.pm.df['nickname'].tolist())

    def when_pressed_confirm_deletion(self):
        selected_wallets = self.wallets.value
        if selected_wallets:
            try:
                for wallet in selected_wallets:
                    df_filtered = self.parentApp.pm.df.loc[self.parentApp.pm.df['nickname'].str.strip().str.lower() == str(wallet).lower(), 'address']
                    if not df_filtered.empty:
                        address = df_filtered.values[0]
                        new_df = self.parentApp.pm.df[self.parentApp.pm.df['address'] != address]
                        pm.df = new_df
                        self.parentApp.pm.df.update(new_df)
                self.parentApp.pm.save_to_file()
            except Exception as e:
                print("An error occurred: ", str(e))
            self.parentApp.switchForm('MAIN')

class MainForm(npyscreen.ActionForm):
    def create(self):
        self.pm = self.parentApp.pm
        self.add(npyscreen.ButtonPress, name="Add Wallet", when_pressed_function=self.when_pressed_add_wallet)
        #self.add(npyscreen.ButtonPress, name="Edit Wallet", when_pressed_function=self.when_pressed_edit_wallet)
        self.add(npyscreen.ButtonPress, name="Delete Wallet", when_pressed_function=self.when_pressed_delete_wallet)
        self.add(npyscreen.ButtonPress, name="Exit", when_pressed_function=self.when_pressed_exit)

    def when_pressed_add_wallet(self):
        self.parentApp.switchForm('ADD_WALLET')

    def when_pressed_edit_wallet(self):
        self.parentApp.switchForm('EDIT_WALLET')

    def when_pressed_delete_wallet(self):
        self.parentApp.switchForm('DELETE_WALLET')

    def when_pressed_exit(self):
        self.parentApp.setNextForm(None)

class TestApp(npyscreen.NPSAppManaged):
    def onStart(self):
        self.pm = PortfolioManager('addies.csv')
        self.addForm('MAIN', MainForm, name="Portfolio Manager", pm=self.pm)
        self.addForm('ADD_WALLET', AddWalletForm, name="Add Wallet")
        self.addForm('EDIT_WALLET', EditWalletForm, name="Edit Wallet")
        self.addForm('DELETE_WALLET', DeleteWalletForm, name="Delete Wallet")

if __name__ == "__main__":
    TestApp().run()
    #pm.update_ethereum_balances_alchemy()
    #pm.show_wallets()
    #pm.save_to_file("addies.csv")