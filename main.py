import streamlit as st
import pandas as pd
import numpy as np
from nsepython import nse_optionchain_scrapper
from datetime import datetime, date
import requests
from SmartApi import SmartConnect
import pyotp
from streamlit_autorefresh import st_autorefresh
import concurrent.futures
import time # For Dual Speed Logic ⏱️

# --- PAGE CONFIG ---
st.set_page_config(page_title="Nifty Trap Master PRO (SHAHRUKH Algo)", layout="wide", page_icon="🦁")

# --- WHITE UI CSS (Clean Light Theme) ---
st.markdown("""
<style>
    /* 1. Main Background - White */
    .stApp { background-color: #FFFFFF; color: #31333F; }
    
    /* 2. Standard Cards */
    .clean-card {
        background-color: #FFFFFF; border: 1px solid #E0E0E0; border-radius: 10px;
        padding: 10px; text-align: center; box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        color: #31333F; transition: transform 0.2s; margin-bottom: 5px;
    }
    .clean-card:hover { transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
    
    /* 3. Signal Boxes */
    .signal-box { padding: 20px; border-radius: 12px; text-align: center; margin: 10px 0; font-weight: bold; }
    .buy-signal { background-color: #E8F5E9; border: 2px solid #2E7D32; color: #1B5E20; }
    .sell-signal { background-color: #FFEBEE; border: 2px solid #C62828; color: #B71C1C; }
    .trap-signal { background-color: #FFF8E1; border: 2px solid #FF8F00; color: #BF360C; }

    /* 4. Action Box */
    .action-card { font-size: 1.5rem; font-weight: 900; padding: 15px; border-radius: 8px; text-align: center; border: 2px dashed; }

    /* 5. Select Box & Table */
    div[data-baseweb="select"] > div { background-color: #F8F9FA; border-color: #E0E0E0; }
    thead tr th { background-color: #F8F9FA !important; color: #31333F !important; }
</style>
""", unsafe_allow_html=True)

# --- 1. MASTER LOADER ---
@st.cache_data(ttl=86400)
def load_scrip_master():
    try:
        url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        data = requests.get(url).json()
        df = pd.DataFrame(data)
        return df[
            (df['exch_seg'] == 'NSE') | 
            ((df['exch_seg'] == 'NFO') & (df['name'] == 'NIFTY') & (df['instrumenttype'] == 'FUTIDX'))
        ]
    except: return None

# --- 2. FETCH OPTION CHAIN ---
def fetch_nse_chain():
    try:
        payload = nse_optionchain_scrapper('NIFTY')
        if payload:
            return payload['records']['data'], payload['records']['expiryDates']
    except Exception as e: pass
    return None, []

# --- 3. FETCH COMPONENTS ---
def fetch_single_stock(api, symbol, token, name):
    try:
        quote = api.ltpData("NSE", symbol, token)
        if quote['status']:
            ltp = float(quote['data']['ltp'])
            close = float(quote['data'].get('close', ltp))
            if close != 0: 
                change = ltp - close
                pct = (change / close) * 100
            else: pct = 0
            weight = 2 if name in ['HDFC Bank', 'Reliance'] else 1
            score_change = 0
            if pct > 0.05: score_change = (1 * weight)
            elif pct < -0.05: score_change = -(1 * weight)
            return name, pct, score_change
    except: pass
    return name, 0, 0

def fetch_heavyweights(api, master_df):
    weights = {
        'HDFCBANK-EQ': 'HDFC Bank', 'RELIANCE-EQ': 'Reliance',
        'ICICIBANK-EQ': 'ICICI Bank', 'INFY-EQ': 'Infosys', 'TCS-EQ': 'TCS'
    }
    results = {}
    total_score = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = []
        for symbol, name in weights.items():
            try:
                row = master_df[(master_df['symbol'] == symbol) & (master_df['exch_seg'] == 'NSE')]
                if not row.empty:
                    token = row.iloc[0]['token']
                    futures.append(executor.submit(fetch_single_stock, api, symbol, token, name))
            except: pass
        for f in concurrent.futures.as_completed(futures):
            name, pct, score = f.result()
            results[name] = pct
            total_score += score
    return results, total_score

# --- MAIN APP ---
st.title("🦁 Nifty Trap Master PRO (SHAHRUKH Algo)")

# Init Session States
if 'prev_pcr' not in st.session_state: st.session_state['prev_pcr'] = 0.0

