import requests
from bs4 import BeautifulSoup
import re
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_ipo_cache = {
    'data': None,
    'timestamp': 0
}
_cache_lock = threading.Lock()
CACHE_TTL = 300  # 5 minutes cache

# Curated & dynamically updated directory of Mainboard IPOs on InvestorGain / Chittorgarh
MAINBOARD_DIRECTORY = [
    {
        "name": "Deepa Jewellers",
        "url": "https://www.investorgain.com/gmp/deepa-jewellers-ipo/2081/",
        "open_date": "1-Sep",
        "close_date": "3-Sep",
        "boa_date": "4-Sep",
        "listing_date": "8-Sep",
        "status": "Upcoming",
        "lot_size": "84",
        "subscription": "-",
        "rating": "3",
        "issue_size": "₹459.72 Cr",
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/deepa-jewellers-ipo/2827/"
    },
    {
        "name": "Rays of Belief",
        "url": "https://www.investorgain.com/gmp/rays-of-belief-ipo/2041/",
        "open_date": "1-Sep",
        "close_date": "3-Sep",
        "boa_date": "4-Sep",
        "listing_date": "8-Sep",
        "status": "Upcoming",
        "lot_size": "62",
        "subscription": "-",
        "rating": "3",
        "issue_size": "₹239.00 Cr",
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/rays-of-belief-ipo/2787/"
    },
    {
        "name": "Purple Style Labs",
        "url": "https://www.investorgain.com/gmp/purple-style-labs-ipo/1897/",
        "open_date": "31-Aug",
        "close_date": "2-Sep",
        "boa_date": "3-Sep",
        "listing_date": "7-Sep",
        "status": "Open",
        "lot_size": "26",
        "subscription": "0.09x",
        "rating": "1",
        "issue_size": "₹680.00 Cr",
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/purple-style-labs-ipo/2622/"
    },
    {
        "name": "ESDS Software Solution",
        "url": "https://www.investorgain.com/gmp/esds-software-ipo/1607/",
        "open_date": "28-Aug",
        "close_date": "1-Sep",
        "boa_date": "2-Sep",
        "listing_date": "4-Sep",
        "status": "Open",
        "lot_size": "34",
        "subscription": "20.75x",
        "rating": "4",
        "issue_size": "₹720.00 Cr",
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/esds-software-ipo/1198/"
    },
    {
        "name": "Priority Jewels",
        "url": "https://www.investorgain.com/gmp/priority-jewels-ipo/1783/",
        "open_date": "28-Aug",
        "close_date": "1-Sep",
        "boa_date": "2-Sep",
        "listing_date": "4-Sep",
        "status": "Open",
        "lot_size": "75",
        "subscription": "22.35x",
        "rating": "4",
        "issue_size": "₹91.50 Cr",
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/priority-jewels-ipo/2435/"
    },
    {
        "name": "Lumino Industries",
        "url": "https://www.investorgain.com/gmp/lumino-industries-ipo/1619/",
        "open_date": "27-Aug",
        "close_date": "31-Aug",
        "boa_date": "1-Sep",
        "listing_date": "3-Sep",
        "status": "Closing Today",
        "lot_size": "182",
        "subscription": "67.01x",
        "rating": "4",
        "issue_size": "₹700.00 Cr",
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/lumino-industries-ipo/2013/"
    },
    {
        "name": "Annu Projects",
        "url": "https://www.investorgain.com/gmp/annu-projects-ipo/1815/",
        "open_date": "25-Aug",
        "close_date": "28-Aug",
        "boa_date": "31-Aug",
        "listing_date": "2-Sep",
        "status": "Closed",
        "lot_size": "151",
        "subscription": "2.93x",
        "rating": "1",
        "issue_size": "₹175.06 Cr",
        "chittorgarh_url": "https://www.chittorgarh.com/search.asp?q=Annu+Projects"
    },
    {
        "name": "Symbiotec Pharmalab",
        "url": "https://www.investorgain.com/gmp/symbiotec-pharmalab-ipo/2069/",
        "open_date": "24-Aug",
        "close_date": "27-Aug",
        "boa_date": "28-Aug",
        "listing_date": "1-Sep",
        "status": "Closed",
        "lot_size": "15",
        "subscription": "75.08x",
        "rating": "4",
        "issue_size": "₹1,757.00 Cr",
        "chittorgarh_url": "https://www.chittorgarh.com/search.asp?q=Symbiotec+Pharmalab"
    },
    {
        "name": "Hy-Tech Engineers",
        "url": "https://www.investorgain.com/gmp/hy-tech-engineers-ipo/1876/",
        "open_date": "24-Aug",
        "close_date": "27-Aug",
        "boa_date": "28-Aug",
        "listing_date": "1-Sep",
        "status": "Closed",
        "lot_size": "283",
        "subscription": "247.39x",
        "rating": "4",
        "issue_size": "₹135.73 Cr",
        "chittorgarh_url": "https://www.chittorgarh.com/search.asp?q=Hy-Tech+Engineers"
    },
    {
        "name": "Skyways Air",
        "url": "https://www.investorgain.com/gmp/skyways-air-ipo/1820/",
        "open_date": "24-Aug",
        "close_date": "27-Aug",
        "boa_date": "28-Aug",
        "listing_date": "1-Sep",
        "status": "Closed",
        "lot_size": "100",
        "subscription": "71.25x",
        "rating": "3",
        "issue_size": "₹582.80 Cr",
        "chittorgarh_url": "https://www.chittorgarh.com/search.asp?q=Skyways+Air"
    },
    {
        "name": "Augmont Enterprises",
        "url": "https://www.investorgain.com/gmp/augmont-enterprises-ipo/1938/",
        "open_date": "21-Aug",
        "close_date": "25-Aug",
        "boa_date": "27-Aug",
        "listing_date": "31-Aug",
        "status": "Listed",
        "lot_size": "19",
        "subscription": "111.18x",
        "rating": "4",
        "issue_size": "₹825.00 Cr",
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/augmont-enterprises-ipo/2673/"
    },
    {
        "name": "Tempsens Instruments (India)",
        "url": "https://www.investorgain.com/gmp/tempsens-instruments-india-ipo/1934/",
        "open_date": "20-Aug",
        "close_date": "24-Aug",
        "boa_date": "25-Aug",
        "listing_date": "28-Aug",
        "status": "Listed",
        "lot_size": "50",
        "subscription": "184.22x",
        "rating": "4",
        "issue_size": "₹650.00 Cr",
        "chittorgarh_url": "https://www.chittorgarh.com/search.asp?q=Tempsens+Instruments"
    },
    {
        "name": "Gaja Alternative Asset Management",
        "url": "https://www.investorgain.com/gmp/gaja-alternative-asset-management-ipo/1828/",
        "open_date": "19-Aug",
        "close_date": "21-Aug",
        "boa_date": "24-Aug",
        "listing_date": "26-Aug",
        "status": "Listed",
        "lot_size": "93",
        "subscription": "32.98x",
        "rating": "1",
        "issue_size": "₹550.00 Cr",
        "chittorgarh_url": "https://www.chittorgarh.com/search.asp?q=Gaja+Alternative"
    },
    {
        "name": "Shankesh Jewellers",
        "url": "https://www.investorgain.com/gmp/shankesh-jewellers-ipo/1932/",
        "open_date": "18-Aug",
        "close_date": "20-Aug",
        "boa_date": "21-Aug",
        "listing_date": "25-Aug",
        "status": "Listed",
        "lot_size": "160",
        "subscription": "2.80x",
        "rating": "1",
        "issue_size": "₹367.18 Cr",
        "chittorgarh_url": "https://www.chittorgarh.com/search.asp?q=Shankesh+Jewellers"
    },
    {
        "name": "Sunshine Pictures",
        "url": "https://www.investorgain.com/gmp/sunshine-pictures-ipo/1612/",
        "open_date": "18-Aug",
        "close_date": "20-Aug",
        "boa_date": "21-Aug",
        "listing_date": "25-Aug",
        "status": "Listed",
        "lot_size": "41",
        "subscription": "105.81x",
        "rating": "3",
        "issue_size": "₹282.14 Cr",
        "chittorgarh_url": "https://www.chittorgarh.com/search.asp?q=Sunshine+Pictures"
    },
    {
        "name": "Lalithaa Jewellery Mart",
        "url": "https://www.investorgain.com/gmp/lalithaa-jewellery-mart-ipo/1799/",
        "open_date": "17-Aug",
        "close_date": "19-Aug",
        "boa_date": "20-Aug",
        "listing_date": "24-Aug",
        "status": "Listed",
        "lot_size": "74",
        "subscription": "66.63x",
        "rating": "4",
        "issue_size": "₹1,700.00 Cr",
        "chittorgarh_url": "https://www.chittorgarh.com/search.asp?q=Lalithaa+Jewellery+Mart"
    }
]

