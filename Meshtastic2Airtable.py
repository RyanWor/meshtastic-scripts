import os
import json
import re
import requests
import argparse
import subprocess
from datetime import datetime

# Load configuration
CONFIG_FILE = "config.json"
if not os.path.exists(CONFIG_FILE):
    print(f"❌ Error: Missing {CONFIG_FILE}. Please create one based on config.example.json.")
    exit(1)

with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

AIRTABLE_API_KEY = config.get("AIRTABLE_API_KEY")
BASE_ID = config.get("AIRTABLE_BASE_ID")
TABLE_NAME = config.get("AIRTABLE_TABLE_NAME")

if not AIRTABLE_API_KEY or not BASE_ID or not TABLE_NAME:
    print("❌ Error: Missing required configuration values in config.json.")
    exit(1)

DEBUG_MODE = False

# Parse CLI args
parser = argparse.ArgumentParser(description="Update Airtable with Meshtastic Node Data")
parser.add_argument("--host", help="IP address of Meshtastic node")
parser.add_argument("--port", help="Serial port for Meshtastic node")
parser.add_argument("--ble", help="Bluetooth address for Meshtastic node")
args = parser.parse_args()

meshtastic_args = []
if args.host:
    meshtastic_command = f"meshtastic --host {args.host} --info --no-nodes"
    meshtastic_args += ["--host", args.host]
    connection_type = f"Using HOST: {args.host}"
elif args.port:
    meshtastic_command = f"meshtastic --port {args.port} --info --no-nodes"
    meshtastic_args += ["--port", args.port]
    connection_type = f"Using PORT: {args.port}"
elif args.ble:
    meshtastic_command = f"meshtastic --ble {args.ble} --info --no-nodes"
    meshtastic_args += ["--ble", args.ble]
    connection_type = f"Using BLE: {args.ble}"
else:
    meshtastic_command = "meshtastic --info --no-nodes"
    connection_type = "Using DEFAULT CONNECTION (serial or localhost)"

print(f"🔄 Running Meshtastic Command: {meshtastic_command}")
print(f"📡 {connection_type}")

def run_meshtastic_command():
    output = os.popen(meshtastic_command).read()
    return output.strip()

def parse_meshtastic_output(output):
    try:
        nodes_match = re.search(r'Nodes in mesh: (\{.*?\})\n\nPreferences:', output, re.DOTALL)
        metadata_match = re.search(r'Metadata: (\{.*?\})', output)
        security_match = re.search(r'"security": (\{.*?\}),', output, re.DOTALL)

        if not nodes_match or not metadata_match or not security_match:
            return None

        nodes_json = json.loads(nodes_match.group(1))
        metadata_json = json.loads(metadata_match.group(1))
        security_json = json.loads(security_match.group(1))

        first_node_key = list(nodes_json.keys())[0]
        first_node = nodes_json[first_node_key]

        user_info = first_node.get("user", {})
        device_metrics = first_node.get("deviceMetrics", {})

        data = {
            "Node ID": first_node_key,
            "Long Name": user_info.get("longName", ""),
            "Short Name": user_info.get("shortName", ""),
            "Hardware": user_info.get("hwModel", ""),
            "Node Number": str(first_node.get("num", "")),
            "MAC Address": user_info.get("macaddr", ""),
            "Public Key": security_json.get("publicKey", ""),
            "Private Key": security_json.get("privateKey", ""),
            "Role": metadata_json.get("role", ""),
            "Firmware": metadata_json.get("firmwareVersion", "")
        }

        if DEBUG_MODE:
            print("\n🔍 DEBUG: Parsed Meshtastic Data:")
            for key, value in data.items():
                print(f"  {key}: {value}")

        return data

    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return None

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

def update_airtable_record(airtable_record_id, data):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}/{airtable_record_id}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    payload = {"fields": data}
    if DEBUG_MODE:
        print(json.dumps(payload, indent=4))
    response = requests.patch(url, json=payload, headers=headers)
    if response.status_code == 200:
        print(f"✅ Updated record {airtable_record_id} for Node ID: {data['Node ID']}")
    else:
        print(f"❌ Error updating record: {response.status_code}, {response.text}")

def create_airtable_record(data):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    payload = {"fields": data}
    if DEBUG_MODE:
        print(json.dumps(payload, indent=4))
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        print(f"✅ Created new record for Node ID: {data['Node ID']}")
    else:
        print(f"❌ Error creating record: {response.status_code}, {response.text}")

def sanitize_filename_part(s):
    return re.sub(r'[^A-Za-z0-9_\-]', '', s.replace(" ", "_"))

def export_node_config(node_id, short_name, long_name, connection_args):
    if not node_id:
        print("❌ Cannot export config: Node ID missing.")
        return

    clean_id = node_id.replace("!", "")
    clean_short = sanitize_filename_part(short_name or "UNKNOWN")
    clean_long = sanitize_filename_part(long_name or "UNKNOWN")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    filename = f"{clean_short}_{clean_long}_{clean_id}_{timestamp}.yaml"
    export_dir = os.path.join(os.getcwd(), "ExportConfig")
    os.makedirs(export_dir, exist_ok=True)
    filepath = os.path.join(export_dir, filename)

    command = ["meshtastic.exe", "--export-config"] + connection_args

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            result = subprocess.run(command, stdout=f, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            print(f"📁 Exported config to: {filepath}")
        else:
            print(f"❌ Failed to export config:\n{result.stderr}")
    except Exception as e:
        print(f"❌ Error during config export: {e}")

# Main execution
output = run_meshtastic_command()
parsed_data = parse_meshtastic_output(output)

if parsed_data:
    node_id = parsed_data["Node ID"]
    record_id = find_airtable_record_by_node_id(node_id)
    if record_id:
        update_airtable_record(record_id, parsed_data)
    else:
        create_airtable_record(parsed_data)

    export_node_config(
        node_id=node_id,
        short_name=parsed_data.get("Short Name", ""),
        long_name=parsed_data.get("Long Name", ""),
        connection_args=meshtastic_args
    )
else:
    print("⚠️ Could not parse Meshtastic output.")