# --- DUAL SPEED CACHE STATES ---
if 'nse_data_cache' not in st.session_state: st.session_state['nse_data_cache'] = None
if 'nse_expiry_cache' not in st.session_state: st.session_state['nse_expiry_cache'] = []
if 'last_nse_fetch_time' not in st.session_state: st.session_state['last_nse_fetch_time'] = 0

with st.sidebar:
    st.header("🔐 Login")
    api_key = st.text_input("API Key", type="password")
    client_id = st.text_input("Client ID")
    password = st.text_input("Password", type="password")
    totp = st.text_input("TOTP Secret", type="password")
    
    if st.button("Connect"):
        try:
            smartApi = SmartConnect(api_key=api_key)
            totp_obj = pyotp.TOTP(totp).now()
            data = smartApi.generateSession(client_id, password, totp_obj)
            if data['status']:
                st.session_state['angel_api'] = smartApi
                st.success("Connected!")
            else: st.error("Failed")
        except Exception as e: st.error(f"Error: {e}")
            
    # --- REFRESH RATE SET TO 10 SECONDS ---
    st_autorefresh(interval=10000, key="trap_refresh")
    st.caption("Auto-Refresh: 10 Seconds")

with st.spinner("Analyzing Market Data..."):
    master_df = load_scrip_master()