def fetch_single_gmp(item, headers):
    url = item.get("url")
    if not url:
        return item

    try:
        r = requests.get(url, headers=headers, verify=False, timeout=6)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            scripts = soup.find_all('script', type='application/ld+json')
            
            for s in scripts:
                try:
                    data = json.loads(s.string)
                    if data.get('@type') == 'Dataset' and 'variableMeasured' in data:
                        gmp_val = 0.0
                        est_price = 0.0
                        gmp_pct = 0.0
                        for var in data['variableMeasured']:
                            vname = var.get('name', '')
                            val = var.get('value', '0')
                            if 'Grey Market Premium' in vname:
                                try: gmp_val = float(val)
                                except: pass
                            elif 'Estimated Listing Price' in vname:
                                try: est_price = float(val)
                                except: pass
                            elif 'GMP Percentage' in vname:
                                try: gmp_pct = float(val)
                                except: pass

                        price = round(est_price - gmp_val, 2) if est_price > gmp_val else 0.0
                        return {
                            **item,
                            'id': f"mainboard-ipo-{re.sub(r'[^a-z0-9]+', '-', item['name'].lower())}",
                            'board_type': 'Mainboard',
                            'gmp': gmp_val,
                            'gmp_raw': f"₹{gmp_val}",
                            'price': price,
                            'price_raw': f"₹{price}",
                            'estimated_listing_price': est_price,
                            'gain_percentage': gmp_pct,
                            'gain_str': f"{gmp_pct:+.2f}%" if gmp_pct != 0 else "0.00%",
                            'last_updated': time.strftime('%Y-%m-%d %H:%M:%S')
                        }

                    elif data.get('@type') == 'Article' and 'description' in data:
                        desc = data['description']
                        gmp_match = re.search(r'Current GMP is ₹?([\d\.]+)', desc)
                        est_match = re.search(r'estimated listing price ₹?([\d\.]+)', desc)
                        pct_match = re.search(r'approximately ([\d\.]+)%', desc)
                        price_match = re.search(r'issue price of ₹?([\d\.]+)', desc)

                        gmp_val = float(gmp_match.group(1)) if gmp_match else 0.0
                        est_price = float(est_match.group(1)) if est_match else 0.0
                        gmp_pct = float(pct_match.group(1)) if pct_match else 0.0
                        price = float(price_match.group(1)) if price_match else (est_price - gmp_val)

                        return {
                            **item,
                            'id': f"mainboard-ipo-{re.sub(r'[^a-z0-9]+', '-', item['name'].lower())}",
                            'board_type': 'Mainboard',
                            'gmp': gmp_val,
                            'gmp_raw': f"₹{gmp_val}",
                            'price': price,
                            'price_raw': f"₹{price}",
                            'estimated_listing_price': est_price,
                            'gain_percentage': gmp_pct,
                            'gain_str': f"{gmp_pct:+.2f}%" if gmp_pct != 0 else "0.00%",
                            'last_updated': time.strftime('%Y-%m-%d %H:%M:%S')
                        }
                except Exception:
                    pass
    except Exception as e:
        print(f"[IPO Service] Error fetching live GMP for {item.get('name')}: {e}")

    # Fallback with default structure
    return {
        **item,
        'id': f"mainboard-ipo-{re.sub(r'[^a-z0-9]+', '-', item['name'].lower())}",
        'board_type': 'Mainboard',
        'gmp': 0.0,
        'gmp_raw': '₹0',
        'price': 0.0,
        'price_raw': 'N/A',
        'estimated_listing_price': 0.0,
        'gain_percentage': 0.0,
        'gain_str': '0.00%',
        'last_updated': time.strftime('%Y-%m-%d %H:%M:%S')
    }

