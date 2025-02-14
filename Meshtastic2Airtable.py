import os
import json
import re
import requests
import argparse

# Load configuration from config.json
CONFIG_FILE = "config.json"

if not os.path.exists(CONFIG_FILE):
    print(f"❌ Error: Missing {CONFIG_FILE}. Please create one based on config.example.json.")
    exit(1)

with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

# Airtable API Configuration from config.json
AIRTABLE_API_KEY = config.get("AIRTABLE_API_KEY")
BASE_ID = config.get("AIRTABLE_BASE_ID")
TABLE_NAME = config.get("AIRTABLE_TABLE_NAME")

# Ensure required config values exist
if not AIRTABLE_API_KEY or not BASE_ID or not TABLE_NAME:
    print("❌ Error: Missing required configuration values in config.json.")
    exit(1)

# Enable Debug Mode
DEBUG_MODE = True  # Set to False to disable debug prints

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Update Airtable with Meshtastic Node Data")
parser.add_argument("--host", help="IP address of Meshtastic node")
parser.add_argument("--port", help="Serial port for Meshtastic node")
parser.add_argument("--ble", help="Bluetooth address for Meshtastic node")

args = parser.parse_args()

# Determine the Meshtastic connection method
if args.host:
    meshtastic_command = f"meshtastic --host {args.host} --info --no-nodes"
    connection_type = f"Using HOST: {args.host}"
elif args.port:
    meshtastic_command = f"meshtastic --port {args.port} --info --no-nodes"
    connection_type = f"Using PORT: {args.port}"
elif args.ble:
    meshtastic_command = f"meshtastic --ble {args.ble} --info --no-nodes"
    connection_type = f"Using BLE: {args.ble}"
else:
    meshtastic_command = "meshtastic --info --no-nodes"
    connection_type = "Using DEFAULT CONNECTION (serial or localhost)"

print(f"🔄 Running Meshtastic Command: {meshtastic_command}")
print(f"📡 {connection_type}")

# Function to run the Meshtastic command
def run_meshtastic_command():
    output = os.popen(meshtastic_command).read()
    return output.strip()

# Function to extract relevant data from the output
def parse_meshtastic_output(output):
    try:
        nodes_match = re.search(r'Nodes in mesh: (\{.*?\})\n\nPreferences:', output, re.DOTALL)
        metadata_match = re.search(r'Metadata: (\{.*?\})', output)

        if not nodes_match or not metadata_match:
            return None

        nodes_json = json.loads(nodes_match.group(1))
        metadata_json = json.loads(metadata_match.group(1))

        first_node_key = list(nodes_json.keys())[0]
        first_node = nodes_json[first_node_key]

        user_info = first_node.get("user", {})
        device_metrics = first_node.get("deviceMetrics", {})

        data = {
            "node_id": first_node_key,
            "long_name": user_info.get("longName", ""),
            "short_name": user_info.get("shortName", ""),
            "hardware": user_info.get("hwModel", ""),
            "node_number": str(first_node.get("num", "")),  
            "mac_address": user_info.get("macaddr", ""),
            "public_key": user_info.get("publicKey", ""),
            "role": metadata_json.get("role", ""),
            "firmware_version": metadata_json.get("firmwareVersion", ""),
        }

        if DEBUG_MODE:
            print("\n🔍 DEBUG: Parsed Meshtastic Data:")
            for key, value in data.items():
                print(f"  {key}: {value}")

        return data

    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return None

# Function to find the Airtable record by Node ID
def find_airtable_record_by_node_id(node_id):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    params = {"filterByFormula": f"{{Node ID}} = '{node_id}'"}

    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        records = response.json().get("records", [])
        if records:
            return records[0]["id"]
    return None

# Function to update an existing Airtable record
def update_airtable_record(airtable_record_id, data):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}/{airtable_record_id}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}

    payload = {"fields": data}

    if DEBUG_MODE:
        print("\n📡 DEBUG: Sending Data to Airtable (Update):")
        print(json.dumps(payload, indent=4))

    response = requests.patch(url, json=payload, headers=headers)

    if response.status_code == 200:
        print(f"✅ Updated record {airtable_record_id} for Node ID: {data['node_id']}")
    else:
        print(f"❌ Error updating record: {response.status_code}, {response.text}")

# Function to create a new Airtable record
def create_airtable_record(data):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}

    payload = {"fields": data}

    if DEBUG_MODE:
        print("\n📡 DEBUG: Sending Data to Airtable (Create):")
        print(json.dumps(payload, indent=4))

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code == 200:
        print(f"✅ Created new record for Node ID: {data['node_id']}")
    else:
        print(f"❌ Error creating record: {response.status_code}, {response.text}")

# Main execution
output = run_meshtastic_command()
parsed_data = parse_meshtastic_output(output)

if parsed_data:
    airtable_record_id = find_airtable_record_by_node_id(parsed_data["node_id"])
    
    if airtable_record_id:
        update_airtable_record(airtable_record_id, parsed_data)
    else:
        create_airtable_record(parsed_data)
else:
    print("⚠️ Could not parse Meshtastic output.")