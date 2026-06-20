import base64
import os

# Change this path to where your logo.png is
logo_path = "assets/logo.png"

if not os.path.exists(logo_path):
    print(f"ERROR: File not found at '{logo_path}'")
    print("Place this script in the same folder as your logo.png and run again.")
    exit()

with open(logo_path, "rb") as f:
    encoded = base64.b64encode(f.read()).decode()

# Write the config file
output = f'''# logo_data.py
# Auto-generated — do not edit manually
# Upload this file to your HF Space alongside app.py

LOGO_B64 = "{encoded}"
'''

with open("logo_data.py", "w") as f:
    f.write(output)

print("✅ logo_data.py generated successfully!")
print("Now upload logo_data.py to your HF Space.")
