import os
import pandas as pd
from datetime import datetime, timezone, timedelta
from tradingview_screener import Query, Column

os.makedirs('data', exist_ok=True)

# ตั้งเวลาเป็นเวลาประเทศไทย (UTC+7)
tz_bkk = timezone(timedelta(hours=7))
now_bkk = datetime.now(tz_bkk)
today_str = now_bkk.strftime('%Y%m%d')

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
trin_df = append_csv('SET_TRIN', trin, is_cumulative=False)
sma_df = append_csv('SET_PCT_SMA50', pct_sma50, is_cumulative=False)
nhnl_df = append_csv('SET_NH_NL', nh_nl, is_cumulative=False)

# คำนวณ McClellan Oscillator จาก Net Advances ย้อนหลัง
net_series = ad_df['close'].diff().fillna(ad_df['close'])
mcclellan = round((net_series.ewm(span=19, adjust=False).mean() - net_series.ewm(span=39, adjust=False).mean()).iloc[-1], 2)
mcc_df = append_csv('SET_MCCLELLAN', mcclellan, is_cumulative=False)

# 3. สร้างไฟล์ Pine Script สำเร็จรูป (SET_900_Breadth.pine)
dates_str  = ",".join(ad_df['date'].astype(str).tolist())
ad_str     = ",".join(ad_df['close'].astype(str).tolist())
trin_str   = ",".join(trin_df['close'].astype(str).tolist())
mcc_str    = ",".join(mcc_df['close'].astype(str).tolist())
sma_str    = ",".join(sma_df['close'].astype(str).tolist())
nhnl_str   = ",".join(nhnl_df['close'].astype(str).tolist())
cnt_str    = ",".join(ad_df['volume'].astype(str).tolist())

pine_code = f'''//@version=5
indicator("SET All Common Stocks (~900) Market Breadth", shorttitle="SET 900 Breadth", overlay=false)

// เลือกอินดิเคเตอร์ที่ต้องการแสดงผลจากเมนู Settings (รูปเฟือง)
metric = input.string("A/D Line", title="เลือก Market Breadth ที่ต้องการแสดง", options=["A/D Line", "TRIN (Arms Index)", "McClellan Oscillator", "% Above SMA 50", "NH-NL Index (52W)", "Valid Stocks Count"])
ema_len = input.int(10, title="Signal EMA Length", minval=1)

// ข้อมูลอัปเดตอัตโนมัติจาก GitHub (อัปเดตล่าสุด: {now_bkk.strftime("%Y-%m-%d %H:%M")} BKK)
var int[]   dates_arr = array.from({dates_str})
var float[] ad_arr    = array.from({ad_str})
var float[] trin_arr  = array.from({trin_str})
var float[] mcc_arr   = array.from({mcc_str})
var float[] sma_arr   = array.from({sma_str})
var float[] nhnl_arr  = array.from({nhnl_str})
var float[] cnt_arr   = array.from({cnt_str})

// จับคู่วันที่บนกราฟ TradingView ให้ตรงกับข้อมูลย้อนหลัง
bar_date = year(time, "Asia/Bangkok") * 10000 + month(time, "Asia/Bangkok") * 100 + dayofmonth(time, "Asia/Bangkok")
idx = array.indexof(dates_arr, bar_date)

float val = na
if idx != -1
    val := switch metric
        "A/D Line"             => array.get(ad_arr, idx)
        "TRIN (Arms Index)"    => array.get(trin_arr, idx)
        "McClellan Oscillator" => array.get(mcc_arr, idx)
        "% Above SMA 50"       => array.get(sma_arr, idx)
        "NH-NL Index (52W)"    => array.get(nhnl_arr, idx)
        "Valid Stocks Count"   => array.get(cnt_arr, idx)

sig_ema = ta.ema(val, ema_len)

// แสดงผลกราฟ (หากมีข้อมูล 1 วันแรก จะพล็อตเป็นจุดวงกลมใหญ่ให้เห็นชัดเจน)
is_hist = metric == "McClellan Oscillator" or metric == "NH-NL Index (52W)"
plot_col = metric == "TRIN (Arms Index)" ? (val < 1.0 ? color.new(#00C853, 0) : color.new(#D50000, 0)) : color.new(#2962FF, 0)

plot(val, title="Market Breadth Value", color=plot_col, linewidth=3, style=is_hist ? plot.style_columns : plot.style_linebr)
plot(val, title="Data Point Marker", color=plot_col, linewidth=4, style=plot.style_circles)
plot(sig_ema, title="Signal EMA", color=color.new(#FF6D00, 0), linewidth=1)
'''

with open('SET_900_Breadth.pine', 'w', encoding='utf-8') as f:
    f.write(pine_code)

print(f"อัปเดตสำเร็จวันที่ {{today_str}} | สร้างไฟล์ SET_900_Breadth.pine เรียบร้อย")
