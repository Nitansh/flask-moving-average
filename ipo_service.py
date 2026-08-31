import requests
from bs4 import BeautifulSoup
import re
import json
import time
import threading
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_ipo_cache = {
    'data': None,
    'timestamp': 0
}
_cache_lock = threading.Lock()
CACHE_TTL = 900  # 15 minutes

def clean_text(text):
    if not text:
        return ""
    return re.sub(r'\s+', ' ', str(text)).strip()

def parse_price(val_str):
    if not val_str:
        return 0.0
    val_clean = str(val_str).replace('₹', '').replace(',', '').strip()
    nums = re.findall(r'[\d\.]+', val_clean)
    if nums:
        try:
            return float(nums[-1])  # Upper band if range
        except ValueError:
            pass
    return 0.0

def parse_gmp(val_str):
    if not val_str:
        return 0.0
    val_clean = str(val_str).replace('₹', '').replace(',', '').strip()
    nums = re.findall(r'[-+]?\d*\.\d+|\d+', val_clean)
    if nums:
        try:
            return float(nums[0])
        except ValueError:
            pass
    return 0.0

def fetch_chittorgarh_ipo_details(ch_url, headers):
    """
    Fetches individual Chittorgarh IPO page to extract Price Band, Dates, Lot Size, Issue Size, and GMP if present.
    """
    details = {
        'price': 0.0,
        'price_raw': 'N/A',
        'open_date': 'TBA',
        'close_date': 'TBA',
        'listing_date': 'TBA',
        'lot_size': 'N/A',
        'issue_size': 'N/A',
        'gmp': 0.0,
        'gmp_raw': '₹0'
    }
    if not ch_url or 'chittorgarh.com' not in ch_url:
        return details

    try:
        resp = requests.get(ch_url, headers=headers, verify=False, timeout=6)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for r in rows:
                    cells = [clean_text(td.get_text()) for td in r.find_all(['th', 'td'])]
                    if len(cells) >= 2:
                        label = cells[0].lower()
                        val = cells[1]
                        if 'price band' in label or 'issue price' in label:
                            details['price_raw'] = val
                            details['price'] = parse_price(val)
                        elif 'ipo date' in label or 'issue date' in label:
                            details['open_date'] = val
                            if 'to' in val:
                                parts = val.split('to')
                                details['open_date'] = parts[0].strip()
                                details['close_date'] = parts[1].strip()
                        elif 'listing date' in label:
                            details['listing_date'] = val
                        elif 'lot size' in label:
                            details['lot_size'] = val
                        elif 'total issue size' in label or 'issue size' in label:
                            details['issue_size'] = val

            # Search text for GMP references if available
            text = soup.get_text()
            gmp_match = re.search(r'GMP\s*(?:is|:)?\s*₹?\s*(\d+)', text, re.I)
            if gmp_match:
                details['gmp'] = float(gmp_match.group(1))
                details['gmp_raw'] = f"₹{gmp_match.group(1)}"

    except Exception as e:
        print(f"[IPO Service] Chittorgarh page detail fetch warning for {ch_url}: {e}")

    return details

