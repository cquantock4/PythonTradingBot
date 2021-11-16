# -*- coding: utf-8 -*-
"""
Created on Sun May 23 16:24:13 2021

@author: codyq
"""
import pytz
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from google.cloud import bigquery
import pyarrow
from google.cloud import storage
import alpaca_trade_api as tradeapi
import string
import time
# Import yfinance
import yfinance as yf
# yahoo financials
#from yahoofinancials import YahooFinancials
import sys
import logging


#logging.basicConfig(filename=r'C:\Users\codyq\PythonScripts\TradingBot_v1\testing.log', encoding='utf-8', level=logging.DEBUG)

#Paper Account Api Creds
key_id = ''
secret_key = '' 

# Initialize the alpaca api
# Prod Link "https://api.alpaca.markets"
# Dev Link "https://paper-api.alpaca.markets"
base_url = "https://paper-api.alpaca.markets"
            
api = tradeapi.REST(
    key_id,
    secret_key,
    base_url,
    'v2'
    )

# Get the current positions from alpaca and create a df
positions = api.list_positions()

symbol, qty, market_value = [], [], []

for each in positions:
    symbol.append(each.symbol)
    qty.append(int(each.qty))
    market_value.append(float(each.market_value))
    
df_pf = pd.DataFrame(
    {
        'symbol': symbol,
         'qty': qty,
        'market_value': market_value
    }
)

# Get our account information.
account = api.get_account()

# Current portfolio value
#portfolio_value = round(df_pf['market_value'].sum(), 2)

#Set Trading Amount above 95k
TradingAmt = float(account.cash) - 95000
print(TradingAmt)

#symbols = ['GUSH','MDH','CO','AVAL','RNGR','WDH','JT','FCA','TEO','HZN','USDP']

symbols = ['GUSH','AVAL', 'RNGR','MIRM','USDP', 'AMC']
    
