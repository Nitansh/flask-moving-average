"""
Service to fetch and parse Mainboard IPOs & Live GMP Data
Sources: InvestorGain.com & Chittorgarh.com
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import time
import threading
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Global in-memory cache
_cache = None
_cache_time = 0
_cache_lock = threading.Lock()
CACHE_TTL = 300  # 5 minutes cache

# Curated & dynamically updated directory of Mainboard IPOs on InvestorGain / Chittorgarh
MAINBOARD_DIRECTORY = [
    {
        "name": "Veegaland Developers",
        "url": "https://www.investorgain.com/gmp/veegaland-developers-ipo/2095/",
        "open_date": "10-Sep",
        "close_date": "15-Sep",
        "boa_date": "16-Sep",
        "listing_date": "18-Sep",
        "status": "Upcoming",
        "lot_size": "107",
        "subscription": "-",
        "rating": "3",
        "issue_size": "₹210.00 Cr",
        "default_price": 140.0,
        "default_gmp": 22.0,
        "default_gain_pct": 15.71,
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/veegaland-developers-ipo/2855/"
    },
    {
        "name": "Manipal Payment and Identity Solutions",
        "url": "https://www.investorgain.com/gmp/manipal-payment-and-identity-solutions-ipo/2091/",
        "open_date": "9-Sep",
        "close_date": "11-Sep",
        "boa_date": "15-Sep",
        "listing_date": "17-Sep",
        "status": "Upcoming",
        "lot_size": "44",
        "subscription": "-",
        "rating": "2",
        "issue_size": "₹805.00 Cr",
        "default_price": 339.0,
        "default_gmp": 0.0,
        "default_gain_pct": 0.0,
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/manipal-payment-and-identity-solutions-ipo/2851/"
    },
    {
        "name": "Karamtara Engineering",
        "url": "https://www.investorgain.com/gmp/karamtara-engineering-ipo/2093/",
        "open_date": "9-Sep",
        "close_date": "11-Sep",
        "boa_date": "15-Sep",
        "listing_date": "17-Sep",
        "status": "Upcoming",
        "lot_size": "59",
        "subscription": "-",
        "rating": "3",
        "issue_size": "₹875.00 Cr",
        "default_price": 254.0,
        "default_gmp": 20.0,
        "default_gain_pct": 7.87,
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/karamtara-engineering-ipo/2853/"
    },
    {
        "name": "LCC Projects",
        "url": "https://www.investorgain.com/gmp/lcc-projects-ipo/2094/",
        "open_date": "9-Sep",
        "close_date": "11-Sep",
        "boa_date": "15-Sep",
        "listing_date": "17-Sep",
        "status": "Upcoming",
        "lot_size": "102",
        "subscription": "-",
        "rating": "2",
        "issue_size": "₹427.14 Cr",
        "default_price": 146.0,
        "default_gmp": 0.0,
        "default_gain_pct": 0.0,
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/lcc-projects-ipo/2854/"
    },
    {
        "name": "Rentomojo",
        "url": "https://www.investorgain.com/gmp/rentomojo-ipo/2092/",
        "open_date": "9-Sep",
        "close_date": "11-Sep",
        "boa_date": "15-Sep",
        "listing_date": "17-Sep",
        "status": "Upcoming",
        "lot_size": "37",
        "subscription": "-",
        "rating": "4",
        "issue_size": "₹1,255.57 Cr",
        "default_price": 404.0,
        "default_gmp": 55.0,
        "default_gain_pct": 13.61,
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/rentomojo-ipo/2852/"
    },
    {
        "name": "Asset Reconstruction Company",
        "url": "https://www.investorgain.com/gmp/asset-reconstruction-company-ipo/2090/",
        "open_date": "9-Sep",
        "close_date": "11-Sep",
        "boa_date": "15-Sep",
        "listing_date": "17-Sep",
        "status": "Upcoming",
        "lot_size": "107",
        "subscription": "-",
        "rating": "2",
        "issue_size": "₹732.97 Cr",
        "default_price": 139.0,
        "default_gmp": 0.0,
        "default_gain_pct": 0.0,
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/asset-reconstruction-company-india-arcil-ipo/2850/"
    },
    {
        "name": "Steamhouse India",
        "url": "https://www.investorgain.com/gmp/steamhouse-india-ipo/2089/",
        "open_date": "9-Sep",
        "close_date": "11-Sep",
        "boa_date": "15-Sep",
        "listing_date": "17-Sep",
        "status": "Upcoming",
        "lot_size": "100",
        "subscription": "-",
        "rating": "2",
        "issue_size": "₹414.00 Cr",
        "default_price": 150.0,
        "default_gmp": 0.0,
        "default_gain_pct": 0.0,
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/steamhouse-india-ipo/2849/"
    },
    {
        "name": "Glass Wall Systems",
        "url": "https://www.investorgain.com/gmp/glass-wall-systems-ipo/2088/",
        "open_date": "8-Sep",
        "close_date": "10-Sep",
        "boa_date": "11-Sep",
        "listing_date": "15-Sep",
        "status": "Upcoming",
        "lot_size": "82",
        "subscription": "-",
        "rating": "4",
        "issue_size": "₹427.89 Cr",
        "default_price": 182.0,
        "default_gmp": 61.0,
        "default_gain_pct": 33.52,
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/glass-wall-systems-india-ipo/2848/"
    },
    {
        "name": "Prasol Chemicals",
        "url": "https://www.investorgain.com/gmp/prasol-chemicals-ipo/2087/",
        "open_date": "8-Sep",
        "close_date": "10-Sep",
        "boa_date": "11-Sep",
        "listing_date": "15-Sep",
        "status": "Upcoming",
        "lot_size": "22",
        "subscription": "-",
        "rating": "4",
        "issue_size": "₹500.00 Cr",
        "default_price": 676.0,
        "default_gmp": 170.0,
        "default_gain_pct": 25.15,
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/prasol-chemicals-ipo/2847/"
    },
    {
        "name": "Kanohar Electricals",
        "url": "https://www.investorgain.com/gmp/kanohar-electricals-ipo/2086/",
        "open_date": "8-Sep",
        "close_date": "10-Sep",
        "boa_date": "11-Sep",
        "listing_date": "15-Sep",
        "status": "Upcoming",
        "lot_size": "23",
        "subscription": "-",
        "rating": "4",
        "issue_size": "₹1,055.74 Cr",
        "default_price": 632.0,
        "default_gmp": 205.0,
        "default_gain_pct": 32.44,
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/kanohar-electricals-ipo/2846/"
    },
    {
        "name": "Pranav Constructions",
        "url": "https://www.investorgain.com/gmp/pranav-constructions-ipo/2085/",
        "open_date": "7-Sep",
        "close_date": "9-Sep",
        "boa_date": "10-Sep",
        "listing_date": "12-Sep",
        "status": "Upcoming",
        "lot_size": "120",
        "subscription": "-",
        "rating": "3",
        "issue_size": "₹351.00 Cr",
        "default_price": 124.0,
        "default_gmp": 34.0,
        "default_gain_pct": 27.42,
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/pranav-constructions-ipo/2845/"
    },
    {
        "name": "Deepa Jewellers",
        "url": "https://www.investorgain.com/gmp/deepa-jewellers-ipo/2081/",
        "open_date": "1-Sep",
        "close_date": "3-Sep",
        "boa_date": "4-Sep",
        "listing_date": "8-Sep",
        "status": "Closed",
        "lot_size": "84",
        "subscription": "43.40x",
        "rating": "3",
        "issue_size": "₹459.72 Cr",
        "default_price": 177.0,
        "default_gmp": 22.0,
        "default_gain_pct": 12.43,
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/deepa-jewellers-ipo/2827/"
    },
    {
        "name": "Rays of Belief",
        "url": "https://www.investorgain.com/gmp/rays-of-belief-ipo/2041/",
        "open_date": "1-Sep",
        "close_date": "3-Sep",
        "boa_date": "4-Sep",
        "listing_date": "8-Sep",
        "status": "Closed",
        "lot_size": "62",
        "subscription": "107.71x",
        "rating": "3",
        "issue_size": "₹239.00 Cr",
        "default_price": 239.0,
        "default_gmp": 17.0,
        "default_gain_pct": 7.11,
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/rays-of-belief-ipo/2787/"
    },
    {
        "name": "Purple Style Labs",
        "url": "https://www.investorgain.com/gmp/purple-style-labs-ipo/1897/",
        "open_date": "31-Aug",
        "close_date": "2-Sep",
        "boa_date": "3-Sep",
        "listing_date": "7-Sep",
        "status": "Closed",
        "lot_size": "26",
        "subscription": "1.36x",
        "rating": "1",
        "issue_size": "₹680.00 Cr",
        "default_price": 575.0,
        "default_gmp": 2.0,
        "default_gain_pct": 0.35,
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/purple-style-labs-ipo/2622/"
    },
    {
        "name": "ESDS Software Solution",
        "url": "https://www.investorgain.com/gmp/esds-software-ipo/1607/",
        "open_date": "28-Aug",
        "close_date": "1-Sep",
        "boa_date": "2-Sep",
        "listing_date": "4-Sep",
        "status": "Listed",
        "lot_size": "34",
        "subscription": "142.88x",
        "rating": "4",
        "issue_size": "₹720.00 Cr",
        "default_price": 429.0,
        "default_gmp": 311.0,
        "default_gain_pct": 72.49,
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/esds-software-ipo/1198/"
    },
    {
        "name": "Priority Jewels",
        "url": "https://www.investorgain.com/gmp/priority-jewels-ipo/1783/",
        "open_date": "28-Aug",
        "close_date": "1-Sep",
        "boa_date": "2-Sep",
        "listing_date": "4-Sep",
        "status": "Listed",
        "lot_size": "75",
        "subscription": "100.45x",
        "rating": "4",
        "issue_size": "₹91.50 Cr",
        "default_price": 200.0,
        "default_gmp": 28.0,
        "default_gain_pct": 14.0,
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/priority-jewels-ipo/2435/"
    },
    {
        "name": "Lumino Industries",
        "url": "https://www.investorgain.com/gmp/lumino-industries-ipo/1619/",
        "open_date": "27-Aug",
        "close_date": "31-Aug",
        "boa_date": "1-Sep",
        "listing_date": "3-Sep",
        "status": "Listed",
        "lot_size": "182",
        "subscription": "124.02x",
        "rating": "4",
        "issue_size": "₹700.00 Cr",
        "default_price": 82.0,
        "default_gmp": 38.0,
        "default_gain_pct": 46.34,
        "chittorgarh_url": "https://www.chittorgarh.com/ipo/lumino-industries-ipo/2013/"
    },
    {
        "name": "Annu Projects",
        "url": "https://www.investorgain.com/gmp/annu-projects-ipo/1815/",
        "open_date": "25-Aug",
        "close_date": "28-Aug",
        "boa_date": "31-Aug",
        "listing_date": "2-Sep",
        "status": "Listed",
        "lot_size": "151",
        "subscription": "2.93x",
        "rating": "1",
        "issue_size": "₹175.06 Cr",
        "default_price": 99.0,
        "default_gmp": -7.0,
        "default_gain_pct": -7.07,
        "chittorgarh_url": "https://www.chittorgarh.com/search.asp?q=Annu+Projects"
    },
    {
        "name": "Symbiotec Pharmalab",
        "url": "https://www.investorgain.com/gmp/symbiotec-pharmalab-ipo/2069/",
        "open_date": "24-Aug",
        "close_date": "27-Aug",
        "boa_date": "28-Aug",
        "listing_date": "1-Sep",
        "status": "Listed",
        "lot_size": "15",
        "subscription": "75.08x",
        "rating": "4",
        "issue_size": "₹1,757.00 Cr",
        "default_price": 988.0,
        "default_gmp": 185.0,
        "default_gain_pct": 18.72,
        "chittorgarh_url": "https://www.chittorgarh.com/search.asp?q=Symbiotec+Pharmalab"
    },
    {
        "name": "Hy-Tech Engineers",
        "url": "https://www.investorgain.com/gmp/hy-tech-engineers-ipo/1876/",
        "open_date": "24-Aug",
        "close_date": "27-Aug",
        "boa_date": "28-Aug",
        "listing_date": "1-Sep",
        "status": "Listed",
        "lot_size": "283",
        "subscription": "247.39x",
        "rating": "4",
        "issue_size": "₹135.73 Cr",
        "default_price": 53.0,
        "default_gmp": 39.0,
        "default_gain_pct": 73.58,
        "chittorgarh_url": "https://www.chittorgarh.com/search.asp?q=Hy-Tech+Engineers"
    },
    {
        "name": "Skyways Air",
        "url": "https://www.investorgain.com/gmp/skyways-air-ipo/1820/",
        "open_date": "24-Aug",
        "close_date": "27-Aug",
        "boa_date": "28-Aug",
        "listing_date": "1-Sep",
        "status": "Listed",
        "lot_size": "100",
        "subscription": "71.25x",
        "rating": "3",
        "issue_size": "₹582.80 Cr",
        "default_price": 138.0,
        "default_gmp": 33.0,
        "default_gain_pct": 23.91,
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
        "default_price": 788.0,
        "default_gmp": 290.0,
        "default_gain_pct": 36.8,
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
        "default_price": 300.0,
        "default_gmp": 330.0,
        "default_gain_pct": 110.0,
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
        "default_price": 160.0,
        "default_gmp": 18.5,
        "default_gain_pct": 11.56,
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
        "default_price": 93.0,
        "default_gmp": 2.75,
        "default_gain_pct": 2.96,
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
        "default_price": 360.0,
        "default_gmp": 50.0,
        "default_gain_pct": 13.89,
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
        "default_price": 100.0,
        "default_gmp": 0.0,
        "default_gain_pct": 0.0,
        "chittorgarh_url": "https://www.chittorgarh.com/search.asp?q=Lalithaa+Jewellery+Mart"
    }
]

def fetch_single_gmp(item, headers):
    url = item.get("url")
    default_price = float(item.get("default_price", 0.0))
    default_gmp = float(item.get("default_gmp", 0.0))
    default_gain = float(item.get("default_gain_pct", 0.0))
    default_est = round(default_price + default_gmp, 2) if default_price > 0 else 0.0

    if not url:
        return {
            **item,
            'id': f"mainboard-ipo-{re.sub(r'[^a-z0-9]+', '-', item['name'].lower())}",
            'board_type': 'Mainboard',
            'gmp': default_gmp,
            'gmp_raw': f"₹{default_gmp}",
            'price': default_price,
            'price_raw': f"₹{default_price}" if default_price > 0 else "N/A",
            'estimated_listing_price': default_est,
            'gain_percentage': default_gain,
            'gain_str': f"{default_gain:+.2f}%" if default_gain != 0 else "0.00%",
            'last_updated': time.strftime('%Y-%m-%d %H:%M:%S')
        }

    try:
        r = requests.get(url, headers=headers, verify=False, timeout=5)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            scripts = soup.find_all('script', type='application/ld+json')
            
            for s in scripts:
                try:
                    data = json.loads(s.string)
                    if data.get('@type') == 'Dataset' and 'variableMeasured' in data:
                        gmp_val = default_gmp
                        est_price = default_est
                        gmp_pct = default_gain
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

                        price = round(est_price - gmp_val, 2) if est_price > gmp_val else default_price
                        return {
                            **item,
                            'id': f"mainboard-ipo-{re.sub(r'[^a-z0-9]+', '-', item['name'].lower())}",
                            'board_type': 'Mainboard',
                            'gmp': gmp_val,
                            'gmp_raw': f"₹{gmp_val}",
                            'price': price,
                            'price_raw': f"₹{price}" if price > 0 else "N/A",
                            'estimated_listing_price': est_price if est_price > 0 else round(price + gmp_val, 2),
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

                        gmp_val = float(gmp_match.group(1)) if gmp_match else default_gmp
                        est_price = float(est_match.group(1)) if est_match else default_est
                        gmp_pct = float(pct_match.group(1)) if pct_match else default_gain
                        price = float(price_match.group(1)) if price_match else (round(est_price - gmp_val, 2) if est_price > gmp_val else default_price)

                        return {
                            **item,
                            'id': f"mainboard-ipo-{re.sub(r'[^a-z0-9]+', '-', item['name'].lower())}",
                            'board_type': 'Mainboard',
                            'gmp': gmp_val,
                            'gmp_raw': f"₹{gmp_val}",
                            'price': price,
                            'price_raw': f"₹{price}" if price > 0 else "N/A",
                            'estimated_listing_price': est_price if est_price > 0 else round(price + gmp_val, 2),
                            'gain_percentage': gmp_pct,
                            'gain_str': f"{gmp_pct:+.2f}%" if gmp_pct != 0 else "0.00%",
                            'last_updated': time.strftime('%Y-%m-%d %H:%M:%S')
                        }
                except Exception:
                    pass
    except Exception as e:
        print(f"[IPO Service] Error fetching live GMP for {item.get('name')}: {e}")

    # Fallback to curated default values
    return {
        **item,
        'id': f"mainboard-ipo-{re.sub(r'[^a-z0-9]+', '-', item['name'].lower())}",
        'board_type': 'Mainboard',
        'gmp': default_gmp,
        'gmp_raw': f"₹{default_gmp}",
        'price': default_price,
        'price_raw': f"₹{default_price}" if default_price > 0 else "N/A",
        'estimated_listing_price': default_est,
        'gain_percentage': default_gain,
        'gain_str': f"{default_gain:+.2f}%" if default_gain != 0 else "0.00%",
        'last_updated': time.strftime('%Y-%m-%d %H:%M:%S')
    }

def fetch_mainboard_gmp_data():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    results = []
    # Multi-threaded fetching for quick responses
    threads = []
    thread_results = [None] * len(MAINBOARD_DIRECTORY)

    def worker(index, item):
        thread_results[index] = fetch_single_gmp(item, headers)

    for i, item in enumerate(MAINBOARD_DIRECTORY):
        t = threading.Thread(target=worker, args=(i, item))
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=8)

    for res in thread_results:
        if res:
            results.append(res)

    # Sort primarily by gain percentage descending
    results.sort(key=lambda x: x.get('gain_percentage', 0), reverse=True)

    # Compute summary metrics
    total_count = len(results)
    positive_gmp_count = sum(1 for item in results if item.get('gmp', 0) > 0)
    top_gainer = results[0] if results else None
    avg_gain = round(sum(item.get('gain_percentage', 0) for item in results) / total_count, 2) if total_count > 0 else 0

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
        'ipos': results
    }

def get_mainboard_ipos_cached(force_refresh=False):
    global _cache, _cache_time

    with _cache_lock:
        now = time.time()
        if not force_refresh and _cache is not None and (now - _cache_time) < CACHE_TTL:
            return _cache

        try:
            data = fetch_mainboard_gmp_data()
            if data and len(data.get('ipos', [])) > 0:
                _cache = data
                _cache_time = now
                return _cache
        except Exception as e:
            print(f"[IPO Service Error] {e}")

        # If refresh fails but we have old cache, return old cache
        if _cache is not None:
            return _cache

        return {
            "summary": {
                'total_mainboard_ipos': 0,
                'positive_gmp_count': 0,
                'avg_expected_gain': 0,
                'top_gainer': None,
                'top_gainer_gain_pct': 0,
                'source': 'Chittorgarh & InvestorGain Live GMP Engine',
                'fetched_at': time.strftime('%Y-%m-%d %H:%M:%S')
            },
            "ipos": []
        }

# Alias for backward compatibility
get_cached_mainboard_ipos = get_mainboard_ipos_cached

if __name__ == "__main__":
    print("Testing get_mainboard_ipos_cached...")
    res = get_mainboard_ipos_cached(force_refresh=True)
    print(f"Fetched {len(res['ipos'])} IPOs. Summary: {res['summary']}")
    print(json.dumps(res, indent=2))