if 'angel_api' in st.session_state and master_df is not None:
    api = st.session_state['angel_api']
    
    # ----------------------------------------------------
    # A. FETCH ANGEL DATA (Every 10s - FAST) ⚡
    # ----------------------------------------------------
    comp_data, comp_score = fetch_heavyweights(api, master_df)
    
    # VWAP Logic
    fut_ltp = 0; fut_vwap = 0
    try:
        nifty_fut = master_df[(master_df['exch_seg'] == 'NFO') & (master_df['name'] == 'NIFTY') & (master_df['instrumenttype'] == 'FUTIDX')]
        if not nifty_fut.empty:
            nifty_fut['expiry'] = pd.to_datetime(nifty_fut['expiry'])
            nifty_fut = nifty_fut.sort_values('expiry')
            cur_fut = nifty_fut.iloc[0]
            q_pkt = api.ltpData("NFO", cur_fut['symbol'], cur_fut['token'])
            if q_pkt['status']:
                fut_ltp = float(q_pkt['data']['ltp'])
                fut_vwap = float(q_pkt['data'].get('averagePrice', q_pkt['data'].get('open', fut_ltp)))
    except: pass

    # Spot & VIX
    spot_price = 0; vix_price = 0
    try:
        spot_packet = api.ltpData("NSE", "Nifty 50", "99926000")
        if spot_packet['status']: spot_price = float(spot_packet['data']['ltp'])
        vix_packet = api.ltpData("NSE", "INDIA VIX", "26009")
        if vix_packet['status']: vix_price = float(vix_packet['data']['ltp'])
    except: pass

    # ----------------------------------------------------
    # B. FETCH NSE DATA (Every 30s - SAFE) 🐢
    # ----------------------------------------------------
    current_time = time.time()
    time_diff = current_time - st.session_state['last_nse_fetch_time']
    
    # Only fetch NSE if 30s passed OR cache is empty
    if time_diff > 30 or st.session_state['nse_data_cache'] is None:
        raw_chain, expiry_list = fetch_nse_chain()
        if raw_chain:
            st.session_state['nse_data_cache'] = raw_chain
            st.session_state['nse_expiry_cache'] = expiry_list
            st.session_state['last_nse_fetch_time'] = current_time
    
    # Load from Cache
    raw_chain = st.session_state['nse_data_cache']
    expiry_list = st.session_state['nse_expiry_cache']
    
    # Fallback Spot
    if spot_price == 0 and raw_chain: spot_price = raw_chain[0]['PE']['underlyingValue']

    if raw_chain and spot_price > 0:
        sel_exp = st.selectbox("📅 Select Expiry Date", expiry_list, index=0)
        
        chain_data = []
        total_pe_oi = 0
        total_ce_oi = 0
        
        for item in raw_chain:
            if item['expiryDate'] == sel_exp:
                ce = item.get('CE', {})
                pe = item.get('PE', {})
                ce_oi = ce.get('openInterest', 0)
                pe_oi = pe.get('openInterest', 0)
                total_ce_oi += ce_oi
                total_pe_oi += pe_oi
                chain_data.append({
                    'CE OI': ce_oi, 'CE LTP': ce.get('lastPrice', 0), 'Strike': item['strikePrice'],
                    'PE LTP': pe.get('lastPrice', 0), 'PE OI': pe_oi
                })
        
        df = pd.DataFrame(chain_data).sort_values('Strike')
        atm = round(spot_price / 50) * 50
        df_view = df[(df['Strike'] >= atm - 1000) & (df['Strike'] <= atm + 1000)]
        
        # Logic
        pcr = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 0
        res_strike = df_view.loc[df_view['CE OI'].idxmax(), 'Strike']
        sup_strike = df_view.loc[df_view['PE OI'].idxmax(), 'Strike']
        
        # PCR Arrow
        pcr_arrow = ""
        if st.session_state['prev_pcr'] != 0:
            if pcr > st.session_state['prev_pcr'] + 0.001: pcr_arrow = "⬆"
            elif pcr < st.session_state['prev_pcr'] - 0.001: pcr_arrow = "⬇"
        st.session_state['prev_pcr'] = pcr
        
        # SCORING
        bull_score = 0; bear_score = 0; reasons = []
        
        # 1. Components
        if comp_score > 3: bull_score += 4; reasons.append("Drivers Strong")
        elif comp_score > 0: bull_score += 2
        elif comp_score < -3: bear_score += 4; reasons.append("Drivers Weak")
        elif comp_score < 0: bear_score += 2
        
        # 2. VWAP Logic
        if fut_ltp > 0 and fut_vwap > 0:
            if fut_ltp > fut_vwap: 
                bull_score += 3; reasons.append("Above VWAP")
            elif fut_ltp < fut_vwap: 
                bear_score += 3; reasons.append("Below VWAP")
            
        # 3. PCR
        if pcr > 1.2: bull_score += 2; reasons.append(f"PCR Bullish")
        elif pcr < 0.8: bear_score += 2; reasons.append(f"PCR Bearish")
        
        if vix_price > 15: reasons.append(f"⚠️ VIX High")
            
        # 4. Levels
        dist_sup = abs(spot_price - sup_strike)
        dist_res = abs(spot_price - res_strike)
        
        if dist_sup < 40: bull_score += 4; reasons.append(f"At Support")
        elif dist_res < 40: bear_score += 4; reasons.append(f"At Resistance")
        
        if spot_price > res_strike + 15: bull_score += 3; reasons.append("Breakout")
        elif spot_price < sup_strike - 15: bear_score += 3; reasons.append("Breakdown")

        # Action Logic
        action_msg = "WAIT & WATCH"; action_color = "#FFF8E1"; action_txt_color = "#BF360C"; action_border = "#FF8F00"
        
        if bull_score > bear_score and dist_res < 20:
            action_msg = "🛑 BOOK PROFIT (EXIT)"; action_color = "#FFEBEE"; action_txt_color = "#B71C1C"; action_border = "#C62828"
        elif bear_score > bull_score and dist_sup < 20:
            action_msg = "🛑 BOOK PROFIT (EXIT)"; action_color = "#FFEBEE"; action_txt_color = "#B71C1C"; action_border = "#C62828"
        elif bull_score >= 7:
            if fut_ltp > fut_vwap: 
                action_msg = "🟢 FRESH ENTRY (CE)"; action_color = "#E8F5E9"; action_txt_color = "#1B5E20"; action_border = "#2E7D32"
            else:
                action_msg = "⚠️ WAIT (Price < VWAP)"; action_color = "#FFF8E1"; action_txt_color = "#BF360C"; action_border = "#FF8F00"
        elif bear_score >= 7:
            if fut_ltp < fut_vwap:
                action_msg = "🟢 FRESH ENTRY (PE)"; action_color = "#E8F5E9"; action_txt_color = "#1B5E20"; action_border = "#2E7D32"
            else:
                action_msg = "⚠️ WAIT (Price > VWAP)"; action_color = "#FFF8E1"; action_txt_color = "#BF360C"; action_border = "#FF8F00"
        elif bull_score > 4 or bear_score > 4:
            action_msg = "🟡 HOLD / TRAIL SL"; action_color = "#FFF8E1"; action_txt_color = "#BF360C"; action_border = "#FF8F00"

        # 2. SIGNAL BOX
        if "FRESH ENTRY" in action_msg:
            if "CE" in action_msg:
                st.markdown(f"""<div class='signal-box buy-signal'><h1>🚀 STRONG BUY CALL</h1><p>{' + '.join(reasons)}</p></div>""", unsafe_allow_html=True)
            else:
                st.markdown(f"""<div class='signal-box sell-signal'><h1>💥 STRONG BUY PUT</h1><p>{' + '.join(reasons)}</p></div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""<div class='signal-box trap-signal'><h3>👀 WAIT / TRAP ZONE</h3><p>{' + '.join(reasons)}</p></div>""", unsafe_allow_html=True)

        # 3. ACTION BOX
        st.markdown(f"""
        <div class='action-card' style='background-color: {action_color}; color: {action_txt_color}; border-color: {action_border};'>
            ACTION: {action_msg}
        </div>
        <div style="height: 15px;"></div>
        """, unsafe_allow_html=True)

        # 4. METRICS ROW
        m1, m_vwap, m2, m3, m4, m5 = st.columns(6)
        
        with m1:
            st.markdown(f"""<div class='clean-card'><small>NIFTY SPOT</small><br><b style='font-size: 1.4rem;'>{spot_price}</b></div>""", unsafe_allow_html=True)
        
        with m_vwap:
            vwap_col = "#31333F"
            if fut_ltp > fut_vwap: vwap_col = "#2E7D32" 
            elif fut_ltp < fut_vwap: vwap_col = "#C62828" 
            st.markdown(f"""<div class='clean-card'><small>FUT VWAP</small><br><b style='font-size: 1.4rem; color:{vwap_col}'>{int(fut_vwap)}</b></div>""", unsafe_allow_html=True)

        with m2:
            if pcr > 1: pcr_bg = "#E8F5E9"; pcr_txt = "#1B5E20"; pcr_border = "#2E7D32" 
            else: pcr_bg = "#FFEBEE"; pcr_txt = "#B71C1C"; pcr_border = "#C62828"
            st.markdown(f"""
            <div class='clean-card' style='background-color:{pcr_bg};border-color:{pcr_border};color:{pcr_txt}'>
                <small>PCR RATIO</small><br>
                <span style='font-size:1.4rem; font-weight:bold'>{pcr:.2f}</span>
                <span style='font-size:1.8rem; font-weight:bold; margin-left:5px'>{pcr_arrow}</span>
            </div>""", unsafe_allow_html=True)

        with m3:
            if vix_price > 15: vix_bg = "#FFEBEE"; vix_txt = "#B71C1C"; vix_border = "#C62828"
            else: vix_bg = "#E8F5E9"; vix_txt = "#1B5E20"; vix_border = "#2E7D32"
            st.markdown(f"""<div class='clean-card' style='background-color:{vix_bg};border-color:{vix_border};color:{vix_txt}'><small>INDIA VIX</small><br><b style='font-size:1.4rem'>{vix_price:.2f}</b></div>""", unsafe_allow_html=True)

        with m4:
            if bull_score > bear_score: conf_bg = "#E8F5E9"; conf_txt = "#1B5E20"; conf_border = "#2E7D32"; score_val = f"{bull_score}/10"
            else: conf_bg = "#FFEBEE"; conf_txt = "#B71C1C"; conf_border = "#C62828"; score_val = f"{bear_score}/10"
            st.markdown(f"""<div class='clean-card' style='background-color:{conf_bg};border-color:{conf_border};color:{conf_txt}'><small>CONFIDENCE</small><br><b style='font-size:1.4rem'>{score_val}</b></div>""", unsafe_allow_html=True)

        with m5:
             st.markdown(f"""<div class='clean-card'><small>LEVELS</small><br><span style='color:green;font-weight:bold'>S: {sup_strike}</span><br><span style='color:red;font-weight:bold'>R: {res_strike}</span></div>""", unsafe_allow_html=True)

        # 5. HEAVYWEIGHTS
        st.write("") 
        c1, c2, c3, c4, c5 = st.columns(5)
        cols = [c1, c2, c3, c4, c5]
        for i, (name, pct) in enumerate(comp_data.items()):
            if pct > 0: bg = "#E8F5E9"; txt = "#1B5E20"; border = "#2E7D32"
            else: bg = "#FFEBEE"; txt = "#B71C1C"; border = "#C62828"
            with cols[i]:
                st.markdown(f"""<div class='clean-card' style='padding:10px;background-color:{bg};color:{txt};border-color:{border}'><small>{name}</small><br><b style='font-size:1.1rem'>{pct:+.2f}%</b></div>""", unsafe_allow_html=True)

        # 6. TABLE
        st.write("") 
        def highlight_cols(row):
            s = [''] * len(row)
            if row['Strike'] == sup_strike: return ['background-color: #E8F5E9; color: #1B5E20; font-weight: bold'] * len(row)
            if row['Strike'] == res_strike: return ['background-color: #FFEBEE; color: #B71C1C; font-weight: bold'] * len(row)
            return s
        st.dataframe(df_view.style.apply(highlight_cols, axis=1), height=500, use_container_width=True)
        
    else: st.warning("Connecting to Data Feeds...")

else: st.info("👋 Please Login from Sidebar")