for symbol in symbols:

    data = yf.download(symbol, period="1d", interval="1m")
    
    # Read the data
    data.index = pd.to_datetime(data.index, dayfirst=True)
    
    # Calculate exponential moving average
    data['12d_EMA'] = data.Close.ewm(span=12, adjust=False).mean()
    data['26d_EMA'] = data.Close.ewm(span=26, adjust=False).mean()
    
    # Calculate MACD
    data['macd'] = data['12d_EMA'] - data['26d_EMA'] 
    
    # Calculate Signal
    data['macdsignal'] = data.macd.ewm(span=9, adjust=False).mean()
    
    # Define Signal
    data['trading_signal'] = np.where(data['macd'] > data['macdsignal'], 1, -1)
    
    # Calculate Returns
    data['returns'] = data.Close.pct_change() * 10
    
    # Calculate Strategy Returns
    data['strategy_returns'] = data.returns * data.trading_signal.shift(1)

    # Calculate Cumulative Returns
    cumulative_strategy_returns = (data.strategy_returns + 1).cumprod()
    
    # Total number of trading days
    days = len(cumulative_strategy_returns)
    
    # Calculate compounded annual growth rate
    annual_returns = (cumulative_strategy_returns.iloc[-1]**(252/days) - 1)*100
    
    # Calculate the annualised volatility
    annual_volatility = data.strategy_returns.std() * np.sqrt(252) * 100
   
    # Assume the annual risk-free rate is 6%
    #risk_free_rate = 0.06
    #daily_risk_free_return = risk_free_rate/252
    
    # Calculate the excess returns by subtracting the daily returns by daily risk-free return
    #excess_daily_returns = data.strategy_returns - daily_risk_free_return
    
    # Calculate the sharpe ratio using the given formula
    #sharpe_ratio = (excess_daily_returns.mean() /
                    #excess_daily_returns.std()) * np.sqrt(252)
    
    #Get current values
    #Signal 1 or -1
    currentsignal = data['trading_signal'].iloc[-1]
    
    #Get most recent Close Value
    price = data['Close'].iloc[-1]
    price = round(price, 2)
    #Get Price
    buyprice = price * 2.5
    
    endoftrading = 0
    now = datetime.now().time()
    now = str(now.hour) + ':' + str(now.minute) + ':' + str(now.second)
    #end trading at 3:45 EST
    endtime = "15:45:00"

    if now > endtime:
        endoftrading = 1
        
    #Get Assest Info
    fractional = 0
    asset = api.get_asset(symbol)
    if asset.fractionable == 'True':
        fractional = 1

    #Check portfolio if we own shares
    res = df_pf.isin([symbol]).any().any()
    sell_now = 0
    
    if res:
        #get position information
        own_position = 1
        currentposition = api.get_position(symbol)
        qtyowned = int(currentposition.qty)
        current_value = float(currentposition.market_value)
        change_today = float(currentposition.change_today)
        cost_bases = float(currentposition.cost_basis)
        #Calculate current % Change
        pct_change = ((current_value - cost_bases) / cost_bases) * 100
        print(pct_change)
        if pct_change > 0 and pct_change >= 1:
            sell_now = 1
    else:
        own_position = 0
        
    print(symbol)
    print(currentsignal)
    
    
     
    if currentsignal == 1 and sell_now != 1:
        #check other factors (sharpe.. etc.)
        
        if buyprice <= TradingAmt and endoftrading != 1:
            #buy
            buyprice = round(buyprice, 2)
            #print('Buy: ' + symbol + ' at this price: ' + str(price))
            #print('Buy $' + str(buyprice) + ' amount of shares')
            
            #logging.debug('Date: ' + str(datetime.now()))
            #logging.debug('Buy: ' + symbol + ' at this price: ' + str(price) + ' for this amount: ' + str(buyprice))
            
            if fractional == 1:
                try:
                    # Send the buy order to the api
                    api.submit_order(
                                symbol=symbol,
                                notional=buyprice,
                                side='buy',
                                type='market',
                                time_in_force='day'
                            )
                    TradingAmt = TradingAmt - buyprice
                    #logging.debug('Remaining Trading Amount: ' + str(TradingAmt))
                except:
                    print('fail')
                    #logging.debug('Failed Trade')
                    #Close Logging
                    #logging.shutdown()
            else:
                if price <= TradingAmt:
                    try:
                        # Send the buy order to the api
                        api.submit_order(
                                    symbol=symbol,
                                    qty=1,
                                    side='buy',
                                    type='market',
                                    time_in_force='day'
                                )
                        TradingAmt = TradingAmt - buyprice
                        #logging.debug('Remaining Trading Amount: ' + str(TradingAmt))
                    except:
                        print('fail')
                        
            
    else:
        
        #sell
        if own_position == 1:
            #sell all price
            sellprice = current_value
        
            # Send the sell order to the api
            #print('Sell: ' + symbol + ' at this price: ' + str(price))
            #print('Sell $' + str(final_sale_price) + ' amount of shares')
            #logging.debug('Date: ' + str(datetime.now()))
            #logging.debug('Sell: ' + symbol + ' at this price: ' + str(price) + ' for this amount: ' + str(sellprice))
            if fractional == 1:
                try:
                    api.submit_order(
                                symbol=symbol,
                                notional=sellprice,
                                side='sell',
                                type='market',
                                time_in_force='day'
                               )
                    TradingAmt = TradingAmt + buyprice
                    #logging.debug('Remaining Trading Amount: ' + str(TradingAmt))
                except:
                    print('fail')
                    #logging.debug('Failed Trade')
                    #Close Logging
                    #logging.shutdown()      
            else:
                try:
                    api.submit_order(
                                symbol=symbol,
                                qty=qtyowned,
                                side='sell',
                                type='market',
                                time_in_force='day'
                               )
                    TradingAmt = TradingAmt + buyprice
                    #logging.debug('Remaining Trading Amount: ' + str(TradingAmt))
                except:
                    print('fail')
                    #logging.debug('Failed Trade')
                    #Close Logging
                    #logging.shutdown()    
            
    
        
#Close Logging
#logging.shutdown()



    