def fetch_chittorgarh_mainboard_directory(headers):
    """
    Scrapes official Chittorgarh Mainboard IPO list to get exact Mainboard titles and Chittorgarh detail URLs.
    """
    mainboard_map = {}
    url = "https://www.chittorgarh.com/report/ipo-in-india-list-main-board-sme/82/mainboard/"
    try:
        resp = requests.get(url, headers=headers, verify=False, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            links = soup.find_all('a', href=re.compile(r'/ipo/[a-z0-9-]+/\d+/'))
            for a in links:
                title = clean_text(a.get_text(strip=True))
                href = a.get('href', '')
                if title and href:
                    clean_name = re.sub(r'\s+IPO$', '', title, flags=re.I).strip()
                    ch_link = href if href.startswith('http') else f"https://www.chittorgarh.com{href}" if href.startswith('/') else href
                    mainboard_map[clean_name.lower()] = {
                        'name': clean_name,
                        'chittorgarh_url': ch_link
                    }
    except Exception as e:
        print(f"[IPO Service] Chittorgarh mainboard fetch warning: {e}")
    return mainboard_map

def fetch_mainboard_gmp_data():
    """
    Fetches and parses live GMP data specifically filtered for Mainboard IPOs from Chittorgarh and live aggregators.
    Returns structured dict with list and summary metadata.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.chittorgarh.com/'
    }

    chittorgarh_map = fetch_chittorgarh_mainboard_directory(headers)
    mainboard_list = []
    fetched_names = set()

    # Primary source for live GMP table
    gmp_urls = [
        "https://www.ipowatch.in/ipo-grey-market-premium-gmp/",
        "https://www.chittorgarh.com/report/ipo-in-india-gmp-rates-live/104/"
    ]

    for url in gmp_urls:
        try:
            resp = requests.get(url, headers=headers, verify=False, timeout=8)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, 'html.parser')
            tables = soup.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                if len(rows) <= 1:
                    continue

                headers_text = [clean_text(cell.get_text()) for cell in rows[0].find_all(['th', 'td'])]
                if not any('gmp' in h.lower() or 'ipo' in h.lower() for h in headers_text):
                    continue

                for r in rows[1:]:
                    cells = [clean_text(td.get_text()) for td in r.find_all(['td', 'th'])]
                    if not cells or len(cells) < 3:
                        continue

                    raw_name = cells[0]
                    if not raw_name or 'no data' in raw_name.lower():
                        continue

                    # Filter out SME IPOs
                    is_sme = bool(re.search(r'\b(sme)\b', raw_name, re.I))
                    if is_sme:
                        continue

                    clean_name = re.sub(r'\(sme\)', '', raw_name, flags=re.I).strip()
                    clean_name = re.sub(r'\s+IPO$', '', clean_name, flags=re.I).strip()
                    name_key = clean_name.lower()

                    if name_key in fetched_names:
                        continue
                    fetched_names.add(name_key)

                    gmp_raw = cells[1] if len(cells) > 1 else "₹0"
                    price_raw = cells[2] if len(cells) > 2 else "0"
                    gain_raw = cells[3] if len(cells) > 3 else "0%"
                    rating = cells[4] if len(cells) > 4 else "-"
                    open_date = cells[5] if len(cells) > 5 else "-"
                    close_date = cells[6] if len(cells) > 6 else "-"
                    boa_date = cells[7] if len(cells) > 7 else "-"

                    gmp_val = parse_gmp(gmp_raw)
                    price_val = parse_price(price_raw)
                    
                    est_listing_price = round(price_val + gmp_val, 2) if price_val > 0 else 0
                    gain_pct = round((gmp_val / price_val) * 100, 2) if price_val > 0 else 0.0

                    status = "Open"
                    if "closed" in close_date.lower() or "close" in close_date.lower():
                        status = "Closed"
                    elif "open" in open_date.lower() or any(m in open_date for m in ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']):
                        status = "Open"
                    else:
                        status = "Upcoming"

                    ch_url = chittorgarh_map.get(name_key, {}).get('chittorgarh_url')
                    if not ch_url:
                        ch_url = f"https://www.chittorgarh.com/search.asp?q={requests.utils.quote(clean_name)}"

                    mainboard_list.append({
                        'id': f"mainboard-ipo-{len(mainboard_list)+1}",
                        'name': clean_name,
                        'raw_name': raw_name,
                        'board_type': 'Mainboard',
                        'gmp': gmp_val,
                        'gmp_raw': gmp_raw,
                        'price': price_val,
                        'price_raw': price_raw,
                        'estimated_listing_price': est_listing_price,
                        'gain_percentage': gain_pct,
                        'gain_str': f"{gain_pct:+.2f}%" if gain_pct != 0 else gain_raw,
                        'rating': rating,
                        'open_date': open_date,
                        'close_date': close_date,
                        'boa_date': boa_date,
                        'lot_size': 'N/A',
                        'issue_size': 'N/A',
                        'status': status,
                        'chittorgarh_url': ch_url,
                        'last_updated': time.strftime('%Y-%m-%d %H:%M:%S')
                    })

            if mainboard_list:
                break

        except Exception as e:
            print(f"[IPO Service] Warning fetching GMP table from {url}: {e}")

    # Process official Chittorgarh Mainboard directory to ensure complete metadata
    if chittorgarh_map:
        for key, item in chittorgarh_map.items():
            if key not in fetched_names:
                fetched_names.add(key)
                # Fetch detailed info from Chittorgarh IPO page
                details = fetch_chittorgarh_ipo_details(item['chittorgarh_url'], headers)
                
                price_val = details['price']
                gmp_val = details['gmp']
                est_listing = round(price_val + gmp_val, 2) if price_val > 0 else 0
                gain_pct = round((gmp_val / price_val) * 100, 2) if price_val > 0 else 0.0

                mainboard_list.append({
                    'id': f"mainboard-ipo-{len(mainboard_list)+1}",
                    'name': item['name'],
                    'raw_name': item['name'],
                    'board_type': 'Mainboard',
                    'gmp': gmp_val,
                    'gmp_raw': details['gmp_raw'],
                    'price': price_val,
                    'price_raw': details['price_raw'],
                    'estimated_listing_price': est_listing,
                    'gain_percentage': gain_pct,
                    'gain_str': f"{gain_pct:+.2f}%" if gain_pct != 0 else "0.00%",
                    'rating': '-',
                    'open_date': details['open_date'],
                    'close_date': details['close_date'],
                    'boa_date': details['listing_date'],
                    'lot_size': details['lot_size'],
                    'issue_size': details['issue_size'],
                    'status': 'Upcoming' if details['open_date'] == 'TBA' else 'Active',
                    'chittorgarh_url': item['chittorgarh_url'],
                    'last_updated': time.strftime('%Y-%m-%d %H:%M:%S')
                })

    # Sort list: highest expected gain percentage first
    mainboard_list.sort(key=lambda x: x['gain_percentage'], reverse=True)

    # Compute summary stats
    total_count = len(mainboard_list)
    positive_gmp_count = sum(1 for item in mainboard_list if item['gmp'] > 0)
    top_gainer = mainboard_list[0] if mainboard_list else None
    avg_gain = round(sum(item['gain_percentage'] for item in mainboard_list) / total_count, 2) if total_count > 0 else 0

    summary = {
        'total_mainboard_ipos': total_count,
        'positive_gmp_count': positive_gmp_count,
        'avg_expected_gain': avg_gain,
        'top_gainer': top_gainer['name'] if top_gainer else None,
        'top_gainer_gain_pct': top_gainer['gain_percentage'] if top_gainer else 0,
        'source': 'Chittorgarh.com Mainboard Directory & Live GMP',
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
        _cache_lock_time = now
        _ipo_cache['timestamp'] = now
        
    return data

if __name__ == "__main__":
    res = get_mainboard_ipos_cached(force_refresh=True)
    print(json.dumps(res, indent=2))
