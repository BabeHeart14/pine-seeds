import os
import pandas as pd
from datetime import datetime
from tradingview_screener import Query, Column

os.makedirs('data', exist_ok=True)

# 1. ดึงข้อมูลหุ้นสามัญไทยทั้งหมด (SET + mai) จาก TradingView Screener
count, df = (Query()
    .set_markets('thailand')
    .select(
        'name', 'type', 'close', 'change', 'Value.Traded',
        'SMA50', 'price_52_week_high', 'price_52_week_low'
    )
    .where(
        Column('type') == 'stock',
        Column('Value.Traded') >= 5000000  # กรองมูลค่าซื้อขาย >= 5.00 ล้านบาท
    )
    .limit(1500)
    .get_scanner_data())

if len(df) == 0:
    print("ไม่พบข้อมูลการซื้อขายวันนี้")
    exit(0)

# 2. คำนวณค่า Market Breadth ทั้ง 5 ตัว
adv_df = df[df['change'] > 0]
dec_df = df[df['change'] < 0]

adv_issues = len(adv_df)
dec_issues = len(dec_df)
net_advances = adv_issues - dec_issues

# TRIN
adv_val = adv_df['Value.Traded'].sum()
dec_val = dec_df['Value.Traded'].sum()
trin = round((adv_issues / max(dec_issues, 1)) / (adv_val / max(dec_val, 1)), 2)

# % Above SMA 50
valid_sma = df.dropna(subset=['close', 'SMA50'])
pct_sma50 = round((len(valid_sma[valid_sma['close'] > valid_sma['SMA50']]) / len(valid_sma)) * 100, 2) if len(valid_sma) > 0 else 0.0

# New Highs - New Lows (52-Week)
nh = len(df[df['close'] >= df['price_52_week_high']])
nl = len(df[df['close'] <= df['price_52_week_low']])
nh_nl = nh - nl

today_str = datetime.now().strftime('%Y%m%d')
valid_count = len(df)

def append_csv(filename, val, is_cumulative=False):
    filepath = f'data/{filename}.csv'
    try:
        hist_df = pd.read_csv(filepath, names=['date', 'open', 'high', 'low', 'close', 'volume'])
        last_val = hist_df['close'].iloc[-1] if len(hist_df) > 0 else 0
    except FileNotFoundError:
        hist_df = pd.DataFrame(columns=['date', 'open', 'high', 'low', 'close', 'volume'])
        last_val = 0

    final_val = (last_val + val) if is_cumulative else val
    new_row = pd.DataFrame([[today_str, final_val, final_val, final_val, final_val, valid_count]],
                           columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    hist_df = hist_df[hist_df['date'].astype(str) != today_str]
    hist_df = pd.concat([hist_df, new_row], ignore_index=True)
    hist_df.to_csv(filepath, index=False, header=False)
    return hist_df

# บันทึกไฟล์ CSV
ad_df = append_csv('SET_AD_LINE', net_advances, is_cumulative=True)
append_csv('SET_TRIN', trin, is_cumulative=False)
append_csv('SET_PCT_SMA50', pct_sma50, is_cumulative=False)
append_csv('SET_NH_NL', nh_nl, is_cumulative=False)

# คำนวณ McClellan Oscillator จาก Net Advances ย้อนหลัง
net_series = ad_df['close'].diff().fillna(ad_df['close'])
mcclellan = round((net_series.ewm(span=19, adjust=False).mean() - net_series.ewm(span=39, adjust=False).mean()).iloc[-1], 2)
append_csv('SET_MCCLELLAN', mcclellan, is_cumulative=False)

print(f"อัปเดตสำเร็จวันที่ {today_str} | หุ้นผ่านเกณฑ์: {valid_count} ตัว")
