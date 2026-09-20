import numpy as np
import pandas as pd


def ema(s, n): return s.ewm(span=n, adjust=False, min_periods=n).mean()
def rsi(s, n=14):
    d=s.diff(); up=d.clip(lower=0).rolling(n).mean(); down=(-d.clip(upper=0)).rolling(n).mean(); rs=up/down.replace(0,np.nan); result=100-(100/(1+rs)); return result.where(~down.eq(0), 100.0)
def macd(s):
    m=ema(s,12)-ema(s,26); return m, ema(m,9)
def atr(df,n=14):
    prev=df.close.shift(); tr=pd.concat([df.high-df.low,(df.high-prev).abs(),(df.low-prev).abs()],axis=1).max(axis=1); return tr.rolling(n).mean()
def bollinger(s,n=20,k=2):
    mid=s.rolling(n).mean(); sd=s.rolling(n).std(); return mid,mid+k*sd,mid-k*sd
def compute_features(df):
    out=df.copy(); out["ema20"]=ema(df.close,20); out["ema50"]=ema(df.close,50); out["ema200"]=ema(df.close,200); out["rsi"]=rsi(df.close); out["macd"],out["macd_signal"]=macd(df.close); out["atr"]=atr(df); out["bb_mid"],out["bb_upper"],out["bb_lower"]=bollinger(df.close); out["volatility"]=df.close.pct_change().rolling(20).std(); out["volume_z"]=(df.volume-df.volume.rolling(20).mean())/df.volume.rolling(20).std(); return out
