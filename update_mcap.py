import csv
import os

# Path to the source CSV
CSV_FILE = "c:/moving-average/flask-moving-average/nifty500.csv"
OUTPUT_FILE = "c:/moving-average/flask-moving-average/mcap.py"

# Known ETFs to whitelist
ETFS = [
    "NIFTYBEES", "BANKBEES", "GOLDBEES", "ITBEES", "JUNIORBEES", "CPSEETF",
    "MON100", "NETITF", "SETFNIF50", "NV20BEES", "PHARMABEES", "ICICINV20",
    "AUTOBEES", "HDFCNIF50", "LICNETFGSC", "SHARIABEES", "MOMENTUM", "ALPHA"
]

def update_mcap():
    mcap_dict = {}
    company_dict = {
        "NIFTYBEES": "Nippon India Nifty 50 BeES",
        "BANKBEES": "Nippon India Bank BeES",
        "GOLDBEES": "Nippon India Gold BeES",
        "ITBEES": "Nippon India IT BeES",
        "JUNIORBEES": "Nippon India Junior BeES",
        "LIQUIDBEES": "Nippon India Liquid BeES",
    }
    
    # 0. Extract existing COMPANY_NAME from old mcap.py if it exists
    if os.path.exists(OUTPUT_FILE):
        print("Extracting existing company names...")
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            if "COMPANY_NAME = {" in content:
                try:
                    # Very basic extraction: everything after COMPANY_NAME = { until }
                    parts = content.split("COMPANY_NAME = {")
                    dict_str = parts[1].split("}")[0]
                    for line in dict_str.split("\n"):
                        line = line.strip()
                        if ":" in line:
                            # Clean up quotes and commas
                            k_v = line.split(":")
                            key = k_v[0].strip().strip('"').strip("'")
                            val = k_v[1].strip().strip(',').strip('"').strip("'")
                            company_dict[key] = val
                except Exception as e:
                    print(f"Warning: Could not extract all company names: {e}")

    # 1. Load the Nifty 500 CSV
    if os.path.exists(CSV_FILE):
        print(f"Parsing {CSV_FILE}...")
        with open(CSV_FILE, mode='r', encoding='utf-8') as f:
            reader = csv.reader(f)
            try:
                header = next(reader) # Skip header
                for row in reader:
                    if len(row) >= 3:
                        symbol = row[2].strip().upper()
                        name = row[0].strip()
                        # Assign a default high MCAP to bypass any filters
                        mcap_dict[symbol] = 500000000 
                        if symbol not in company_dict:
                            company_dict[symbol] = name
            except Exception as e:
                print(f"Error parsing CSV: {e}")
    
    # 2. Add ETFs to MCAP
    for etf in ETFS:
        mcap_dict[etf.upper()] = 500000000 

    # 3. Write mcap.py
    print(f"Writing updated data to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("# Market Cap Database (Updated Total Market)\n")
        f.write("# NOTE: Assigned 500,000,000 as default to ensure liquidity filters pass.\n")
        f.write("MCAP = {\n")
        for symbol in sorted(mcap_dict.keys()):
            f.write(f'    "{symbol}": {mcap_dict[symbol]},\n')
        f.write("}\n\n")
        
        f.write("COMPANY_NAME = {\n")
        for symbol in sorted(company_dict.keys()):
            # Handle symbols that might contain quotes
            escaped_name = company_dict[symbol].replace('"', '\\"')
            f.write(f'    "{symbol}": "{escaped_name}",\n')
        f.write("}\n")

    print(f"Successfully updated {OUTPUT_FILE} with {len(mcap_dict)} symbols and {len(company_dict)} company names.")

if __name__ == "__main__":
    update_mcap()