def fetch_mainboard_gmp_data():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.chittorgarh.com/'
    }

    # Fetch all Mainboard IPO live GMP values in parallel
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch_single_gmp, item, headers) for item in MAINBOARD_DIRECTORY]
        mainboard_list = [f.result() for f in futures]

    # Sort: Highest expected gain % first
    mainboard_list.sort(key=lambda x: x.get('gain_percentage', 0), reverse=True)

    # Compute summary metrics
    total_count = len(mainboard_list)
    positive_gmp_count = sum(1 for item in mainboard_list if item.get('gmp', 0) > 0)
    top_gainer = mainboard_list[0] if mainboard_list else None
    avg_gain = round(sum(item.get('gain_percentage', 0) for item in mainboard_list) / total_count, 2) if total_count > 0 else 0

    summary = {
        'total_mainboard_ipos': total_count,
        'positive_gmp_count': positive_gmp_count,
        'avg_expected_gain': avg_gain,
        'top_gainer': top_gainer['name'] if top_gainer else None,
        'top_gainer_gain_pct': top_gainer['gain_percentage'] if top_gainer else 0,
        'source': 'Chittorgarh & InvestorGain Live GMP Engine',
        'fetched_at': time.strftime('%Y-%m-%d %H:%M:%S')
    }

    return {
        'summary': summary,
        'ipos': mainboard_list
    }

def get_mainboard_ipos_cached(force_refresh=False):
    global _ipo_cache
    now = time.time()

    with _cache_lock:
        if not force_refresh and _ipo_cache['data'] and (now - _ipo_cache['timestamp'] < CACHE_TTL):
            return _ipo_cache['data']

    data = fetch_mainboard_gmp_data()

    with _cache_lock:
        _ipo_cache['data'] = data
        _ipo_cache['timestamp'] = now

    return data

if __name__ == "__main__":
    res = get_mainboard_ipos_cached(force_refresh=True)
    print(json.dumps(res, indent=2))
